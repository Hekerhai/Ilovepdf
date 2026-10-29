"""Stripe adapter (Checkout + subscription webhooks). Prices are created inline, so no dashboard setup is needed."""

from datetime import UTC, datetime

from app.domain.errors import ServiceUnavailable, ValidationFailed
from app.domain.ports import CheckoutSession, SubscriptionEvent


class StripeGateway:
    name = "stripe"
    currency = "usd"

    def __init__(self, secret_key: str | None, webhook_secret: str | None):
        self._key = secret_key
        self._webhook_secret = webhook_secret

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _stripe(self):
        if not self.configured:
            raise ServiceUnavailable("Card payments are not configured yet.")
        import stripe

        stripe.api_key = self._key
        return stripe

    def create_checkout(
        self, *, owner_type, owner_id, email, plan_id, interval, seats, amount, success_url, cancel_url
    ):
        stripe = self._stripe()
        metadata = {"owner_type": owner_type, "owner_id": owner_id, "plan_id": plan_id}
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            client_reference_id=f"{owner_type}:{owner_id}",
            line_items=[
                {
                    "quantity": seats,
                    "price_data": {
                        "currency": self.currency,
                        "unit_amount": amount,
                        "recurring": {"interval": interval},
                        "product_data": {"name": f"{plan_id.title()} plan"},
                    },
                }
            ],
            metadata=metadata,
            subscription_data={"metadata": metadata},
            allow_promotion_codes=True,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return CheckoutSession(provider=self.name, url=session.url)

    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> SubscriptionEvent:
        stripe = self._stripe()
        if not self._webhook_secret:
            raise ServiceUnavailable("Stripe webhook secret is not configured.")
        try:
            event = stripe.Webhook.construct_event(payload, headers.get("stripe-signature", ""), self._webhook_secret)
        except (ValueError, stripe.SignatureVerificationError):
            raise ValidationFailed("Invalid Stripe signature.") from None
        obj = event["data"]["object"]
        kind = {
            "customer.subscription.created": "activated",
            "customer.subscription.updated": "renewed",
            "customer.subscription.deleted": "cancelled",
        }.get(event["type"])
        if kind is None:
            return SubscriptionEvent(provider=self.name, kind="ignored")
        if kind != "cancelled" and obj.get("status") not in ("active", "trialing"):
            kind = "cancelled" if obj.get("status") in ("canceled", "unpaid", "incomplete_expired") else "ignored"
        meta = obj.get("metadata") or {}
        items = (obj.get("items") or {}).get("data") or [{}]
        period_end = obj.get("current_period_end") or items[0].get("current_period_end")
        return SubscriptionEvent(
            provider=self.name,
            kind=kind,
            owner_type=meta.get("owner_type"),
            owner_id=meta.get("owner_id"),
            plan_id=meta.get("plan_id"),
            seats=int(items[0].get("quantity") or 1),
            external_customer_id=obj.get("customer"),
            external_subscription_id=obj.get("id"),
            current_period_end=datetime.fromtimestamp(period_end, UTC) if period_end else None,
        )

    def cancel(self, external_subscription_id: str) -> None:
        self._stripe().Subscription.cancel(external_subscription_id)
