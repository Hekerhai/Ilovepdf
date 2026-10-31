"""My documents and share links.

Task files are deleted automatically; a document is a file the user explicitly chose to keep. A share link gives
anyone holding it access to one document, optionally behind a password, an expiry date or a download limit.
"""

import mimetypes
import secrets
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.errors import Forbidden, NotFound, QuotaExceeded, Unauthorized, ValidationFailed
from app.domain.ports import FileStorage, Mailer
from app.infra.db import Database, Document, ShareLink, User, as_utc, utcnow
from app.plans import MB, Plan
from app.services.actors import Actor
from app.services.jobs import JobService, safe_name

GRANT_MINUTES = 30


def _content_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


class DocumentService:
    def __init__(
        self,
        *,
        db: Database,
        storage: FileStorage,
        mailer: Mailer,
        jobs: JobService,
        secret_key: str,
        public_url: str,
        brand_name: str,
    ):
        self.db = db
        self.storage = storage
        self.mailer = mailer
        self.jobs = jobs
        self.secret = secret_key
        self.public_url = public_url.rstrip("/")
        self.brand = brand_name
        self.hasher = PasswordHasher()

    # ---- documents --------------------------------------------------------------------------------------------

    def usage(self, actor: Actor) -> dict:
        with self.db.session() as session:
            used = self._used(session, actor.user.id)
        return {"used_bytes": used, "limit_bytes": actor.plan.storage_bytes}

    def add(self, actor: Actor, path: Path, name: str) -> dict:
        user = self._user(actor)
        size = path.stat().st_size
        name = safe_name(name)
        with self.db.session() as session:
            self._check_space(session, user.id, actor.plan, size)
            doc = Document(owner_id=user.id, name=name, size=size, content_type=_content_type(name))
            session.add(doc)
            session.flush()
            self.storage.put(self._key(doc), path)
            return self._out(doc)

    def add_from_job(self, actor: Actor, job_id: str, work_dir: Path) -> dict:
        job, stream = self.jobs.open_output(actor, job_id)
        target = work_dir / safe_name(job.output_name)
        with target.open("wb") as out:
            for chunk in stream:
                out.write(chunk)
        return self.add(actor, target, job.output_name)

    def all(self, actor: Actor) -> list[dict]:
        user = self._user(actor)
        with self.db.session() as session:
            docs = session.scalars(
                select(Document).where(Document.owner_id == user.id).order_by(Document.updated_at.desc()).limit(1000)
            ).all()
            return [self._out(d) for d in docs]

    def open(self, actor: Actor, doc_id: str) -> tuple[dict, Iterator[bytes]]:
        with self.db.session() as session:
            doc = self._owned(session, actor, doc_id)
            return self._out(doc), self.storage.open_stream(self._key(doc))

    def rename(self, actor: Actor, doc_id: str, name: str) -> dict:
        name = safe_name(name.strip())
        if not name:
            raise ValidationFailed("Give the document a name.")
        with self.db.session() as session:
            doc = self._owned(session, actor, doc_id)
            if Path(name).suffix.lower() != Path(doc.name).suffix.lower():
                name += Path(doc.name).suffix  # keep the extension, so the file still opens
            doc.name, doc.updated_at = name, utcnow()
            return self._out(doc)

    def delete(self, actor: Actor, doc_id: str) -> None:
        with self.db.session() as session:
            doc = self._owned(session, actor, doc_id)
            self.storage.delete_prefix(f"docs/{doc.owner_id}/{doc.id}")
            session.delete(doc)

    def delete_all_for(self, user_id: str) -> None:
        self.storage.delete_prefix(f"docs/{user_id}/")
        with self.db.session() as session:
            for doc in session.scalars(select(Document).where(Document.owner_id == user_id)):
                session.delete(doc)

    # ---- sharing ----------------------------------------------------------------------------------------------

    def share(
        self,
        actor: Actor,
        doc_id: str,
        *,
        expires_in_days: int | None = None,
        password: str | None = None,
        max_downloads: int | None = None,
        allow_download: bool = True,
        sent_to: str | None = None,
    ) -> dict:
        with self.db.session() as session:
            doc = self._owned(session, actor, doc_id)
            if session.scalar(select(func.count()).select_from(ShareLink).where(ShareLink.document_id == doc.id)) >= 50:
                raise ValidationFailed("A document can have at most 50 share links. Remove some first.")
            link = ShareLink(
                token=secrets.token_urlsafe(24),
                password_hash=self.hasher.hash(password) if password else None,
                allow_download=allow_download,
                expires_at=utcnow() + timedelta(days=expires_in_days) if expires_in_days else None,
                max_downloads=max_downloads,
                sent_to=sent_to,
            )
            doc.shares.append(link)
            session.flush()
            return self._share_out(link)

    def send(self, actor: Actor, doc_id: str, *, email: str, message: str | None, expires_in_days: int = 7) -> dict:
        user = self._user(actor)
        link = self.share(actor, doc_id, expires_in_days=expires_in_days, sent_to=email)
        with self.db.session() as session:
            name = session.get(Document, doc_id).name
        who = user.name or user.email
        note = f"\n\n{who} wrote:\n{message.strip()}" if message and message.strip() else ""
        self.mailer.send(
            to=email,
            subject=f"{who} sent you “{name}”",
            text=f"{who} shared “{name}” with you using {self.brand}.{note}\n\nOpen it: {link['url']}\n\n"
            f"The link works for {expires_in_days} days.",
        )
        return link

    def shares(self, actor: Actor, doc_id: str) -> list[dict]:
        with self.db.session() as session:
            doc = self._owned(session, actor, doc_id)
            return [self._share_out(s) for s in doc.shares if s.revoked_at is None]

    def revoke(self, actor: Actor, doc_id: str, share_id: str) -> None:
        with self.db.session() as session:
            doc = self._owned(session, actor, doc_id)
            link = next((s for s in doc.shares if s.id == share_id), None)
            if link is None:
                raise NotFound("Share link not found.")
            link.revoked_at = utcnow()

    # ---- public side of a share link --------------------------------------------------------------------------

    def shared(self, token: str) -> dict:
        with self.db.session() as session:
            link = self._link(session, token)
            link.views += 1
            owner = session.get(User, link.document.owner_id)
            return {
                "name": link.document.name,
                "size": link.document.size,
                "content_type": link.document.content_type,
                "shared_by": (owner.name or owner.email.split("@")[0]) if owner else self.brand,
                "needs_password": link.password_hash is not None,
                "allow_download": link.allow_download,
                "expires_at": as_utc(link.expires_at).isoformat() if link.expires_at else None,
                "grant": None if link.password_hash else self._grant(link),
            }

    def unlock(self, token: str, password: str) -> str:
        with self.db.session() as session:
            link = self._link(session, token)
            if link.password_hash is None:
                return self._grant(link)
            try:
                self.hasher.verify(link.password_hash, password)
            except VerificationError:
                raise Unauthorized("That password isn't right.") from None
            return self._grant(link)

    def shared_file(self, token: str, grant: str, *, download: bool) -> tuple[dict, Iterator[bytes]]:
        with self.db.session() as session:
            link = self._link(session, token)
            try:
                claims = jwt.decode(grant, self.secret, algorithms=["HS256"], audience="share")
            except jwt.PyJWTError:
                raise Unauthorized("This link has timed out. Open it again.") from None
            if claims.get("sub") != link.id:
                raise Unauthorized("This link has timed out. Open it again.")
            if download:
                if not link.allow_download:
                    raise Forbidden("The owner turned off downloads for this link.")
                if link.max_downloads is not None and link.downloads >= link.max_downloads:
                    raise Forbidden("This link has reached its download limit.")
                link.downloads += 1
            return self._out(link.document), self.storage.open_stream(self._key(link.document))

    # ---- internals --------------------------------------------------------------------------------------------

    @staticmethod
    def _user(actor: Actor) -> User:
        if actor.user is None:
            raise Unauthorized("Sign in to keep documents in your account.")
        return actor.user

    @staticmethod
    def _used(session: Session, user_id: str) -> int:
        return session.scalar(select(func.coalesce(func.sum(Document.size), 0)).where(Document.owner_id == user_id))

    def _check_space(self, session: Session, user_id: str, plan: Plan, size: int) -> None:
        if plan.storage_bytes <= 0:
            raise QuotaExceeded("Create a free account to keep documents.", code="storage_full")
        if self._used(session, user_id) + size > plan.storage_bytes:
            limit = plan.storage_bytes // MB
            shown = f"{limit // 1024} GB" if limit >= 1024 else f"{limit} MB"
            raise QuotaExceeded(
                f"Your documents are using all {shown} of your storage. Delete some, or upgrade for more.",
                code="storage_full",
            )

    def _owned(self, session: Session, actor: Actor, doc_id: str) -> Document:
        user = self._user(actor)
        doc = session.get(Document, doc_id)
        if doc is None or doc.owner_id != user.id:
            raise NotFound("Document not found.")
        return doc

    def _link(self, session: Session, token: str) -> ShareLink:
        link = session.scalar(select(ShareLink).where(ShareLink.token == token))
        if link is None or link.revoked_at is not None:
            raise NotFound("This link doesn't exist or was turned off.")
        if link.expires_at and as_utc(link.expires_at) < utcnow():
            raise NotFound("This link has expired.")
        return link

    def _grant(self, link: ShareLink) -> str:
        exp = utcnow() + timedelta(minutes=GRANT_MINUTES)
        return jwt.encode({"sub": link.id, "aud": "share", "exp": exp}, self.secret, algorithm="HS256")

    @staticmethod
    def _key(doc: Document) -> str:
        return f"docs/{doc.owner_id}/{doc.id}"

    @staticmethod
    def _out(doc: Document) -> dict:
        return {
            "id": doc.id,
            "name": doc.name,
            "size": doc.size,
            "content_type": doc.content_type,
            "created_at": as_utc(doc.created_at).isoformat(),
            "updated_at": as_utc(doc.updated_at).isoformat(),
        }

    def _share_out(self, link: ShareLink) -> dict:
        return {
            "id": link.id,
            "url": f"{self.public_url}/s/{link.token}",
            "embed": f'<iframe src="{self.public_url}/s/{link.token}?embed=1" width="100%" height="600" '
            f'style="border:0" title="Shared PDF"></iframe>',
            "has_password": link.password_hash is not None,
            "allow_download": link.allow_download,
            "expires_at": as_utc(link.expires_at).isoformat() if link.expires_at else None,
            "max_downloads": link.max_downloads,
            "downloads": link.downloads,
            "views": link.views,
            "sent_to": link.sent_to,
            "created_at": as_utc(link.created_at).isoformat(),
        }
