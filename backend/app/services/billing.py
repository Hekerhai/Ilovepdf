"""Billing: start checkouts and apply provider webhooks to plans. Providers are pluggable PaymentGateways."""

import logging

from sqlalchemy import select

from app.domain.errors import Forbidden, NotFound, ServiceUnavailable, ValidationFailed
from app.domain.ports import CheckoutSession, PaymentGateway, SubscriptionEvent
from app.infra.db import Database, Membership, Subscription, Team, User
from app.plans import PLANS, BillingInterval, PlanId, get_plan

log = logging.getLogger(__name__)


class BillingService:
    def __init__(self, *, db: Database, gateways: dict[str, PaymentGateway], public_url: str):
        self.db = db
        self.gateways = gateways
        self.public_url = public_url.rstrip("/")

    def catalog(self) -> dict:
        return {
            "providers": [
                {"id": name, "currency": getattr(g, "currency", "").upper(), "configured": g.configured}
                for name, g in self.gateways.items()
            ],
            "plans": [
                {
                    "id": plan.id.value,
                    "name": plan.name,
                    "max_file_mb": plan.max_file_bytes // (1024 * 1024),
                    "max_files_per_task": plan.max_files_per_task,
                    "tasks_per_day": plan.tasks_per_day,
                    "premium_tools": plan.premium_tools,
                    "team_workspace": plan.team_workspace,
                    "monthly_api_credits": plan.monthly_api_credits,
                    "per_seat": plan.per_seat,
                    "min_seats": plan.min_seats,
                    "highlights": list(plan.highlights),
                    "prices": {
                        interval.value: {"usd": price.usd, "inr": price.inr} for interval, price in plan.prices.items()
                    },
                }
                for plan in PLANS.values()
                if plan.id != PlanId.GUEST
            ],
        }

    def checkout(
        self,
        user: User,
        *,
        plan_id: str,
        interval: str,
        provider: str,
        seats: int = 1,
        team_id: str | None = None,
    ) -> CheckoutSession:
        gateway = self.gateways.get(provider)
        if gateway is None:
            raise ValidationFailed("Unknown payment provider.")
        if not gateway.configured:
            raise ServiceUnavailable(f"{provider.title()} payments are not configured yet.")
        plan = get_plan(plan_id)
        if not plan.purchasable:
            raise ValidationFailed("That plan can't be purchased.")
        price = plan.prices.get(BillingInterval(interval))
        if price is None:
            raise ValidationFailed("Choose monthly or yearly billing.")
        if plan.team_workspace:
            if team_id is None:
                raise ValidationFailed("Choose the team to upgrade.")
            seats = max(seats, plan.min_seats)
            with self.db.session() as session:
                role = session.scalar(
                    select(Membership.role).where(Membership.team_id == team_id, Membership.user_id == user.id)
                )
                if role is None:
                    raise NotFound("Team not found.")
                if role != "owner":
                    raise Forbidden("Only team owners can change the plan.")
            owner_type, owner_id = "team", team_id
        else:
            seats, owner_type, owner_id = 1, "user", user.id
        amount = price.inr if provider == "razorpay" else price.usd
        return gateway.create_checkout(
            owner_type=owner_type,
            owner_id=owner_id,
            email=user.email,
            plan_id=plan.id.value,
            interval=interval,
            seats=seats,
            amount=amount,
            success_url=f"{self.public_url}/account/billing?status=success",
            cancel_url=f"{self.public_url}/pricing?status=cancelled",
        )

    def handle_webhook(self, provider: str, payload: bytes, headers: dict[str, str]) -> SubscriptionEvent:
        gateway = self.gateways.get(provider)
        if gateway is None:
            raise NotFound("Unknown payment provider.")
        event = gateway.parse_webhook(payload, {k.lower(): v for k, v in headers.items()})
        self.apply(event)
        return event

    def apply(self, event: SubscriptionEvent) -> None:
        if event.kind == "ignored" or not event.external_subscription_id:
            return
        with self.db.session() as session:
            sub = session.scalar(select(Subscription).where(Subscription.external_id == event.external_subscription_id))
            if sub is None:
                if event.kind == "cancelled" or not (event.owner_type and event.owner_id and event.plan_id):
                    log.warning("Webhook for unknown subscription %s ignored", event.external_subscription_id)
                    return
                sub = Subscription(
                    owner_type=event.owner_type,
                    owner_id=event.owner_id,
                    provider=event.provider,
                    external_id=event.external_subscription_id,
                    plan_id=event.plan_id,
                )
                session.add(sub)
            sub.external_customer_id = event.external_customer_id or sub.external_customer_id
            sub.seats = event.seats
            sub.current_period_end = event.current_period_end or sub.current_period_end
            sub.status = "cancelled" if event.kind == "cancelled" else "active"
            owner = session.get(Team if sub.owner_type == "team" else User, sub.owner_id)
            if owner is None:
                return
            if sub.status == "active":
                owner.plan_id = sub.plan_id
                if isinstance(owner, Team):
                    owner.seats = sub.seats
            else:
                still_active = session.scalar(
                    select(Subscription).where(
                        Subscription.owner_id == sub.owner_id,
                        Subscription.status == "active",
                        Subscription.id != sub.id,
                    )
                )
                owner.plan_id = still_active.plan_id if still_active else PlanId.FREE.value
                if isinstance(owner, Team) and not still_active:
                    owner.seats = 1

    def subscriptions(self, user: User) -> list[Subscription]:
        with self.db.session() as session:
            team_ids = select(Membership.team_id).where(Membership.user_id == user.id, Membership.role == "owner")
            return list(
                session.scalars(
                    select(Subscription).where(
                        ((Subscription.owner_type == "user") & (Subscription.owner_id == user.id))
                        | ((Subscription.owner_type == "team") & Subscription.owner_id.in_(team_ids))
                    )
                )
            )

    def cancel(self, user: User, subscription_id: str) -> None:
        subs = {s.id: s for s in self.subscriptions(user)}
        sub = subs.get(subscription_id)
        if sub is None:
            raise NotFound("Subscription not found.")
        if sub.status == "active" and sub.external_id:
            self.gateways[sub.provider].cancel(sub.external_id)
        # The provider's webhook confirms the cancellation and downgrades the plan.
