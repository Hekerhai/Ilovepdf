import secrets

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import SESSION_COOKIE, actor, client_ip_hash, container, set_session, user
from app.api.schemas import user_out
from app.container import Container
from app.domain.errors import FolioError
from app.services.actors import Actor, effective_plan

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "folio_oauth_state"


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    name: str | None = Field(None, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=256)


class MagicLinkIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(..., max_length=200)


def _signed_in(c: Container, response: Response, u) -> dict:
    set_session(response, c, c.auth.issue_token(u))
    with c.db.session() as session:
        return {"user": user_out(u, effective_plan(session, u))}


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"register:{client_ip_hash(request, c)}", limit=10, window_seconds=3600)
    return _signed_in(c, response, c.auth.register(body.email, body.password, body.name))


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"login:{client_ip_hash(request, c)}", limit=20, window_seconds=600)
    c.limiter.hit(f"login:{body.email.lower()}", limit=10, window_seconds=600)
    return _signed_in(c, response, c.auth.login(body.email, body.password))


@router.post("/magic-link", status_code=202)
def magic_link(body: MagicLinkIn, request: Request, c: Container = Depends(container)) -> dict:
    c.limiter.hit(f"magic:{client_ip_hash(request, c)}", limit=10, window_seconds=3600)
    c.limiter.hit(f"magic:{body.email.lower()}", limit=5, window_seconds=3600)
    c.auth.send_magic_link(body.email)
    return {"sent": True}


@router.post("/magic-link/verify")
def verify_magic_link(body: TokenIn, response: Response, c: Container = Depends(container)) -> dict:
    return _signed_in(c, response, c.auth.consume_magic_link(body.token))


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/logout-all", status_code=204)
def logout_all(response: Response, a: Actor = Depends(user), c: Container = Depends(container)) -> None:
    c.auth.sign_out_everywhere(a.user.id)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/google")
def google_start(c: Container = Depends(container)):
    state = secrets.token_urlsafe(24)
    redirect = RedirectResponse(c.auth.google_authorize_url(state))
    redirect.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax",
                        secure=c.settings.cookie_secure, path="/")  # fmt: skip
    return redirect


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", c: Container = Depends(container)):
    base = c.settings.public_url.rstrip("/")
    if not state or state != request.cookies.get(OAUTH_STATE_COOKIE):
        return RedirectResponse(f"{base}/login?error=state")
    try:
        u = c.auth.google_login(code)
    except FolioError:
        return RedirectResponse(f"{base}/login?error=google")
    redirect = RedirectResponse(f"{base}/account")
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    set_session(redirect, c, c.auth.issue_token(u))
    return redirect


@router.get("/session", summary="Who am I (works for guests too)")
def session_info(a: Actor = Depends(actor), c: Container = Depends(container)) -> dict:
    from app.api.schemas import plan_out

    if a.user is None:
        return {"user": None, "plan": plan_out(a.plan)}
    with c.db.session() as session:
        return {"user": user_out(a.user, a.plan), "plan": plan_out(a.plan),
                "tasks_today": c.quota.tasks_today(session, a)}  # fmt: skip
