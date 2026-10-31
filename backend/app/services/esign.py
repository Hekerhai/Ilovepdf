"""Request signatures: send a PDF to people, collect their signatures, and deliver a sealed copy with an audit trail.

Flow: the owner uploads a PDF, names the signers and places fields for each. Every signer gets a private link
(only its hash is stored). When the last one signs, the fields are drawn onto the document, an audit-trail page is
appended, and the result is sealed with a certificate signature so any later change is visible in every PDF reader.
"""

import base64
import hashlib
import io
import logging
import secrets
import tempfile
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Literal

import pikepdf
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from PIL import Image
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.errors import Forbidden, NotFound, QuotaExceeded, Unauthorized, ValidationFailed
from app.domain.ports import FileStorage, Mailer
from app.infra.db import (
    Database,
    SignatureEvent,
    SignatureRequest,
    SignatureTemplate,
    Signer,
    User,
    as_utc,
    utcnow,
)
from app.services.actors import Actor
from app.services.auth import normalize_email, sha256
from app.tools.editor import EditObject, _draw_object
from app.tools.overlay import stamp_pages
from app.tools.pdfio import open_pdf, save_pdf

log = logging.getLogger(__name__)

FieldKind = Literal["signature", "initials", "date", "name", "text", "checkbox"]
DONE = ("completed", "declined", "cancelled", "expired")
MAX_CODE_FAILURES = 10
MAX_TEMPLATES = 100
_hasher = PasswordHasher()


class SignerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    access_code: str | None = Field(
        None, min_length=4, max_length=64, description="Optional code you give the signer another way (phone, chat)"
    )


class FieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signer: int = Field(..., ge=0, description="Index into signers")
    type: FieldKind
    page: int = Field(..., ge=1)
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)
    height: float = Field(..., gt=0, le=1)
    required: bool = True
    label: str | None = Field(None, max_length=100)


class RequestIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    message: str | None = Field(None, max_length=2000)
    signers: list[SignerIn] = Field(..., min_length=1, max_length=20)
    fields: list[FieldIn] = Field(..., min_length=1, max_length=500)
    sequential: bool = Field(False, description="Ask signers one after another, in order")
    expires_in_days: int = Field(14, ge=1, le=90)
    stamp_id: bool = Field(True, description="Print the request ID in the margin of every page of the signed copy")

    @model_validator(mode="after")
    def _check(self):
        emails = [normalize_email(s.email) for s in self.signers]
        if len(set(emails)) != len(emails):
            raise ValueError("Each signer needs a different email address.")
        _check_fields(self.fields, [s.name for s in self.signers])
        return self


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    roles: list[str] = Field(..., min_length=1, max_length=20, description="Who signs, e.g. Tenant, Landlord")
    fields: list[FieldIn] = Field(..., min_length=1, max_length=500, description="'signer' indexes roles")
    message: str | None = Field(None, max_length=2000)
    sequential: bool = False

    @model_validator(mode="after")
    def _check(self):
        self.roles = [r.strip()[:100] for r in self.roles]
        if not all(self.roles):
            raise ValueError("Give every role a name.")
        if len({r.lower() for r in self.roles}) != len(self.roles):
            raise ValueError("Each role needs a different name.")
        _check_fields(self.fields, self.roles)
        return self


def _check_fields(fields: list[FieldIn], names: list[str]) -> None:
    if any(f.signer >= len(names) for f in fields):
        raise ValueError("A field belongs to a signer that doesn't exist.")
    for i, name in enumerate(names):
        if not any(f.signer == i and f.type in ("signature", "initials") for f in fields):
            raise ValueError(f"Add a signature field for {name}.")


class SignIn(BaseModel):
    values: dict[str, str | bool] = Field(default_factory=dict, description="Field index (as text) to value")
    signature: str | None = Field(None, description="Signature image as a data URL")
    initials: str | None = Field(None, description="Initials image as a data URL")
    consent: bool = Field(..., description="Agrees to sign electronically")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_size(data_url: str) -> tuple[int, int]:
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url)
        with Image.open(io.BytesIO(raw)) as im:
            return im.size
    except Exception:
        raise ValidationFailed("The signature image could not be read.") from None


class ESignService:
    def __init__(
        self,
        *,
        db: Database,
        storage: FileStorage,
        mailer: Mailer,
        public_url: str,
        brand_name: str,
        work_root: Path,
        retention_days: int = 30,
    ):
        self.db = db
        self.storage = storage
        self.mailer = mailer
        self.public_url = public_url.rstrip("/")
        self.brand = brand_name
        self.work_root = work_root
        self.retention = timedelta(days=retention_days)

    # ---- owner ------------------------------------------------------------------------------------------------

    def create(self, actor: Actor, pdf: Path, file_name: str, body: RequestIn, *, ip: str | None = None) -> dict:
        user = actor.user
        if user is None:
            raise Forbidden("Sign in to request signatures.")
        with self.db.session() as session:
            self._check_quota(session, actor)
        with open_pdf(pdf) as doc:
            pages = len(doc.pages)
        for f in body.fields:
            if f.page > pages:
                raise ValidationFailed(f"Page {f.page} doesn't exist; this PDF has {pages}.")

        tokens: list[str] = []
        with self.db.session() as session:
            req = SignatureRequest(
                owner_id=user.id,
                title=body.title.strip(),
                message=(body.message or "").strip() or None,
                file_name=file_name,
                sequential=body.sequential,
                stamp_id=body.stamp_id,
                original_sha256=_sha256_file(pdf),
                expires_at=utcnow() + timedelta(days=body.expires_in_days),
            )
            session.add(req)
            session.flush()
            self.storage.put(f"esign/{req.id}/original.pdf", pdf)
            for i, s in enumerate(body.signers):
                token = secrets.token_urlsafe(32)
                tokens.append(token)
                fields = [f.model_dump(exclude={"signer"}) for f in body.fields if f.signer == i]
                first = i == 0 or not body.sequential
                req.signers.append(
                    Signer(
                        position=i,
                        name=s.name.strip(),
                        email=normalize_email(s.email),
                        token_hash=sha256(token),
                        status="pending" if first else "waiting",
                        fields=fields,
                        access_code_hash=_hasher.hash(s.access_code.strip()) if s.access_code else None,
                    )
                )
            session.flush()
            self._event(req, None, "created", ip=ip, detail=f"Sent by {user.email}")
            for signer, token in zip(req.signers, tokens, strict=True):
                if signer.status == "pending":
                    self._invite(req, signer, token, sender=user)
            session.flush()
            return self._detail(req)

    def list_for(self, user: User) -> list[dict]:
        with self.db.session() as session:
            rows = session.scalars(
                select(SignatureRequest)
                .where(SignatureRequest.owner_id == user.id)
                .order_by(SignatureRequest.created_at.desc())
                .limit(200)
            ).all()
            for r in rows:
                self._expire_if_due(r)
            return [self._summary(r) for r in rows]

    def detail(self, user: User, request_id: str) -> dict:
        with self.db.session() as session:
            req = self._owned(session, user, request_id)
            self._expire_if_due(req)
            return self._detail(req)

    def remind(self, user: User, request_id: str) -> dict:
        with self.db.session() as session:
            req = self._owned(session, user, request_id)
            if req.status != "sent":
                raise ValidationFailed("Only requests that are still out for signature can be reminded.")
            reminded = 0
            for signer in req.signers:
                if signer.status in ("pending", "viewed"):
                    token = secrets.token_urlsafe(32)  # links are single-copy, so a reminder carries a fresh one
                    signer.token_hash = sha256(token)
                    self._invite(req, signer, token, sender=user, reminder=True)
                    self._event(req, signer, "reminded")
                    reminded += 1
            if not reminded:
                raise ValidationFailed("Nobody is waiting to sign right now.")
            return self._detail(req)

    def cancel(self, user: User, request_id: str) -> dict:
        with self.db.session() as session:
            req = self._owned(session, user, request_id)
            if req.status != "sent":
                raise ValidationFailed("This request is already finished.")
            req.status = "cancelled"
            self._event(req, None, "cancelled")
            for signer in req.signers:
                if signer.status in ("pending", "viewed"):
                    self.mailer.send(
                        to=signer.email,
                        subject=f"Cancelled: {req.title}",
                        text=f"{user.name or user.email} cancelled the request to sign “{req.title}”. "
                        "You don't need to do anything.",
                    )
            return self._detail(req)

    def delete(self, user: User, request_id: str) -> None:
        with self.db.session() as session:
            req = self._owned(session, user, request_id)
            self.storage.delete_prefix(f"esign/{req.id}/")
            session.delete(req)

    def owner_document(self, user: User, request_id: str) -> tuple[str, Iterator[bytes]]:
        with self.db.session() as session:
            req = self._owned(session, user, request_id)
            return self._document(req)

    # ---- signer -----------------------------------------------------------------------------------------------

    def view(
        self, token: str, *, code: str | None = None, ip: str | None = None, user_agent: str | None = None
    ) -> dict:
        with self.db.session() as session:
            signer = self._signer(session, token)
            req = signer.request
            needs_code = signer.access_code_hash is not None
            if needs_code and not code:
                # Say only enough for the signer to recognise the request; the rest waits for the code.
                return {
                    "needs_code": True,
                    "request": {"title": req.title, "sender": self._owner_name(session, req)},
                    "signer": {"name": signer.name},
                }
        if needs_code:
            self._check_code(token, code, ip=ip, user_agent=user_agent)
        with self.db.session() as session:
            signer = self._signer(session, token)
            req = signer.request
            self._expire_if_due(req)
            if signer.status == "pending" and req.status == "sent":
                signer.status = "viewed"
                self._event(req, signer, "viewed", ip=ip, user_agent=user_agent)
            return {
                "request": {
                    "title": req.title,
                    "message": req.message,
                    "file_name": req.file_name,
                    "status": req.status,
                    "sender": self._owner_name(session, req),
                    "expires_at": as_utc(req.expires_at).isoformat(),
                },
                "signer": {"name": signer.name, "email": signer.email, "status": signer.status},
                "needs_code": False,
                "fields": signer.fields,
                "can_sign": req.status == "sent" and signer.status in ("pending", "viewed"),
                "final_available": req.status == "completed" and not req.files_deleted,
            }

    def signer_document(self, token: str, *, code: str | None = None) -> tuple[str, Iterator[bytes]]:
        self._check_code(token, code)
        with self.db.session() as session:
            signer = self._signer(session, token)
            if signer.status == "waiting":
                raise Forbidden("It isn't your turn to sign yet. You'll get an email when it is.")
            return self._document(signer.request)

    def sign(
        self,
        token: str,
        body: SignIn,
        *,
        code: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        if not body.consent:
            raise ValidationFailed("Please agree to sign electronically.")
        self._check_code(token, code, ip=ip, user_agent=user_agent)
        with self.db.session() as session:
            signer = self._signer(session, token)
            req = signer.request
            self._expire_if_due(req)
            if req.status != "sent" or signer.status not in ("pending", "viewed"):
                raise ValidationFailed("This document can't be signed any more.")
            values: dict[str, str | bool] = {}
            for i, field in enumerate(signer.fields):
                kind, value = field["type"], body.values.get(str(i))
                if kind == "signature":
                    if not body.signature:
                        raise ValidationFailed("Add your signature.")
                    _image_size(body.signature)
                elif kind == "initials":
                    if not (body.initials or body.signature):
                        raise ValidationFailed("Add your initials.")
                elif kind in ("text",):
                    if field.get("required", True) and not str(value or "").strip():
                        raise ValidationFailed(f"Fill in “{field.get('label') or 'the text field'}”.")
                    values[str(i)] = str(value or "")[:500]
                elif kind == "checkbox":
                    if field.get("required", True) and value is not True:
                        raise ValidationFailed(f"Tick “{field.get('label') or 'the checkbox'}”.")
                    values[str(i)] = value is True
            signer.values = {"fields": values, "signature": body.signature, "initials": body.initials or body.signature}
            signer.status = "signed"
            signer.signed_at = utcnow()
            self._event(req, signer, "signed", ip=ip, user_agent=user_agent)
            session.flush()

            remaining = [s for s in req.signers if s.status != "signed"]
            if remaining and req.sequential:
                nxt = remaining[0]
                if nxt.status == "waiting":
                    token_next = secrets.token_urlsafe(32)
                    nxt.token_hash = sha256(token_next)
                    nxt.status = "pending"
                    self._invite(req, nxt, token_next, sender=session.get(User, req.owner_id))
            if not remaining:
                self._finalize(session, req)
            return {"status": signer.status, "request_status": req.status}

    def decline(
        self,
        token: str,
        reason: str | None,
        *,
        code: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        self._check_code(token, code, ip=ip, user_agent=user_agent)
        with self.db.session() as session:
            signer = self._signer(session, token)
            req = signer.request
            if req.status != "sent" or signer.status not in ("pending", "viewed"):
                raise ValidationFailed("This document can't be declined any more.")
            signer.status = "declined"
            signer.decline_reason = (reason or "").strip()[:1000] or None
            req.status = "declined"
            self._event(req, signer, "declined", ip=ip, user_agent=user_agent, detail=signer.decline_reason)
            owner = session.get(User, req.owner_id)
            if owner:
                why = f"\n\nTheir reason: {signer.decline_reason}" if signer.decline_reason else ""
                self.mailer.send(
                    to=owner.email,
                    subject=f"Declined: {req.title}",
                    text=f"{signer.name} ({signer.email}) declined to sign “{req.title}”.{why}\n\n"
                    f"{self.public_url}/esign/{req.id}",
                )
            return {"status": "declined"}

    # ---- templates --------------------------------------------------------------------------------------------

    def templates(self, user: User) -> list[dict]:
        with self.db.session() as session:
            rows = session.scalars(
                select(SignatureTemplate)
                .where(SignatureTemplate.owner_id == user.id)
                .order_by(SignatureTemplate.updated_at.desc())
            ).all()
            return [self._template_out(t) for t in rows]

    def save_template(self, actor: Actor, pdf: Path, file_name: str, body: TemplateIn) -> dict:
        user = actor.user
        if user is None:
            raise Forbidden("Sign in to save templates.")
        if actor.plan.esign_requests_per_month == 0:
            raise QuotaExceeded("Your plan doesn't include signature requests.", code="esign_limit")
        with open_pdf(pdf) as doc:
            pages = len(doc.pages)
        if any(f.page > pages for f in body.fields):
            raise ValidationFailed(f"A field is on a page this PDF doesn't have; it has {pages}.")
        with self.db.session() as session:
            count = session.scalar(
                select(func.count()).select_from(SignatureTemplate).where(SignatureTemplate.owner_id == user.id)
            )
            if count >= MAX_TEMPLATES:
                raise ValidationFailed(f"You can keep up to {MAX_TEMPLATES} templates. Delete one first.")
            tpl = SignatureTemplate(
                owner_id=user.id,
                name=body.name.strip(),
                file_name=file_name,
                roles=body.roles,
                fields=[f.model_dump() for f in body.fields],
                message=(body.message or "").strip() or None,
                sequential=body.sequential,
            )
            session.add(tpl)
            session.flush()
            self.storage.put(self._template_key(tpl), pdf)
            return self._template_out(tpl)

    def template(self, user: User, template_id: str) -> dict:
        with self.db.session() as session:
            tpl = self._owned_template(session, user, template_id)
            return {**self._template_out(tpl), "fields": tpl.fields, "message": tpl.message}

    def template_document(self, user: User, template_id: str) -> tuple[str, Iterator[bytes]]:
        with self.db.session() as session:
            tpl = self._owned_template(session, user, template_id)
            return tpl.file_name, self.storage.open_stream(self._template_key(tpl))

    def rename_template(self, user: User, template_id: str, name: str) -> dict:
        name = name.strip()[:200]
        if not name:
            raise ValidationFailed("Give the template a name.")
        with self.db.session() as session:
            tpl = self._owned_template(session, user, template_id)
            tpl.name, tpl.updated_at = name, utcnow()
            return self._template_out(tpl)

    def delete_template(self, user: User, template_id: str) -> None:
        with self.db.session() as session:
            tpl = self._owned_template(session, user, template_id)
            self.storage.delete_prefix(self._template_key(tpl))
            session.delete(tpl)

    def delete_templates_for(self, user_id: str) -> None:
        self.storage.delete_prefix(f"esign-templates/{user_id}/")
        with self.db.session() as session:
            for tpl in session.scalars(select(SignatureTemplate).where(SignatureTemplate.owner_id == user_id)):
                session.delete(tpl)

    @staticmethod
    def _owned_template(session: Session, user: User, template_id: str) -> SignatureTemplate:
        tpl = session.get(SignatureTemplate, template_id)
        if tpl is None or tpl.owner_id != user.id:
            raise NotFound("Template not found.")
        return tpl

    @staticmethod
    def _template_key(tpl: SignatureTemplate) -> str:
        return f"esign-templates/{tpl.owner_id}/{tpl.id}.pdf"

    @staticmethod
    def _template_out(tpl: SignatureTemplate) -> dict:
        return {
            "id": tpl.id,
            "name": tpl.name,
            "file_name": tpl.file_name,
            "roles": tpl.roles,
            "sequential": tpl.sequential,
            "field_count": len(tpl.fields),
            "created_at": as_utc(tpl.created_at).isoformat(),
            "updated_at": as_utc(tpl.updated_at).isoformat(),
        }

    # ---- housekeeping -----------------------------------------------------------------------------------------

    def purge(self) -> int:
        """Delete documents of finished requests once the retention period has passed."""
        cutoff = utcnow() - self.retention
        removed = 0
        with self.db.session() as session:
            rows = session.scalars(
                select(SignatureRequest).where(
                    SignatureRequest.files_deleted.is_(False),
                    func.coalesce(SignatureRequest.completed_at, SignatureRequest.expires_at) < cutoff,
                )
            ).all()
            for req in rows:
                self.storage.delete_prefix(f"esign/{req.id}/")
                req.files_deleted = True
                removed += 1
            for req in session.scalars(
                select(SignatureRequest).where(
                    SignatureRequest.status == "sent", SignatureRequest.expires_at < utcnow()
                )
            ):
                self._expire_if_due(req)
        return removed

    # ---- internals --------------------------------------------------------------------------------------------

    def _check_quota(self, session: Session, actor: Actor) -> None:
        limit = actor.plan.esign_requests_per_month
        if limit is None:
            return
        since = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = session.scalar(
            select(func.count())
            .select_from(SignatureRequest)
            .where(SignatureRequest.owner_id == actor.user.id, SignatureRequest.created_at >= since)
        )
        if used >= limit:
            raise QuotaExceeded(
                f"Your plan includes {limit} signature requests a month. Upgrade to Pro for unlimited requests.",
                code="esign_limit",
            )

    def _owned(self, session: Session, user: User, request_id: str) -> SignatureRequest:
        req = session.get(SignatureRequest, request_id)
        if req is None or req.owner_id != user.id:
            raise NotFound("Signature request not found.")
        return req

    def _signer(self, session: Session, token: str) -> Signer:
        signer = session.scalar(select(Signer).where(Signer.token_hash == sha256(token)))
        if signer is None:
            raise NotFound("This signing link isn't valid. Ask the sender for a new one.")
        return signer

    def _check_code(self, token: str, code: str | None, *, ip=None, user_agent=None) -> None:
        """Signers with an access code must give it on every call, not just the first.

        Runs in its own session so a wrong guess is counted even though the request then fails.
        """
        wrong = False
        with self.db.session() as session:
            signer = self._signer(session, token)
            if not signer.access_code_hash:
                return
            if signer.code_failures >= MAX_CODE_FAILURES:
                raise Forbidden("Too many wrong codes. Ask the sender to send the request again.")
            try:
                _hasher.verify(signer.access_code_hash, (code or "").strip())
            except VerificationError:
                wrong = True
                signer.code_failures += 1
                self._event(signer.request, signer, "code_failed", ip=ip, user_agent=user_agent)
        if wrong:
            raise Unauthorized("That access code isn't right.", code="bad_code")

    def _owner_name(self, session: Session, req: SignatureRequest) -> str:
        owner = session.get(User, req.owner_id)
        return (owner.name or owner.email) if owner else self.brand

    def _expire_if_due(self, req: SignatureRequest) -> None:
        if req.status == "sent" and as_utc(req.expires_at) < utcnow():
            req.status = "expired"
            self._event(req, None, "expired")

    def _document(self, req: SignatureRequest) -> tuple[str, Iterator[bytes]]:
        if req.files_deleted:
            raise NotFound("This document has been deleted.")
        if req.status == "completed":
            return f"{Path(req.file_name).stem}-signed.pdf", self.storage.open_stream(f"esign/{req.id}/final.pdf")
        return req.file_name, self.storage.open_stream(f"esign/{req.id}/original.pdf")

    def _event(self, req, signer, kind: str, *, ip=None, user_agent=None, detail=None) -> None:
        req.events.append(
            SignatureEvent(
                signer_id=signer.id if signer else None,
                kind=kind,
                ip=ip,
                user_agent=(user_agent or "")[:300] or None,
                detail=detail,
                at=utcnow(),
            )
        )

    def _invite(self, req, signer, token: str, *, sender: User | None, reminder: bool = False) -> None:
        who = (sender.name or sender.email) if sender else self.brand
        note = f"\n\nMessage from {who}:\n{req.message}" if req.message else ""
        if signer.access_code_hash:
            note += f"\n\nYou'll need the access code {who} gave you. It isn't in this email."
        self.mailer.send(
            to=signer.email,
            subject=f"{'Reminder: ' if reminder else ''}{who} asked you to sign “{req.title}”",
            text=(
                f"Hi {signer.name},\n\n{who} sent you “{req.title}” to sign with {self.brand}.{note}\n\n"
                f"Review and sign: {self.public_url}/sign/{token}\n\n"
                f"This link is personal to you. It expires on {as_utc(req.expires_at):%d %B %Y}."
            ),
        )

    def _summary(self, req: SignatureRequest) -> dict:
        return {
            "id": req.id,
            "title": req.title,
            "file_name": req.file_name,
            "status": req.status,
            "created_at": as_utc(req.created_at).isoformat(),
            "completed_at": as_utc(req.completed_at).isoformat() if req.completed_at else None,
            "expires_at": as_utc(req.expires_at).isoformat(),
            "signers": [{"name": s.name, "email": s.email, "status": s.status} for s in req.signers],
        }

    def _detail(self, req: SignatureRequest) -> dict:
        names = {s.id: s.name for s in req.signers}
        return {
            **self._summary(req),
            "message": req.message,
            "sequential": req.sequential,
            "stamp_id": req.stamp_id,
            "original_sha256": req.original_sha256,
            "final_sha256": req.final_sha256,
            "files_deleted": req.files_deleted,
            "signers": [
                {
                    "name": s.name,
                    "email": s.email,
                    "status": s.status,
                    "signed_at": as_utc(s.signed_at).isoformat() if s.signed_at else None,
                    "decline_reason": s.decline_reason,
                    "fields": len(s.fields),
                    "has_code": s.access_code_hash is not None,
                }
                for s in req.signers
            ],
            "events": [
                {
                    "kind": e.kind,
                    "at": as_utc(e.at).isoformat(),
                    "who": names.get(e.signer_id) if e.signer_id else None,
                    "ip": e.ip,
                    "detail": e.detail,
                }
                for e in req.events
            ],
        }

    # ---- the signed copy ---------------------------------------------------------------------------------------

    def _finalize(self, session: Session, req: SignatureRequest) -> None:
        work = Path(tempfile.mkdtemp(prefix="esign-", dir=self.work_root if self.work_root.exists() else None))
        original = self.storage.get(f"esign/{req.id}/original.pdf", work / "original.pdf")
        stamped = work / "stamped.pdf"
        with open_pdf(original) as pdf:
            self._draw_fields(pdf, req)
            completed = utcnow()
            audit = self._audit_pdf(session, req, completed, work / "audit.pdf")
            with pikepdf.open(audit) as trail:
                pdf.pages.extend(trail.pages)
            pdf.docinfo["/Title"] = req.title
            save_pdf(pdf, stamped)
        final = work / "final.pdf"
        self._seal(stamped, final, req)
        self.storage.put(f"esign/{req.id}/final.pdf", final)
        req.final_sha256 = _sha256_file(final)
        req.status = "completed"
        req.completed_at = completed
        self._event(req, None, "completed", detail=f"SHA-256 {req.final_sha256}")
        owner = session.get(User, req.owner_id)
        recipients = [owner.email] if owner else []
        recipients += [s.email for s in req.signers]
        for email in recipients:
            link = f"{self.public_url}/esign/{req.id}" if owner and email == owner.email else None
            self.mailer.send(
                to=email,
                subject=f"Completed: {req.title}",
                text=(
                    f"Everyone has signed “{req.title}”.\n\n"
                    + (
                        f"Download the signed copy: {link}\n\n"
                        if link
                        else "Open your signing link to download the signed copy.\n\n"
                    )
                    + f"The copy is sealed: any change after signing shows in your PDF reader. "
                    f"It is kept for {self.retention.days} days."
                ),
            )

    def _draw_fields(self, pdf: pikepdf.Pdf, req: SignatureRequest) -> None:
        by_page: dict[int, list[EditObject]] = {}
        for signer in req.signers:
            stored = signer.values or {}
            for i, f in enumerate(signer.fields):
                obj = self._field_object(f, stored, signer, str(i))
                if obj is not None:
                    by_page.setdefault(f["page"] - 1, []).append(obj)

        stamp = f"{self.brand} eSign · ID {req.id}" if req.stamp_id else None

        def draw(c, index: int, w: float, h: float) -> None:
            for obj in by_page.get(index, []):
                _draw_object(c, self._fit(obj, w, h), w, h)
            if stamp:
                # Small and grey in the bottom margin, so every page can be matched to its audit trail.
                c.saveState()
                c.setFont("Helvetica", 6.5)
                c.setFillGray(0.45)
                c.drawString(14, 8, stamp)
                c.restoreState()

        stamp_pages(pdf, draw, None if stamp else set(by_page))

    @staticmethod
    def _fit(obj: EditObject, w: float, h: float) -> EditObject:
        """Signatures keep their shape inside the box (left aligned, centred vertically); text scales to the box."""
        if obj.type == "image":
            iw, ih = _image_size(obj.image or "")
            bw, bh = obj.width * w, obj.height * h
            scale = min(bw / iw, bh / ih)
            width, height = iw * scale / w, ih * scale / h
            return obj.model_copy(update={"width": width, "height": height, "y": obj.y + (obj.height - height) / 2})
        return obj.model_copy(update={"font_size": max(6.0, min(14.0, obj.height * h * 0.7))})

    def _field_object(self, f: dict, stored: dict, signer: Signer, key: str) -> EditObject | None:
        kind = f["type"]
        box = {"page": f["page"], "x": f["x"], "y": f["y"], "width": f["width"], "height": f["height"]}
        if kind in ("signature", "initials"):
            image = stored.get(kind) or stored.get("signature")
            return EditObject(type="image", image=image, **box) if image else None
        values = stored.get("fields") or {}
        text = {
            "date": (signer.signed_at or utcnow()).strftime("%d %b %Y"),
            "name": signer.name,
            "text": str(values.get(key, "")),
            "checkbox": "X" if values.get(key) is True else "",
        }[kind]
        return EditObject(type="text", text=text, **box) if text else None

    def _audit_pdf(self, session: Session, req: SignatureRequest, completed, out: Path) -> Path:
        styles = getSampleStyleSheet()
        small = styles["BodyText"].clone("small", fontSize=8.5, leading=11)
        story = [
            Paragraph(f"{self.brand} signature certificate", styles["Title"]),
            Paragraph(f"<b>{req.title}</b> · {req.file_name}", styles["BodyText"]),
            Spacer(1, 4 * mm),
            Table(
                [
                    ["Request ID", req.id],
                    ["Sent by", self._owner_name(session, req)],
                    ["Sent", f"{as_utc(req.created_at):%d %b %Y %H:%M UTC}"],
                    ["Completed", f"{as_utc(completed):%d %b %Y %H:%M UTC}"],
                    ["Original document SHA-256", Paragraph(req.original_sha256, small)],
                ],
                colWidths=[45 * mm, 125 * mm],
                style=TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (0, -1), colors.grey)]),
            ),
            Spacer(1, 6 * mm),
            Paragraph("Signers", styles["Heading2"]),
        ]
        signed_ip = {e.signer_id: e.ip for e in req.events if e.kind == "signed"}
        rows = [["Name", "Email", "Signed (UTC)", "IP address"]]
        for s in req.signers:
            rows.append(
                [
                    s.name,
                    s.email,
                    f"{as_utc(s.signed_at):%d %b %Y %H:%M}" if s.signed_at else "–",
                    signed_ip.get(s.id) or "–",
                ]
            )
        story.append(self._table(rows, [45 * mm, 60 * mm, 35 * mm, 30 * mm]))
        story += [Spacer(1, 6 * mm), Paragraph("History", styles["Heading2"])]
        names = {s.id: s.name for s in req.signers}
        history = [["When (UTC)", "What", "Who", "IP address"]]
        for e in req.events:
            history.append([f"{as_utc(e.at):%d %b %Y %H:%M:%S}", e.kind, names.get(e.signer_id, "–"), e.ip or "–"])
        history.append([f"{as_utc(completed):%d %b %Y %H:%M:%S}", "completed", "–", "–"])
        story.append(self._table(history, [40 * mm, 30 * mm, 60 * mm, 40 * mm]))
        story += [
            Spacer(1, 6 * mm),
            Paragraph(
                "Each signer opened a personal link sent to their email address, agreed to sign electronically and "
                "adopted the signature shown in the document. This copy is sealed with a digital signature: any change "
                "made after it was issued is reported by PDF readers.",
                small,
            ),
        ]
        SimpleDocTemplate(str(out), pagesize=A4, title="Signature certificate").build(story)
        return out

    @staticmethod
    def _table(rows, widths) -> Table:
        return Table(
            rows,
            colWidths=widths,
            repeatRows=1,
            style=TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ]
            ),
        )

    def _seal(self, source: Path, out: Path, req: SignatureRequest) -> None:
        """Certify the document with the platform's own certificate (created once, kept in storage)."""
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import fields, signers

        from app.tools.signatures import self_signed_pkcs12

        key = "esign/_platform/seal.p12"
        cert_path = out.parent / "seal.p12"
        try:
            self.storage.get(key, cert_path)
        except NotFound:
            cert_path.write_bytes(self_signed_pkcs12(f"{self.brand} eSign", None, days=3650))
            self.storage.put(key, cert_path)
        signer = signers.SimpleSigner.load_pkcs12_data(cert_path.read_bytes(), other_certs=[])
        meta = signers.PdfSignatureMetadata(
            field_name="Seal", reason=f"Signed with {self.brand} eSign", certify=True, md_algorithm="sha256"
        )
        with source.open("rb") as f:
            writer = IncrementalPdfFileWriter(f, strict=False)
            buf = signers.PdfSigner(meta, signer, new_field_spec=fields.SigFieldSpec("Seal")).sign_pdf(
                writer, output=io.BytesIO()
            )
        out.write_bytes(buf.getvalue())
