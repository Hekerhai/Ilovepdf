"""API tests: the full stack (HTTP -> services -> real PDF engines) with an inline queue."""

import hashlib
import hmac
import io
import json
from datetime import timedelta

import pikepdf
import pytest
from fastapi.testclient import TestClient

from app.domain.ports import SubscriptionEvent
from app.infra.db import Job, User, utcnow
from tests.conftest import make_pdf


def files(*paths):
    return [("files", (p.name, p.read_bytes(), "application/pdf")) for p in paths]


def run(client, tool, paths, options=None, **kw):
    data = {"tool": tool, "options": json.dumps(options or {})}
    return client.post("/api/jobs", data=data, files=files(*paths), **kw)


def signup(client, email="ada@example.com", password="correct horse"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "Ada"})
    assert r.status_code == 200, r.text
    return r.json()["user"]


def upgrade(c, owner_type, owner_id, plan="pro", seats=1, sub="sub_1"):
    c.billing.apply(SubscriptionEvent(provider="stripe", kind="activated", owner_type=owner_type,
                                      owner_id=owner_id, plan_id=plan, seats=seats,
                                      external_subscription_id=sub))  # fmt: skip


def test_tools_catalog(app_env):
    _, client = app_env
    body = client.get("/api/tools").json()
    ids = {t["id"] for t in body["tools"]}
    assert {"merge", "compress", "ocr", "pdf_to_word", "sign", "redact"} <= ids
    assert len(body["categories"]) == 7


def test_guest_merge_and_download(app_env, pdf3, pdf2):
    _, client = app_env
    r = run(client, "merge", [pdf3, pdf2])
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "succeeded" and job["output_name"] == "merged.pdf"
    download = client.get(job["download_url"])
    assert download.status_code == 200 and download.headers["content-type"] == "application/pdf"
    with pikepdf.open(io.BytesIO(download.content)) as pdf:
        assert len(pdf.pages) == 5


def test_multiple_outputs_are_zipped(app_env, pdf3):
    _, client = app_env
    job = run(client, "split", [pdf3], {"mode": "all"}).json()
    assert job["output_name"].endswith(".zip") and job["output_count"] == 3


def test_other_guests_cannot_see_my_task(app_env, pdf3):
    c, client = app_env
    job = run(client, "rotate", [pdf3]).json()
    stranger = TestClient(client.app)
    assert stranger.get(f"/api/jobs/{job['id']}").status_code == 403


def test_input_validation(app_env, pdf3, tmp_path):
    _, client = app_env
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"not a pdf")
    r = run(client, "compress", [fake])
    assert r.status_code == 422 and "not a valid PDF" in r.json()["error"]["message"]
    r = client.post("/api/jobs", data={"tool": "compress"},
                    files=[("files", ("a.docx", b"x", "application/octet-stream"))])  # fmt: skip
    assert r.status_code == 422 and "isn't supported" in r.json()["error"]["message"]
    r = run(client, "rotate", [pdf3], {"angle": 45})
    assert r.status_code == 422 and "angle" in r.json()["error"]["message"]
    assert run(client, "merge", [pdf3]).status_code == 422
    assert run(client, "nope", [pdf3]).status_code == 404


def test_tool_errors_are_reported_on_the_job(app_env, pdf3):
    _, client = app_env
    job = run(client, "remove_pages", [pdf3], {"pages": "1-3"}).json()
    assert job["status"] == "failed" and "every page" in job["error"]


def test_premium_and_limits_for_guests(app_env, pdf3):
    c, client = app_env
    r = run(client, "ocr", [pdf3])
    assert r.status_code == 402 and r.json()["error"]["code"] == "premium_required"
    for _ in range(10):
        assert run(client, "rotate", [pdf3]).status_code == 202
    r = run(client, "rotate", [pdf3])
    assert r.status_code == 429 and "Sign up" in r.json()["error"]["message"]
    # Clearing cookies doesn't reset the limit (same IP).
    assert run(TestClient(client.app), "rotate", [pdf3]).status_code == 429


def test_file_size_limit(app_env, tmp_path):
    c, client = app_env
    big = make_pdf(tmp_path / "big.pdf", 1)
    with big.open("ab") as fh:
        fh.write(b"%" + b"0" * (26 * 1024 * 1024))
    r = run(client, "compress", [big])
    assert r.status_code == 429 and r.json()["error"]["code"] == "file_too_large"


def test_register_login_session(app_env):
    _, client = app_env
    signup(client)
    me = client.get("/api/auth/session").json()
    assert me["user"]["email"] == "ada@example.com" and me["plan"]["id"] == "free"
    assert (
        client.post("/api/auth/register", json={"email": "ADA@example.com", "password": "another one"}).status_code
        == 422
    )
    client.post("/api/auth/logout")
    assert client.get("/api/auth/session").json()["user"] is None
    assert (
        client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong pass"}).status_code == 401
    )
    assert (
        client.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse"}).status_code
        == 200
    )
    assert client.get("/api/jobs").status_code == 200


def test_magic_link(app_env):
    c, client = app_env
    assert client.post("/api/auth/magic-link", json={"email": "grace@example.com"}).status_code == 202
    token = c.mailer.outbox[-1]["text"].split("token=")[1].split()[0]
    r = client.post("/api/auth/magic-link/verify", json={"token": token})
    assert r.status_code == 200 and r.json()["user"]["email_verified"]
    assert client.post("/api/auth/magic-link/verify", json={"token": token}).status_code == 401  # single use


def test_logout_everywhere_revokes_tokens(app_env):
    c, client = app_env
    signup(client)
    other = TestClient(client.app)
    other.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse"})
    assert client.post("/api/auth/logout-all").status_code == 204
    assert other.get("/api/auth/session").json()["user"] is None


def test_workflow_needs_pro_then_runs(app_env, pdf3):
    c, client = app_env
    user = signup(client)
    steps = [{"tool": "compress", "options": {"level": "low"}}, {"tool": "protect", "options": {"password": "pw"}}]
    r = client.post("/api/jobs", data={"steps": json.dumps(steps)}, files=files(pdf3))
    assert r.status_code == 402
    upgrade(c, "user", user["id"])
    assert client.get("/api/auth/session").json()["plan"]["id"] == "pro"
    job = client.post("/api/jobs", data={"steps": json.dumps(steps)}, files=files(pdf3)).json()
    assert job["status"] == "succeeded"
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(io.BytesIO(client.get(job["download_url"]).content))
    # Save it and run it again by id.
    wf = client.post("/api/workflows", json={"name": "Secure", "steps": steps}).json()
    job = client.post(f"/api/workflows/{wf['id']}/run", files=files(pdf3)).json()
    assert job["status"] == "succeeded"
    # A non-PDF producing step can't be followed by another.
    bad = [{"tool": "pdf_to_text"}, {"tool": "compress"}]
    assert client.post("/api/workflows", json={"name": "x", "steps": bad}).status_code == 422


def test_api_keys_and_public_api(app_env, pdf3):
    c, client = app_env
    signup(client)
    key = client.post("/api/me/api-keys", json={"name": "CI"}).json()["key"]
    api = TestClient(client.app)
    headers = {"Authorization": f"Bearer {key}"}
    assert api.get("/v1/tools").status_code == 401
    assert api.get("/v1/tools", headers=headers).status_code == 200
    job = api.post("/v1/jobs", headers=headers, data={"tool": "rotate", "options": '{"angle": 90}'},
                   files=files(pdf3)).json()  # fmt: skip
    assert job["status"] == "succeeded" and job["download_url"].startswith("/v1/")
    assert api.get(job["download_url"], headers=headers).status_code == 200
    assert api.get("/v1/usage", headers=headers).json()["used"] == 1
    key_id = client.get("/api/me/api-keys").json()["keys"][0]["id"]
    client.delete(f"/api/me/api-keys/{key_id}")
    assert api.get("/v1/tools", headers=headers).status_code == 401


def test_teams_seats_and_shared_plan(app_env, pdf3):
    c, client = app_env
    owner = signup(client, "owner@example.com")
    team = client.post("/api/teams", json={"name": "Acme"}).json()
    r = client.post(f"/api/teams/{team['id']}/invitations", json={"email": "bob@example.com"})
    assert r.status_code == 402  # needs Business
    upgrade(c, "team", team["id"], plan="business", seats=2, sub="sub_team")
    assert client.post(f"/api/teams/{team['id']}/invitations", json={"email": "bob@example.com"}).status_code == 201
    r = client.post(f"/api/teams/{team['id']}/invitations", json={"email": "eve@example.com"})
    assert r.status_code == 402 and "seats" in r.json()["error"]["message"]
    token = c.mailer.outbox[-1]["text"].split("token=")[1].split()[0]
    bob = TestClient(client.app)
    signup(bob, "bob@example.com")
    assert bob.post("/api/teams/join", json={"token": token}).status_code == 200
    assert bob.get("/api/auth/session").json()["plan"]["id"] == "business"
    assert run(bob, "ocr", [pdf3]).status_code == 202  # premium tool via the team plan
    detail = client.get(f"/api/teams/{team['id']}").json()
    assert {m["email"] for m in detail["members"]} == {"owner@example.com", "bob@example.com"}
    assert owner["id"] in {m["user_id"] for m in detail["members"]}


def test_razorpay_webhook_and_cancellation(app_env):
    c, client = app_env
    user = signup(client)
    payload = json.dumps({
        "event": "subscription.activated",
        "payload": {"subscription": {"entity": {
            "id": "sub_rzp", "quantity": 1, "current_end": 1900000000,
            "notes": {"owner_type": "user", "owner_id": user["id"], "plan_id": "pro"},
        }}},
    }).encode()  # fmt: skip
    bad = client.post("/api/billing/webhooks/razorpay", content=payload, headers={"X-Razorpay-Signature": "x"})
    assert bad.status_code == 422
    sig = hmac.new(b"whsec", payload, hashlib.sha256).hexdigest()
    ok = client.post("/api/billing/webhooks/razorpay", content=payload, headers={"X-Razorpay-Signature": sig})
    assert ok.status_code == 200 and client.get("/api/auth/session").json()["plan"]["id"] == "pro"
    cancelled = payload.replace(b"subscription.activated", b"subscription.cancelled")
    sig = hmac.new(b"whsec", cancelled, hashlib.sha256).hexdigest()
    client.post("/api/billing/webhooks/razorpay", content=cancelled, headers={"X-Razorpay-Signature": sig})
    assert client.get("/api/auth/session").json()["plan"]["id"] == "free"


def test_checkout_requires_configured_provider(app_env):
    _, client = app_env
    signup(client)
    r = client.post("/api/billing/checkout", json={"plan": "pro", "provider": "stripe"})
    assert r.status_code == 503
    plans = client.get("/api/billing/plans").json()
    assert {p["id"] for p in plans["plans"]} == {"free", "pro", "business"}


def test_gdpr_export_and_delete(app_env, pdf3):
    c, client = app_env
    user = signup(client)
    run(client, "rotate", [pdf3])
    export = client.get("/api/me/export").json()
    assert export["account"]["email"] == "ada@example.com" and len(export["tasks"]) == 1
    assert client.delete("/api/me").status_code == 204
    with c.db.session() as session:
        assert session.get(User, user["id"]) is None
        assert session.query(Job).count() == 0


def test_janitor_deletes_expired_files(app_env, pdf3):
    c, client = app_env
    job = run(client, "rotate", [pdf3]).json()
    assert c.privacy.purge_expired()["files"] == 0
    with c.db.session() as session:
        session.get(Job, job["id"]).expires_at = utcnow() - timedelta(minutes=1)
    assert c.privacy.purge_expired()["files"] == 1
    assert client.get(job["download_url"]).status_code == 404
    assert not list((c.settings.storage_dir / "jobs").glob(f"{job['id']}/**/*.pdf"))


def test_delete_files_now(app_env, pdf3):
    _, client = app_env
    job = run(client, "rotate", [pdf3]).json()
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(job["download_url"]).status_code == 404
