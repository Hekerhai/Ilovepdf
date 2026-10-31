import hashlib
import hmac
import json

import httpx
import pytest

from app.domain.errors import ValidationFailed
from app.infra.webhooks import SIGNATURE_HEADER, WebhookSender, check_url
from tests.test_api import files, signup


def api_client(app_env):
    c, client = app_env
    signup(client)
    key = client.post("/api/me/api-keys", json={"name": "CI"}).json()["key"]
    return c, client, {"Authorization": f"Bearer {key}"}


def capture(c, status=200):
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(status)

    c.jobs.webhooks = WebhookSender(allow_private=True, transport=httpx.MockTransport(handler), sleep=lambda _: None)
    return received


def verify(request: httpx.Request, secret: str) -> dict:
    parts = dict(p.split("=", 1) for p in request.headers[SIGNATURE_HEADER].split(","))
    expected = hmac.new(secret.encode(), f"{parts['t']}.".encode() + request.content, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, parts["v1"])
    return json.loads(request.content)


def test_job_webhook_is_signed_and_recorded(app_env, pdf3):
    c, client, headers = api_client(app_env)
    received = capture(c)
    r = client.post(
        "/v1/jobs",
        data={"tool": "compress", "webhook_url": "http://hooks.test/folio"},
        files=files(pdf3),
        headers=headers,
    )
    assert r.status_code == 202, r.text
    secret = client.get("/v1/webhooks/secret", headers=headers).json()["secret"]
    assert secret.startswith("whsec_") and client.get("/api/me/webhook-secret").json()["secret"] == secret
    [request] = received
    event = verify(request, secret)
    assert event["type"] == "job.succeeded" and event["job"]["id"] == r.json()["id"]
    assert event["job"]["download_url"].endswith(f"/v1/jobs/{r.json()['id']}/download")
    assert client.get(f"/v1/jobs/{r.json()['id']}", headers=headers).json()["webhook_status"] == "delivered"

    rotated = client.post("/api/me/webhook-secret/rotate").json()["secret"]
    assert rotated != secret


def test_failed_jobs_and_failing_endpoints(app_env, tmp_path):
    c, client, headers = api_client(app_env)
    received = capture(c, status=503)
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot really a pdf")
    r = client.post(
        "/v1/jobs", data={"tool": "compress", "webhook_url": "http://hooks.test/x"}, files=files(bad), headers=headers
    )
    assert len(received) == 3  # retried, then given up
    assert json.loads(received[0].content)["type"] == "job.failed"
    assert client.get(f"/v1/jobs/{r.json()['id']}", headers=headers).json()["webhook_status"] == "failed"


def test_webhook_urls_must_be_public():
    for url in (
        "ftp://x.test/",
        "http://example.com/hook",
        "https://127.0.0.1/hook",
        "https://10.0.0.8/",
        "https://[::1]/",
        "https://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(ValidationFailed):
            check_url(url)
    assert check_url("http://localhost:9000/", allow_private=True)


def test_form_fields_endpoint(app_env, pdf3, tmp_path):
    from tests.test_tools import run

    c, client, headers = api_client(app_env)
    [form] = run("create_forms", [pdf3], tmp_path, fields=[
        {"type": "text", "name": "full_name", "page": 1, "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.04},
        {"type": "dropdown", "name": "size", "page": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.04,
         "options": ["S", "M", "L"]},
    ])  # fmt: skip
    with form.open("rb") as f:
        r = client.post("/v1/forms/fields", files={"file": ("form.pdf", f, "application/pdf")}, headers=headers)
    fields = {f["name"]: f for f in r.json()["fields"]}
    assert fields["full_name"]["type"] == "text" and fields["size"]["options"] == ["S", "M", "L"]
    assert client.get("/v1/usage", headers=headers).json()["used"] == 0  # free
