from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import SESSION_COOKIE, container, user
from app.container import Container
from app.infra.db import User, as_utc
from app.services.actors import Actor

router = APIRouter(prefix="/me", tags=["account"])


class ProfileIn(BaseModel):
    name: str | None = Field(None, max_length=200)


class PasswordIn(BaseModel):
    current_password: str | None = Field(None, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


class ApiKeyIn(BaseModel):
    name: str = Field("API key", max_length=100)


@router.patch("")
def update_profile(body: ProfileIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    with c.db.session() as session:
        session.get(User, a.user.id).name = body.name
    return {"ok": True}


@router.post("/password", status_code=204)
def change_password(body: PasswordIn, response: Response, a: Actor = Depends(user), c: Container = Depends(container)):
    c.auth.change_password(a.user.id, body.current_password, body.new_password)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/export", summary="Download all data we hold about you (GDPR Art. 15/20)")
def export(a: Actor = Depends(user), c: Container = Depends(container)):
    return JSONResponse(
        c.privacy.export(a.user.id),
        headers={"Content-Disposition": 'attachment; filename="my-data.json"'},
    )


@router.delete("", status_code=204, summary="Delete your account and all data (GDPR Art. 17)")
def delete_account(response: Response, a: Actor = Depends(user), c: Container = Depends(container)) -> None:
    c.privacy.delete_account(a.user.id)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/api-keys")
def list_keys(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    with c.db.session() as session:
        usage = c.quota.api_usage(session, a)
    return {
        "usage": usage,
        "keys": [
            {
                "id": k.id,
                "name": k.name,
                "prefix": k.prefix,
                "created_at": as_utc(k.created_at).isoformat(),
                "last_used_at": as_utc(k.last_used_at).isoformat() if k.last_used_at else None,
            }
            for k in c.auth.list_api_keys(a.user.id)
        ],
    }


@router.post("/api-keys", status_code=201)
def create_key(body: ApiKeyIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    key, raw = c.auth.create_api_key(a.user.id, body.name)
    return {"id": key.id, "name": key.name, "prefix": key.prefix, "key": raw}


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_key(key_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> None:
    c.auth.revoke_api_key(a.user.id, key_id)


@router.get("/webhook-secret", summary="The secret that signs your API webhooks")
def webhook_secret(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"secret": c.auth.webhook_secret(a.user.id)}


@router.post("/webhook-secret/rotate", summary="Replace the webhook secret")
def rotate_webhook_secret(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {"secret": c.auth.webhook_secret(a.user.id, rotate=True)}
