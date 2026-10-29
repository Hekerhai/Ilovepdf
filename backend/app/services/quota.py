"""Enforces plan limits. Kept separate from job execution so limits can change without touching the runner."""

from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.errors import PremiumRequired, QuotaExceeded, ValidationFailed
from app.infra.db import Job, utcnow
from app.plans import MB
from app.services.actors import Actor
from app.tools.base import Tool


class QuotaService:
    def check_tools(self, actor: Actor, tools: list[Tool]) -> None:
        premium = [t.name for t in tools if t.premium]
        if premium and not actor.plan.premium_tools:
            raise PremiumRequired(f"{', '.join(premium)} is a Pro feature. Upgrade to use it.")
        if len(tools) > 1 and actor.plan.max_workflows == 0:
            raise PremiumRequired("Workflows (chaining tools) are a Pro feature.")

    def check_files(self, actor: Actor, sizes: list[int]) -> None:
        limit = actor.plan.max_file_bytes
        if any(size > limit for size in sizes):
            raise QuotaExceeded(
                f"Files on the {actor.plan.name} plan can be up to {limit // MB} MB. Upgrade for bigger files.",
                code="file_too_large",
            )
        if len(sizes) > actor.plan.max_files_per_task:
            raise QuotaExceeded(
                f"The {actor.plan.name} plan allows {actor.plan.max_files_per_task} files per task.",
                code="too_many_files",
            )

    def check_rate(self, session: Session, actor: Actor) -> None:
        if actor.via_api:
            self._check_api_credits(session, actor)
            return
        limit = actor.plan.tasks_per_day
        if limit is None:
            return
        since = utcnow() - timedelta(days=1)
        if actor.user is not None:
            owner = Job.user_id == actor.user.id
        else:
            # Count by guest cookie *or* hashed IP, so clearing cookies doesn't reset the limit.
            clauses = []
            if actor.guest_id:
                clauses.append(Job.guest_id == actor.guest_id)
            if actor.ip_hash:
                clauses.append(Job.ip_hash == actor.ip_hash)
            if not clauses:
                raise ValidationFailed("Enable cookies to use the free tools.")
            owner = or_(*clauses) & Job.user_id.is_(None)
        used = session.scalar(select(func.count()).select_from(Job).where(owner, Job.created_at >= since))
        if used >= limit:
            hint = "Sign up for free to get more." if actor.is_guest else "Upgrade to Pro for unlimited tasks."
            raise QuotaExceeded(f"You've used today's {limit} free tasks. {hint}", code="daily_limit")

    def _check_api_credits(self, session: Session, actor: Actor) -> None:
        now = utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.user_id == actor.user.id, Job.api_key_id.is_not(None), Job.created_at >= month_start)
        )
        if used >= actor.plan.monthly_api_credits:
            raise QuotaExceeded(
                f"You've used this month's {actor.plan.monthly_api_credits} API credits.", code="api_credits"
            )

    def api_usage(self, session: Session, actor: Actor) -> dict:
        now = utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.user_id == actor.user.id, Job.api_key_id.is_not(None), Job.created_at >= month_start)
        )
        return {"used": used, "included": actor.plan.monthly_api_credits, "period_start": month_start.isoformat()}

    def tasks_today(self, session: Session, actor: Actor) -> int:
        if actor.user is None:
            return 0
        since = utcnow() - timedelta(days=1)
        return session.scalar(
            select(func.count()).select_from(Job).where(Job.user_id == actor.user.id, Job.created_at >= since)
        )
