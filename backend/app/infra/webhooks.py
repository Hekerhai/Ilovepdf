"""Outgoing webhooks: tell an API client's server when its task finishes, signed so it can trust the call.

Signature header (same scheme as Stripe's, so existing verification helpers fit):
    Folio-Signature: t=<unix time>,v1=<hex HMAC-SHA256 of "<t>.<raw body>" with the account's webhook secret>
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import time
from urllib.parse import urlsplit

import httpx

from app.domain.errors import ValidationFailed

log = logging.getLogger(__name__)

SIGNATURE_HEADER = "Folio-Signature"
RETRY_DELAYS = (0, 2, 8)  # seconds before each attempt


def new_webhook_secret() -> str:
    return "whsec_" + secrets.token_hex(24)


def sign(secret: str, body: bytes, timestamp: int) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def check_url(url: str, *, allow_private: bool = False) -> str:
    """Only public http(s) endpoints: a webhook must never be able to reach the platform's own network."""
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValidationFailed("webhook_url must be an http(s) URL.")
    if parts.scheme == "http" and not allow_private:
        raise ValidationFailed("webhook_url must use https.")
    if len(url) > 2000:
        raise ValidationFailed("webhook_url is too long.")
    if allow_private:
        return url
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise ValidationFailed("webhook_url's host can't be resolved.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValidationFailed("webhook_url must point to a public address.")
    return url


class WebhookSender:
    def __init__(self, *, allow_private: bool = False, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.allow_private = allow_private
        self.transport = transport
        self.sleep = sleep

    def deliver(self, url: str, secret: str, event: dict) -> bool:
        """POST the event, retrying a few times on errors and 5xx. Returns whether the endpoint accepted it."""
        body = json.dumps(event, separators=(",", ":")).encode()
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            self.sleep(delay)
            try:
                check_url(url, allow_private=self.allow_private)  # re-checked at send time: DNS can change
                with httpx.Client(timeout=10, transport=self.transport, follow_redirects=False) as client:
                    response = client.post(
                        url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "Folio-Webhooks/1",
                            SIGNATURE_HEADER: sign(secret, body, int(time.time())),
                        },
                    )
                if response.status_code < 300:
                    return True
                if response.status_code < 500 and response.status_code != 429:
                    log.warning("Webhook to %s rejected with %s", url, response.status_code)
                    return False
            except ValidationFailed as exc:
                log.warning("Webhook to %s not sent: %s", url, exc.message)
                return False
            except httpx.HTTPError as exc:
                log.info("Webhook attempt %s to %s failed: %s", attempt, url, exc)
        return False
