"""Ports: the small interfaces the application depends on.

Concrete adapters live in ``app.infra`` and ``app.engines`` and are wired in ``app.container``.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileStorage(Protocol):
    """Blob storage for uploaded inputs and produced outputs."""

    def put(self, key: str, source: Path) -> None: ...
    def get(self, key: str, destination: Path) -> Path: ...
    def open_stream(self, key: str) -> Iterator[bytes]: ...
    def size(self, key: str) -> int: ...
    def delete_prefix(self, prefix: str) -> None: ...


@runtime_checkable
class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...


@runtime_checkable
class DocumentConverter(Protocol):
    """Converts office documents and HTML into PDF."""

    def office_to_pdf(self, source: Path, output: Path) -> Path: ...
    def html_to_pdf(self, *, output: Path, html_file: Path | None = None, url: str | None = None) -> Path: ...


@runtime_checkable
class AIProvider(Protocol):
    @property
    def available(self) -> bool: ...
    def complete(self, *, system: str, prompt: str, max_tokens: int = 2048) -> str: ...


@runtime_checkable
class Mailer(Protocol):
    def send(self, *, to: str, subject: str, text: str) -> None: ...


@dataclass(frozen=True)
class CheckoutSession:
    provider: str
    url: str | None
    # Razorpay checkout runs in the page and needs these instead of a redirect URL.
    client_payload: dict | None = None


@dataclass(frozen=True)
class SubscriptionEvent:
    """A provider-neutral billing event produced by verifying a webhook."""

    provider: str
    kind: str  # "activated" | "renewed" | "cancelled" | "ignored"
    owner_type: str | None = None  # "user" | "team"
    owner_id: str | None = None
    plan_id: str | None = None
    seats: int = 1
    external_customer_id: str | None = None
    external_subscription_id: str | None = None
    current_period_end: datetime | None = None


@runtime_checkable
class PaymentGateway(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    def create_checkout(
        self,
        *,
        owner_type: str,
        owner_id: str,
        email: str,
        plan_id: str,
        interval: str,
        seats: int,
        amount: int,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...

    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> SubscriptionEvent: ...

    def cancel(self, external_subscription_id: str) -> None: ...
