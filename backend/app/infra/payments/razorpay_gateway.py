"""Razorpay adapter (subscriptions in INR, hosted payment page via short_url)."""

import hashlib
import hmac
import json
from datetime import UTC, datetime

from app.domain.errors import ServiceUnavailable, ValidationFailed
from app.domain.ports import CheckoutSession, SubscriptionEvent

_PERIOD = {"month": ("monthly", 120), "year": ("yearly", 10)}  # period, number of billing cycles


class RazorpayGateway:
    name = "razorpay"
    currency = "INR"

    def __init__(self, key_id: str | None, key_secret: str | None, webhook_secret: str | None):
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret
        self._plan_cache: dict[tuple[str, str, int], str] = {}

    @property
    def configured(self) -> bool:
        return bool(self._key_id and self._key_secret)

    def _client(self):
        if not self.configured:
            raise ServiceUnavailable("UPI and Indian card payments are not configured yet.")
        import razorpay

        return razorpay.Client(auth=(self._key_id, self._key_secret))

    def _plan(self, client, plan_id: str, interval: str, amount: int) -> str:
        """Razorpay subscriptions need a Plan object; find or create one per (plan, interval, amount)."""
        cache_key = (plan_id, interval, amount)
        if cache_key in self._plan_cache:
            return self._plan_cache[cache_key]
        tag = f"folio:{plan_id}:{interval}:{amount}"
        for existing in client.plan.all({"count": 100}).get("items", []):
            if (existing.get("notes") or {}).get("tag") == tag:
                self._plan_cache[cache_key] = existing["id"]
                return existing["id"]
        period, _ = _PERIOD[interval]
        created = client.plan.create({
            "period": period,
            "interval": 1,
            "item": {"name": f"{plan_id.title()} ({interval}ly)", "amount": amount, "currency": self.currency},
            "notes": {"tag": tag},
        })  # fmt: skip
        self._plan_cache[cache_key] = created["id"]
        return created["id"]

    def create_checkout(
        self, *, owner_type, owner_id, email, plan_id, interval, seats, amount, success_url, cancel_url
    ):
        client = self._client()
        _, total_count = _PERIOD[interval]
        subscription = client.subscription.create({
            "plan_id": self._plan(client, plan_id, interval, amount),
            "total_count": total_count,
            "quantity": seats,
            "customer_notify": 1,
            "notes": {"owner_type": owner_type, "owner_id": owner_id, "plan_id": plan_id, "email": email},
        })  # fmt: skip
        return CheckoutSession(
            provider=self.name,
            url=subscription.get("short_url"),
            client_payload={"key": self._key_id, "subscription_id": subscription["id"]},
        )

    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> SubscriptionEvent:
        if not self._webhook_secret:
            raise ServiceUnavailable("Razorpay webhook secret is not configured.")
        expected = hmac.new(self._webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, headers.get("x-razorpay-signature", "")):
            raise ValidationFailed("Invalid Razorpay signature.")
        event = json.loads(payload)
        kind = {
            "subscription.activated": "activated",
            "subscription.charged": "renewed",
            "subscription.resumed": "renewed",
            "subscription.cancelled": "cancelled",
            "subscription.completed": "cancelled",
            "subscription.halted": "cancelled",
        }.get(event.get("event"))
        if kind is None:
            return SubscriptionEvent(provider=self.name, kind="ignored")
        sub = event["payload"]["subscription"]["entity"]
        notes = sub.get("notes") or {}
        end = sub.get("current_end")
        return SubscriptionEvent(
            provider=self.name,
            kind=kind,
            owner_type=notes.get("owner_type"),
            owner_id=notes.get("owner_id"),
            plan_id=notes.get("plan_id"),
            seats=int(sub.get("quantity") or 1),
            external_customer_id=sub.get("customer_id"),
            external_subscription_id=sub.get("id"),
            current_period_end=datetime.fromtimestamp(end, UTC) if end else None,
        )

    def cancel(self, external_subscription_id: str) -> None:
        self._client().subscription.cancel(external_subscription_id, {"cancel_at_cycle_end": 0})
