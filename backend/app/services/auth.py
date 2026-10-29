"""Accounts and sign-in: email + password, magic links, Google, and API keys."""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import func, select

from app.domain.errors import NotFound, ServiceUnavailable, Unauthorized, ValidationFailed
from app.domain.ports import Mailer
from app.infra.db import ApiKey, Database, LoginToken, User, as_utc, utcnow

API_KEY_PREFIX = "fk_live_"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(
        self,
        *,
        db: Database,
        mailer: Mailer,
        secret_key: str,
        public_url: str,
        brand_name: str,
        token_minutes: int,
        magic_link_minutes: int,
        google_client_id: str | None,
        google_client_secret: str | None,
    ):
        self.db = db
        self.mailer = mailer
        self.secret = secret_key
        self.public_url = public_url.rstrip("/")
        self.brand = brand_name
        self.token_ttl = timedelta(minutes=token_minutes)
        self.magic_ttl = timedelta(minutes=magic_link_minutes)
        self.google_id = google_client_id
        self.google_secret = google_client_secret
        self.hasher = PasswordHasher()

    # ---- sessions ---------------------------------------------------------------------------

    def issue_token(self, user: User) -> str:
        now = utcnow()
        payload = {"sub": user.id, "ver": user.token_version, "iat": now, "exp": now + self.token_ttl, "typ": "session"}
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def user_from_token(self, token: str) -> User:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise Unauthorized("Your session has expired. Please sign in again.") from None
        if payload.get("typ") != "session":
            raise Unauthorized("Invalid session.")
        with self.db.session() as session:
            user = session.get(User, payload["sub"])
            if user is None or user.token_version != payload.get("ver"):
                raise Unauthorized("Your session has expired. Please sign in again.")
            return user

    def sign_out_everywhere(self, user_id: str) -> None:
        with self.db.session() as session:
            session.get(User, user_id).token_version += 1

    # ---- password ---------------------------------------------------------------------------

    def register(self, email: str, password: str, name: str | None = None) -> User:
        email = normalize_email(email)
        self._check_password(password)
        with self.db.session() as session:
            existing = session.scalar(select(User).where(User.email == email))
            if existing is not None:
                if existing.password_hash:
                    raise ValidationFailed("An account with this email already exists. Sign in instead.")
                # Account created via Google or magic link: let them add a password.
                existing.password_hash = self.hasher.hash(password)
                existing.name = existing.name or name
                return existing
            user = User(email=email, name=name, password_hash=self.hasher.hash(password))
            session.add(user)
            session.flush()
            return user

    def login(self, email: str, password: str) -> User:
        with self.db.session() as session:
            user = session.scalar(select(User).where(User.email == normalize_email(email)))
            if user is None or not user.password_hash:
                self.hasher.hash(password)  # equalize timing for unknown accounts
                raise Unauthorized("Wrong email or password.")
            try:
                self.hasher.verify(user.password_hash, password)
            except VerificationError:
                raise Unauthorized("Wrong email or password.") from None
            if self.hasher.check_needs_rehash(user.password_hash):
                user.password_hash = self.hasher.hash(password)
            return user

    def change_password(self, user_id: str, current: str | None, new: str) -> None:
        self._check_password(new)
        with self.db.session() as session:
            user = session.get(User, user_id)
            if user.password_hash:
                try:
                    self.hasher.verify(user.password_hash, current or "")
                except VerificationError:
                    raise Unauthorized("Your current password is wrong.") from None
            user.password_hash = self.hasher.hash(new)
            user.token_version += 1

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < 8:
            raise ValidationFailed("Use at least 8 characters for your password.")
        if len(password) > 256:
            raise ValidationFailed("That password is too long.")

    # ---- magic links ------------------------------------------------------------------------

    def send_magic_link(self, email: str) -> None:
        email = normalize_email(email)
        token = secrets.token_urlsafe(32)
        with self.db.session() as session:
            session.add(LoginToken(token_hash=sha256(token), email=email, expires_at=utcnow() + self.magic_ttl))
        link = f"{self.public_url}/auth/magic?token={token}"
        self.mailer.send(
            to=email,
            subject=f"Your {self.brand} sign-in link",
            text=(
                f"Click to sign in to {self.brand}:\n\n{link}\n\n"
                f"The link works once and expires in {int(self.magic_ttl.total_seconds() // 60)} minutes. "
                "If you didn't ask for it, ignore this email."
            ),
        )

    def consume_magic_link(self, token: str) -> User:
        with self.db.session() as session:
            row = session.get(LoginToken, sha256(token))
            if row is None or row.used_at is not None or as_utc(row.expires_at) < utcnow():
                raise Unauthorized("This sign-in link is invalid or has expired. Request a new one.")
            row.used_at = utcnow()
            user = session.scalar(select(User).where(User.email == row.email))
            if user is None:
                user = User(email=row.email)
                session.add(user)
            user.email_verified = True
            session.flush()
            return user

    # ---- Google -----------------------------------------------------------------------------

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_id and self.google_secret)

    def google_redirect_uri(self) -> str:
        return f"{self.public_url}/api/auth/google/callback"

    def google_authorize_url(self, state: str) -> str:
        if not self.google_enabled:
            raise ServiceUnavailable("Google sign-in is not configured.")
        query = {
            "client_id": self.google_id,
            "redirect_uri": self.google_redirect_uri(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(query)}"

    def google_login(self, code: str) -> User:
        if not self.google_enabled:
            raise ServiceUnavailable("Google sign-in is not configured.")
        try:
            tokens = httpx.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.google_id,
                    "client_secret": self.google_secret,
                    "redirect_uri": self.google_redirect_uri(),
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            tokens.raise_for_status()
            info = httpx.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens.json()['access_token']}"},
                timeout=15,
            )
            info.raise_for_status()
        except httpx.HTTPError:
            raise Unauthorized("Google sign-in failed. Please try again.") from None
        profile = info.json()
        if not profile.get("email_verified"):
            raise Unauthorized("Your Google email address isn't verified.")
        return self.upsert_google_user(profile["sub"], profile["email"], profile.get("name"))

    def upsert_google_user(self, sub: str, email: str, name: str | None) -> User:
        email = normalize_email(email)
        with self.db.session() as session:
            user = session.scalar(select(User).where(User.google_sub == sub)) or session.scalar(
                select(User).where(User.email == email)
            )
            if user is None:
                user = User(email=email, name=name)
                session.add(user)
            user.google_sub, user.email_verified = sub, True
            user.name = user.name or name
            session.flush()
            return user

    # ---- API keys ---------------------------------------------------------------------------

    def create_api_key(self, user_id: str, name: str) -> tuple[ApiKey, str]:
        raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
        with self.db.session() as session:
            active = session.scalar(
                select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
            )
            if active >= 20:
                raise ValidationFailed("You can have at most 20 active API keys.")
            key = ApiKey(user_id=user_id, name=name.strip()[:100] or "API key", prefix=raw[:12], key_hash=sha256(raw))
            session.add(key)
            session.flush()
            return key, raw

    def list_api_keys(self, user_id: str) -> list[ApiKey]:
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(ApiKey)
                    .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
                    .order_by(ApiKey.created_at.desc())
                )
            )

    def revoke_api_key(self, user_id: str, key_id: str) -> None:
        with self.db.session() as session:
            key = session.get(ApiKey, key_id)
            if key is None or key.user_id != user_id:
                raise NotFound("API key not found.")
            key.revoked_at = utcnow()

    def authenticate_api_key(self, raw: str) -> tuple[User, ApiKey]:
        if not raw.startswith(API_KEY_PREFIX):
            raise Unauthorized("Invalid API key.")
        with self.db.session() as session:
            key = session.scalar(select(ApiKey).where(ApiKey.key_hash == sha256(raw)))
            if key is None or key.revoked_at is not None:
                raise Unauthorized("Invalid or revoked API key.")
            key.last_used_at = utcnow()
            user = session.get(User, key.user_id)
            return user, key
