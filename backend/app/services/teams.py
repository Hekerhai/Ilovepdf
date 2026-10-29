"""Team workspaces: members, roles, invitations and seat limits."""

import secrets
from datetime import timedelta

from sqlalchemy import func, select

from app.domain.errors import Forbidden, NotFound, PremiumRequired, ValidationFailed
from app.domain.ports import Mailer
from app.infra.db import Database, Invitation, Membership, Team, User, as_utc, utcnow
from app.plans import get_plan
from app.services.auth import normalize_email, sha256

ROLES = ("owner", "admin", "member")


class TeamService:
    def __init__(self, *, db: Database, mailer: Mailer, public_url: str, brand_name: str):
        self.db = db
        self.mailer = mailer
        self.public_url = public_url.rstrip("/")
        self.brand = brand_name

    def create(self, owner: User, name: str) -> Team:
        name = name.strip()
        if not name:
            raise ValidationFailed("Give your team a name.")
        with self.db.session() as session:
            team = Team(name=name[:200])
            session.add(team)
            session.flush()
            session.add(Membership(team_id=team.id, user_id=owner.id, role="owner"))
            return team

    def list_for(self, user: User) -> list[dict]:
        with self.db.session() as session:
            rows = session.execute(
                select(Team, Membership.role).join(Membership).where(Membership.user_id == user.id)
            ).all()
            return [self._summary(session, team, role) for team, role in rows]

    def detail(self, user: User, team_id: str) -> dict:
        with self.db.session() as session:
            team, role = self._require(session, user, team_id)
            members = session.execute(
                select(User, Membership.role).join(Membership).where(Membership.team_id == team.id)
            ).all()
            invites = session.scalars(
                select(Invitation).where(Invitation.team_id == team.id, Invitation.accepted_at.is_(None))
            ).all()
            return {
                **self._summary(session, team, role),
                "members": [{"user_id": u.id, "email": u.email, "name": u.name, "role": r} for u, r in members],
                "invitations": [
                    {"id": i.id, "email": i.email, "role": i.role, "expires_at": i.expires_at.isoformat()}
                    for i in invites
                    if as_utc(i.expires_at) > utcnow()
                ],
            }

    def invite(self, user: User, team_id: str, email: str, role: str = "member") -> None:
        if role not in ("admin", "member"):
            raise ValidationFailed("Role must be admin or member.")
        email = normalize_email(email)
        with self.db.session() as session:
            team, my_role = self._require(session, user, team_id, admin=True)
            plan = get_plan(team.plan_id)
            if not plan.team_workspace:
                raise PremiumRequired("Inviting teammates needs the Business plan.")
            if self._seats_used(session, team.id) >= team.seats:
                raise PremiumRequired(f"All {team.seats} seats are in use. Add seats to invite more people.")
            token = secrets.token_urlsafe(32)
            session.add(
                Invitation(
                    team_id=team.id, email=email, role=role, token_hash=sha256(token),
                    expires_at=utcnow() + timedelta(days=7),
                )
            )  # fmt: skip
            team_name = team.name
        self.mailer.send(
            to=email,
            subject=f"{user.name or user.email} invited you to {team_name} on {self.brand}",
            text=f"Join the team here (link valid for 7 days):\n\n{self.public_url}/teams/join?token={token}",
        )

    def accept(self, user: User, token: str) -> Team:
        with self.db.session() as session:
            invite = session.scalar(select(Invitation).where(Invitation.token_hash == sha256(token)))
            if invite is None or invite.accepted_at is not None or as_utc(invite.expires_at) < utcnow():
                raise NotFound("This invitation is invalid or has expired.")
            if normalize_email(user.email) != invite.email:
                raise Forbidden(f"This invitation was sent to {invite.email}. Sign in with that address.")
            invite.accepted_at = utcnow()
            exists = session.scalar(
                select(Membership).where(Membership.team_id == invite.team_id, Membership.user_id == user.id)
            )
            if exists is None:
                session.add(Membership(team_id=invite.team_id, user_id=user.id, role=invite.role))
            return session.get(Team, invite.team_id)

    def set_role(self, user: User, team_id: str, member_id: str, role: str) -> None:
        if role not in ROLES:
            raise ValidationFailed("Unknown role.")
        with self.db.session() as session:
            self._require(session, user, team_id, owner=True)
            membership = self._membership(session, team_id, member_id)
            if membership.role == "owner" and role != "owner" and self._owner_count(session, team_id) == 1:
                raise ValidationFailed("A team needs at least one owner.")
            membership.role = role

    def remove_member(self, user: User, team_id: str, member_id: str) -> None:
        with self.db.session() as session:
            if member_id != user.id:
                self._require(session, user, team_id, admin=True)
            membership = self._membership(session, team_id, member_id)
            if membership.role == "owner" and self._owner_count(session, team_id) == 1:
                raise ValidationFailed("Transfer ownership before the last owner leaves.")
            session.delete(membership)

    def revoke_invitation(self, user: User, team_id: str, invitation_id: str) -> None:
        with self.db.session() as session:
            self._require(session, user, team_id, admin=True)
            invite = session.get(Invitation, invitation_id)
            if invite is None or invite.team_id != team_id:
                raise NotFound("Invitation not found.")
            session.delete(invite)

    def role_of(self, user: User, team_id: str) -> str | None:
        with self.db.session() as session:
            m = session.scalar(select(Membership).where(Membership.team_id == team_id, Membership.user_id == user.id))
            return m.role if m else None

    # ---- helpers ----------------------------------------------------------------------------

    def _require(self, session, user: User, team_id: str, *, admin=False, owner=False) -> tuple[Team, str]:
        row = session.execute(
            select(Team, Membership.role).join(Membership).where(Team.id == team_id, Membership.user_id == user.id)
        ).first()
        if row is None:
            raise NotFound("Team not found.")
        team, role = row
        if owner and role != "owner":
            raise Forbidden("Only team owners can do that.")
        if admin and role not in ("owner", "admin"):
            raise Forbidden("Only team admins can do that.")
        return team, role

    @staticmethod
    def _membership(session, team_id: str, user_id: str) -> Membership:
        m = session.scalar(select(Membership).where(Membership.team_id == team_id, Membership.user_id == user_id))
        if m is None:
            raise NotFound("Member not found.")
        return m

    @staticmethod
    def _owner_count(session, team_id: str) -> int:
        return session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.team_id == team_id, Membership.role == "owner")
        )

    @staticmethod
    def _seats_used(session, team_id: str) -> int:
        members = session.scalar(select(func.count()).select_from(Membership).where(Membership.team_id == team_id))
        pending = session.scalar(
            select(func.count())
            .select_from(Invitation)
            .where(Invitation.team_id == team_id, Invitation.accepted_at.is_(None), Invitation.expires_at > utcnow())
        )
        return members + pending

    def _summary(self, session, team: Team, role: str) -> dict:
        return {
            "id": team.id,
            "name": team.name,
            "plan": team.plan_id,
            "seats": team.seats,
            "seats_used": self._seats_used(session, team.id),
            "role": role,
        }
