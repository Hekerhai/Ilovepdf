"""Database models (SQLAlchemy 2.0). Portable across PostgreSQL (production) and SQLite (tests)."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_id: Mapped[str] = mapped_column(String(32), default="free")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Bumped on logout-everywhere / password change, invalidating outstanding session tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    # Signs outgoing API webhooks; created the first time the user asks for it.
    webhook_secret: Mapped[str | None] = mapped_column(String(64))

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    plan_id: Mapped[str] = mapped_column(String(32), default="free")
    seats: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # owner | admin | member
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    team: Mapped[Team] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(16), default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]


class LoginToken(Base):
    """Single-use magic-link tokens (only the hash is stored)."""

    __tablename__ = "login_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_type: Mapped[str] = mapped_column(String(8))  # user | team
    owner_id: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(16))  # stripe | razorpay
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(255))
    plan_id: Mapped[str] = mapped_column(String(32))
    seats: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | cancelled
    current_period_end: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    steps: Mapped[list] = mapped_column(JSON)  # [{"tool": "...", "options": {...}}]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    guest_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    api_key_id: Mapped[str | None] = mapped_column(String(32), index=True)
    steps: Mapped[list] = mapped_column(JSON)  # [{"tool": "...", "options": {...}}]
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    input_names: Mapped[list] = mapped_column(JSON, default=list)
    input_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    output_name: Mapped[str | None] = mapped_column(String(300))
    output_bytes: Mapped[int | None] = mapped_column(BigInteger)
    output_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    expires_at: Mapped[datetime] = mapped_column(index=True)
    files_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_url: Mapped[str | None] = mapped_column(String(2000))
    webhook_status: Mapped[str | None] = mapped_column(String(16))  # pending | delivered | failed


class Document(Base):
    """A file the user chose to keep in their account. Unlike task files, these are not auto-deleted."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    shares: Mapped[list["ShareLink"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class ShareLink(Base):
    """A link that lets anyone holding it view or download one document."""

    __tablename__ = "share_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    allow_download: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None]
    max_downloads: Mapped[int | None] = mapped_column(Integer)
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    sent_to: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    revoked_at: Mapped[datetime | None]

    document: Mapped[Document] = relationship(back_populates="shares")


MIGRATION_LOCK = 0x466F6C696F  # "Folio"


def alembic_config(connection=None):
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    config.attributes["connection"] = connection
    return config


class SignatureRequest(Base):
    """A document sent to one or more people to sign. Its files live under esign/{id}/ in storage."""

    __tablename__ = "signature_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="sent")  # sent | completed | declined | cancelled | expired
    sequential: Mapped[bool] = mapped_column(Boolean, default=False)
    original_sha256: Mapped[str] = mapped_column(String(64))
    final_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    expires_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    files_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    signers: Mapped[list["Signer"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="Signer.position"
    )
    events: Mapped[list["SignatureEvent"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="SignatureEvent.at"
    )


class Signer(Base):
    __tablename__ = "signers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("signature_requests.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="waiting")  # waiting | pending | viewed | signed | declined
    # [{"type": "signature" | "initials" | "date" | "name" | "text" | "checkbox", "page", "x", "y", "width", "height",
    #   "required", "label"}], positions as fractions of the visible page (top-left origin)
    fields: Mapped[list] = mapped_column(JSON)
    values: Mapped[dict | None] = mapped_column(JSON)  # filled in when they sign
    signed_at: Mapped[datetime | None]
    decline_reason: Mapped[str | None] = mapped_column(Text)

    request: Mapped[SignatureRequest] = relationship(back_populates="signers")


class SignatureEvent(Base):
    """The audit trail: every send, view, signature, decline and reminder."""

    __tablename__ = "signature_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("signature_requests.id", ondelete="CASCADE"), index=True)
    signer_id: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))
    at: Mapped[datetime] = mapped_column(default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[str | None] = mapped_column(Text)

    request: Mapped[SignatureRequest] = relationship(back_populates="events")


class Database:
    def __init__(self, url: str):
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self) -> None:
        """Bring the schema up to date. Safe to call from every process at once: Postgres serialises the runs."""
        from alembic import command

        with self.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK})
            command.upgrade(alembic_config(connection), "head")

    @contextmanager
    def session(self) -> Iterator:
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; normalise so comparisons with aware datetimes work everywhere."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
