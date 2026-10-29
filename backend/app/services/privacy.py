"""GDPR and retention: data export, account deletion, and the janitor that auto-deletes files."""

import logging
from datetime import timedelta

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.domain.ports import FileStorage
from app.infra.db import ApiKey, Database, Job, LoginToken, Membership, Subscription, Team, User, Workflow, utcnow
from app.services.billing import BillingService

log = logging.getLogger(__name__)

JOB_METADATA_DAYS = 30


def delete(model):
    # Bulk deletes without in-Python evaluation (SQLite returns naive datetimes).
    return sa_delete(model).execution_options(synchronize_session=False)


class PrivacyService:
    def __init__(self, *, db: Database, storage: FileStorage, billing: BillingService):
        self.db = db
        self.storage = storage
        self.billing = billing

    def export(self, user_id: str) -> dict:
        with self.db.session() as session:
            user = session.get(User, user_id)
            memberships = session.execute(
                select(Team.name, Membership.role).join(Membership).where(Membership.user_id == user_id)
            ).all()
            return {
                "account": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "plan": user.plan_id,
                    "created_at": user.created_at.isoformat(),
                    "google_linked": bool(user.google_sub),
                    "has_password": bool(user.password_hash),
                },
                "teams": [{"name": n, "role": r} for n, r in memberships],
                "tasks": [
                    {
                        "id": j.id,
                        "tools": [s["tool"] for s in j.steps],
                        "inputs": j.input_names,
                        "status": j.status,
                        "created_at": j.created_at.isoformat(),
                    }
                    for j in session.scalars(select(Job).where(Job.user_id == user_id))
                ],
                "workflows": [
                    {"name": w.name, "steps": w.steps}
                    for w in session.scalars(select(Workflow).where(Workflow.user_id == user_id))
                ],
                "api_keys": [
                    {"name": k.name, "prefix": k.prefix, "created_at": k.created_at.isoformat()}
                    for k in session.scalars(select(ApiKey).where(ApiKey.user_id == user_id))
                ],
                "subscriptions": [
                    {"plan": s.plan_id, "provider": s.provider, "status": s.status}
                    for s in session.scalars(
                        select(Subscription).where(Subscription.owner_type == "user", Subscription.owner_id == user_id)
                    )
                ],
            }

    def delete_account(self, user_id: str) -> None:
        with self.db.session() as session:
            user = session.get(User, user_id)
        for sub in self.billing.subscriptions(user):
            if sub.owner_type == "user" and sub.status == "active":
                try:
                    self.billing.cancel(user, sub.id)
                except Exception:
                    log.exception("Could not cancel subscription %s during account deletion", sub.id)
        with self.db.session() as session:
            for job_id in session.scalars(select(Job.id).where(Job.user_id == user_id)):
                self.storage.delete_prefix(f"jobs/{job_id}/")
            session.execute(delete(Job).where(Job.user_id == user_id))
            session.execute(delete(Workflow).where(Workflow.user_id == user_id))
            session.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
            session.execute(delete(LoginToken).where(LoginToken.email == user.email))
            session.execute(
                delete(Subscription).where(Subscription.owner_type == "user", Subscription.owner_id == user_id)
            )
            # Teams where they were the only member go too.
            for team_id in session.scalars(select(Membership.team_id).where(Membership.user_id == user_id)).all():
                others = session.scalar(
                    select(Membership).where(Membership.team_id == team_id, Membership.user_id != user_id)
                )
                if others is None:
                    session.delete(session.get(Team, team_id))
            session.delete(session.get(User, user_id))

    def purge_expired(self) -> dict:
        """Delete files past their TTL and job metadata past the retention window."""
        now = utcnow()
        files = 0
        with self.db.session() as session:
            expired = session.scalars(
                select(Job).where(Job.expires_at < now, Job.files_deleted.is_(False)).limit(1000)
            ).all()
            for job in expired:
                self.storage.delete_prefix(f"jobs/{job.id}/")
                job.files_deleted = True
                if job.status in ("queued", "running"):
                    job.status, job.error = "failed", "Timed out."
                files += 1
            old = now - timedelta(days=JOB_METADATA_DAYS)
            rows = session.execute(delete(Job).where(Job.created_at < old, Job.files_deleted.is_(True))).rowcount
            session.execute(delete(LoginToken).where(LoginToken.expires_at < now))
        if files or rows:
            log.info("Janitor removed files for %s tasks and %s old task records", files, rows)
        return {"files": files, "records": rows}
