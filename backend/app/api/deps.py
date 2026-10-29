"""Request-scoped dependencies: the container, the acting user/guest, and upload spooling."""

import hashlib
import secrets
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, Request, Response, UploadFile

from app.container import Container, get_container
from app.domain.errors import QuotaExceeded, Unauthorized
from app.plans import MB
from app.services.actors import Actor, guest_actor, user_actor
from app.services.auth import API_KEY_PREFIX
from app.services.jobs import Upload

SESSION_COOKIE = "folio_session"
GUEST_COOKIE = "folio_guest"


def container() -> Container:
    return get_container()


def client_ip_hash(request: Request, c: Container) -> str:
    # Behind the bundled reverse proxy the client IP is in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    return hashlib.sha256(f"{c.settings.secret_key}:{ip}".encode()).hexdigest()


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("x-api-key")


def actor(request: Request, response: Response, c: Container = Depends(container)) -> Actor:
    ip_hash = client_ip_hash(request, c)
    token = _bearer(request)
    if token and token.startswith(API_KEY_PREFIX):
        user, key = c.auth.authenticate_api_key(token)
        with c.db.session() as session:
            return user_actor(session, user, ip_hash=ip_hash, api_key=key)
    token = token or request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            user = c.auth.user_from_token(token)
        except Unauthorized:
            response.delete_cookie(SESSION_COOKIE, path="/")
        else:
            with c.db.session() as session:
                return user_actor(session, user, ip_hash=ip_hash)
    guest_id = request.cookies.get(GUEST_COOKIE)
    if not guest_id:
        guest_id = secrets.token_urlsafe(24)
        response.set_cookie(
            GUEST_COOKIE, guest_id, max_age=60 * 60 * 24 * 365, httponly=True,
            samesite="lax", secure=c.settings.cookie_secure, path="/",
        )  # fmt: skip
    return guest_actor(guest_id, ip_hash)


def user(a: Actor = Depends(actor)) -> Actor:
    if a.user is None:
        raise Unauthorized("Sign in to continue.")
    return a


def api_user(a: Actor = Depends(actor)) -> Actor:
    if a.api_key is None:
        raise Unauthorized("Send your API key as 'Authorization: Bearer fk_live_...'.")
    return a


def set_session(response: Response, c: Container, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=c.settings.access_token_minutes * 60, httponly=True,
        samesite="lax", secure=c.settings.cookie_secure, path="/",
    )  # fmt: skip


class SpooledUploads:
    """Copies uploads to a private temp dir, enforcing the plan's size limit while streaming."""

    def __init__(self, limit_bytes: int):
        self.limit = limit_bytes
        self.dir = Path(tempfile.mkdtemp(prefix="upload-"))

    async def add(self, files: list[UploadFile]) -> list[Upload]:
        uploads = []
        for index, file in enumerate(files):
            target = self.dir / f"{index:03d}"
            size = 0
            with target.open("wb") as out:
                while chunk := await file.read(MB):
                    size += len(chunk)
                    if size > self.limit:
                        raise QuotaExceeded(
                            f"'{file.filename}' is larger than your plan allows ({self.limit // MB} MB).",
                            code="file_too_large",
                        )
                    out.write(chunk)
            uploads.append(Upload(path=target, name=file.filename or f"file-{index}", size=size))
        return uploads

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def spooler(a: Actor = Depends(actor)) -> Iterator[SpooledUploads]:
    spool = SpooledUploads(a.plan.max_file_bytes)
    try:
        yield spool
    finally:
        spool.cleanup()
