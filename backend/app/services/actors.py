"""Who is making a request, and what their plan entitles them to."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.db import ApiKey, Membership, Subscription, Team, User, utcnow
from app.plans import PLANS, Plan, PlanId, get_plan

_RANK = {plan_id: rank for rank, plan_id in enumerate(PLANS)}


@dataclass
class Actor:
    plan: Plan
    user: User | None = None
    guest_id: str | None = None
    ip_hash: str | None = None
    api_key: ApiKey | None = None

    @property
    def is_guest(self) -> bool:
        return self.user is None

    @property
    def via_api(self) -> bool:
        return self.api_key is not None


def effective_plan(session: Session, user: User) -> Plan:
    """The best plan among the user's own plan and those of the teams they belong to."""
    candidates = [PlanId(user.plan_id)]
    team_plans = session.scalars(
        select(Team.plan_id).join(Membership, Membership.team_id == Team.id).where(Membership.user_id == user.id)
    ).all()
    candidates.extend(PlanId(p) for p in team_plans)
    passes = session.scalars(
        select(Subscription.plan_id).where(
            Subscription.owner_type == "user",
            Subscription.owner_id == user.id,
            Subscription.status == "pass",
            Subscription.current_period_end > utcnow(),
        )
    ).all()
    candidates.extend(PlanId(p) for p in passes)
    return get_plan(max(candidates, key=lambda p: _RANK[p]))


def guest_actor(guest_id: str | None, ip_hash: str | None) -> Actor:
    return Actor(plan=get_plan(PlanId.GUEST), guest_id=guest_id, ip_hash=ip_hash)


def user_actor(session: Session, user: User, *, ip_hash: str | None = None, api_key: ApiKey | None = None) -> Actor:
    return Actor(plan=effective_plan(session, user), user=user, ip_hash=ip_hash, api_key=api_key)
