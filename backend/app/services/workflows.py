"""Saved workflows: named chains of tools, personal or shared with a team."""

from __future__ import annotations

from sqlalchemy import func, or_, select

from app.domain.errors import NotFound, PremiumRequired
from app.infra.db import Database, Membership, Workflow
from app.services.actors import Actor
from app.services.jobs import JobService


class WorkflowService:
    def __init__(self, *, db: Database, jobs: JobService):
        self.db = db
        self.jobs = jobs

    def list(self, actor: Actor) -> list[Workflow]:
        if actor.user is None:
            return []
        with self.db.session() as session:
            team_ids = select(Membership.team_id).where(Membership.user_id == actor.user.id)
            return list(
                session.scalars(
                    select(Workflow)
                    .where(or_(Workflow.user_id == actor.user.id, Workflow.team_id.in_(team_ids)))
                    .order_by(Workflow.updated_at.desc())
                )
            )

    def save(self, actor: Actor, name: str, steps: list[dict], team_id: str | None = None,
             workflow_id: str | None = None) -> Workflow:  # fmt: skip
        if actor.user is None or actor.plan.max_workflows == 0:
            raise PremiumRequired("Saved workflows are a Pro feature.")
        parsed = self.jobs.parse_steps(steps)
        normalized = [s.as_json() for s in parsed]
        with self.db.session() as session:
            if team_id is not None:
                member = session.scalar(
                    select(Membership).where(Membership.team_id == team_id, Membership.user_id == actor.user.id)
                )
                if member is None:
                    raise NotFound("Team not found.")
            if workflow_id:
                wf = self._editable(session, actor, workflow_id)
                wf.name, wf.steps, wf.team_id = name.strip()[:200] or wf.name, normalized, team_id
                return wf
            limit = actor.plan.max_workflows
            if limit is not None:
                count = session.scalar(
                    select(func.count()).select_from(Workflow).where(Workflow.user_id == actor.user.id)
                )
                if count >= limit:
                    raise PremiumRequired(f"You can save up to {limit} workflows on your plan.")
            wf = Workflow(
                user_id=actor.user.id, team_id=team_id, name=name.strip()[:200] or "Workflow", steps=normalized
            )
            session.add(wf)
            session.flush()
            return wf

    def get(self, actor: Actor, workflow_id: str) -> Workflow:
        for wf in self.list(actor):
            if wf.id == workflow_id:
                return wf
        raise NotFound("Workflow not found.")

    def delete(self, actor: Actor, workflow_id: str) -> None:
        with self.db.session() as session:
            session.delete(self._editable(session, actor, workflow_id))

    @staticmethod
    def _editable(session, actor: Actor, workflow_id: str) -> Workflow:
        wf = session.get(Workflow, workflow_id)
        if wf is None or actor.user is None:
            raise NotFound("Workflow not found.")
        if wf.user_id != actor.user.id:
            role = session.scalar(
                select(Membership.role).where(Membership.team_id == wf.team_id, Membership.user_id == actor.user.id)
            )
            if role not in ("owner", "admin"):
                raise NotFound("Workflow not found.")
        return wf
