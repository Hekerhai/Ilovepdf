from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import container, user
from app.container import Container
from app.services.actors import Actor

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"


class RoleIn(BaseModel):
    role: str


class JoinIn(BaseModel):
    token: str = Field(..., max_length=200)


@router.get("")
def list_teams(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"teams": c.teams.list_for(a.user)}


@router.post("", status_code=201)
def create_team(body: TeamIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    team = c.teams.create(a.user, body.name)
    return c.teams.detail(a.user, team.id)


@router.post("/join")
def join(body: JoinIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    team = c.teams.accept(a.user, body.token)
    return c.teams.detail(a.user, team.id)


@router.get("/{team_id}")
def team_detail(team_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return c.teams.detail(a.user, team_id)


@router.post("/{team_id}/invitations", status_code=201)
def invite(team_id: str, body: InviteIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"invite:{a.user.id}", limit=50, window_seconds=3600)
    c.teams.invite(a.user, team_id, body.email, body.role)
    return c.teams.detail(a.user, team_id)


@router.delete("/{team_id}/invitations/{invitation_id}", status_code=204)
def revoke_invite(team_id: str, invitation_id: str, a: Actor = Depends(user), c: Container = Depends(container)):
    c.teams.revoke_invitation(a.user, team_id, invitation_id)


@router.put("/{team_id}/members/{member_id}")
def set_role(team_id: str, member_id: str, body: RoleIn, a: Actor = Depends(user), c: Container = Depends(container)):
    c.teams.set_role(a.user, team_id, member_id, body.role)
    return c.teams.detail(a.user, team_id)


@router.delete("/{team_id}/members/{member_id}", status_code=204)
def remove_member(team_id: str, member_id: str, a: Actor = Depends(user), c: Container = Depends(container)):
    c.teams.remove_member(a.user, team_id, member_id)
