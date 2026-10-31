import json
import re

import pdfplumber
import pikepdf

from tests.conftest import make_pdf
from tests.test_api import signup


def signature_png(size=(240, 90)) -> str:
    import base64
    import io

    from PIL import Image, ImageDraw

    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(10, 70), (80, 15), (150, 70), (230, 20)], fill=(20, 20, 120, 255), width=6)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def details(**over):
    body = {
        "title": "Services agreement",
        "message": "Please sign by Friday.",
        "signers": [
            {"name": "Grace Hopper", "email": "grace@example.com"},
            {"name": "Alan Turing", "email": "alan@example.com"},
        ],
        "fields": [
            {"signer": 0, "type": "signature", "page": 1, "x": 0.1, "y": 0.7, "width": 0.3, "height": 0.08},
            {"signer": 0, "type": "date", "page": 1, "x": 0.1, "y": 0.8, "width": 0.2, "height": 0.03},
            {
                "signer": 0,
                "type": "text",
                "page": 1,
                "x": 0.5,
                "y": 0.8,
                "width": 0.3,
                "height": 0.03,
                "label": "Job title",
            },
            {"signer": 1, "type": "signature", "page": 2, "x": 0.5, "y": 0.7, "width": 0.3, "height": 0.08},
            {
                "signer": 1,
                "type": "checkbox",
                "page": 2,
                "x": 0.5,
                "y": 0.85,
                "width": 0.03,
                "height": 0.02,
                "label": "I agree",
            },
        ],
    }
    body.update(over)
    return body


def send(client, tmp_path, **over):
    pdf = make_pdf(tmp_path / "agreement.pdf", 2)
    with pdf.open("rb") as f:
        return client.post(
            "/api/esign/requests",
            data={"details": json.dumps(details(**over))},
            files={"file": ("agreement.pdf", f, "application/pdf")},
        )


def link_for(c, email: str) -> str:
    mails = [m for m in c.mailer.outbox if m["to"] == email and "/sign/" in m["text"]]
    assert mails, f"no signing email for {email}"
    return re.search(r"/sign/([\w-]+)", mails[-1]["text"]).group(1)


def test_full_flow_parallel(app_env, tmp_path):
    c, client = app_env
    signup(client)
    r = send(client, tmp_path)
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["status"] == "sent" and [s["status"] for s in req["signers"]] == ["pending", "pending"]

    grace, alan = link_for(c, "grace@example.com"), link_for(c, "alan@example.com")
    anon = client.__class__(client.app)  # signers have no account
    view = anon.get(f"/api/esign/sign/{grace}").json()
    assert view["can_sign"] and len(view["fields"]) == 3 and view["request"]["sender"] == "Ada"
    assert anon.get(f"/api/esign/sign/{grace}/document").content.startswith(b"%PDF")

    missing = anon.post(f"/api/esign/sign/{grace}", json={"signature": signature_png(), "consent": True})
    assert missing.status_code == 422 and "Job title" in missing.json()["error"]["message"]
    ok = anon.post(
        f"/api/esign/sign/{grace}", json={"signature": signature_png(), "values": {"2": "CTO"}, "consent": True}
    )
    assert ok.json() == {"status": "signed", "request_status": "sent"}
    again = anon.post(
        f"/api/esign/sign/{grace}", json={"signature": signature_png(), "values": {"2": "CTO"}, "consent": True}
    )
    assert again.status_code == 422

    done = anon.post(
        f"/api/esign/sign/{alan}", json={"signature": signature_png(), "values": {"1": True}, "consent": True}
    )
    assert done.json()["request_status"] == "completed"

    detail = client.get(f"/api/esign/requests/{req['id']}").json()
    assert detail["status"] == "completed" and detail["final_sha256"]
    assert [e["kind"] for e in detail["events"]] == ["created", "viewed", "signed", "signed", "completed"]
    assert sum("Completed:" in m["subject"] for m in c.mailer.outbox) == 3

    out = tmp_path / "signed.pdf"
    out.write_bytes(client.get(f"/api/esign/requests/{req['id']}/document").content)
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 3  # two pages plus the audit trail
    with pdfplumber.open(out) as pdf:
        assert "CTO" in pdf.pages[0].extract_text()
        assert pdf.pages[0].images, "signature image drawn on page 1"
        assert pdf.pages[1].images and "X" in pdf.pages[1].extract_text()
        trail = pdf.pages[2].extract_text()
        assert "Grace Hopper" in trail and "alan@example.com" in trail and req["id"] in trail

    from app.tools.signatures import signature_report

    report = signature_report(out)
    assert "valid, document unchanged since signing" in report
    # The signer can download the sealed copy from their link too.
    assert anon.get(f"/api/esign/sign/{grace}").json()["final_available"]
    assert anon.get(f"/api/esign/sign/{grace}/document").content == out.read_bytes()


def test_sequential_and_decline(app_env, tmp_path):
    c, client = app_env
    signup(client)
    req = send(client, tmp_path, sequential=True).json()
    assert [s["status"] for s in req["signers"]] == ["pending", "waiting"]
    assert not any(m["to"] == "alan@example.com" for m in c.mailer.outbox)
    grace = link_for(c, "grace@example.com")
    client.post(
        f"/api/esign/sign/{grace}", json={"signature": signature_png(), "values": {"2": "CTO"}, "consent": True}
    )
    alan = link_for(c, "alan@example.com")  # sent only now
    r = client.post(f"/api/esign/sign/{alan}/decline", json={"reason": "Wrong address"})
    assert r.json() == {"status": "declined"}
    assert any(m["to"] == "ada@example.com" and "Wrong address" in m["text"] for m in c.mailer.outbox)
    assert client.get(f"/api/esign/requests/{req['id']}").json()["status"] == "declined"


def test_owner_actions_and_quota(app_env, tmp_path):
    c, client = app_env
    assert send(client, tmp_path).status_code == 401  # needs an account
    signup(client)
    bad = send(
        client,
        tmp_path,
        fields=[{"signer": 0, "type": "date", "page": 1, "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}],
    )
    assert bad.status_code == 422 and "signature field" in bad.json()["error"]["message"]
    far = send(
        client,
        tmp_path,
        fields=[
            {"signer": 0, "type": "signature", "page": 9, "x": 0, "y": 0, "width": 0.1, "height": 0.1},
            {"signer": 1, "type": "signature", "page": 1, "x": 0, "y": 0, "width": 0.1, "height": 0.1},
        ],
    )
    assert far.status_code == 422 and "Page 9" in far.json()["error"]["message"]

    first = send(client, tmp_path).json()
    old = link_for(c, "grace@example.com")
    assert client.post(f"/api/esign/requests/{first['id']}/remind").status_code == 200
    assert client.get(f"/api/esign/sign/{old}").status_code == 404  # a reminder replaces the link
    assert client.get(f"/api/esign/sign/{link_for(c, 'grace@example.com')}").status_code == 200

    assert client.post(f"/api/esign/requests/{first['id']}/cancel").json()["status"] == "cancelled"
    send(client, tmp_path)
    send(client, tmp_path)
    over = send(client, tmp_path)  # the free plan includes three a month
    assert over.status_code == 429 and over.json()["error"]["code"] == "esign_limit"
    assert len(client.get("/api/esign/requests").json()["requests"]) == 3

    assert client.delete(f"/api/esign/requests/{first['id']}").status_code == 204
    assert client.get(f"/api/esign/requests/{first['id']}").status_code == 404
    assert not list((c.settings.storage_dir / "esign" / first["id"]).glob("*"))


def test_purge_and_account_export(app_env, tmp_path):
    from datetime import timedelta

    from app.infra.db import SignatureRequest, utcnow

    c, client = app_env
    user = signup(client)
    req = send(client, tmp_path).json()
    with c.db.session() as s:
        s.get(SignatureRequest, req["id"]).expires_at = utcnow() - timedelta(days=60)
    assert c.esign.purge() == 1
    detail = client.get(f"/api/esign/requests/{req['id']}").json()
    assert detail["status"] == "expired" and detail["files_deleted"]
    assert client.get(f"/api/esign/requests/{req['id']}/document").status_code == 404
    assert c.privacy.export(user["id"])["signature_requests"][0]["title"] == "Services agreement"


def test_access_code_and_id_stamp(app_env, tmp_path):
    c, client = app_env
    signup(client)
    signers = [
        {"name": "Grace Hopper", "email": "grace@example.com", "access_code": "4821"},
        {"name": "Alan Turing", "email": "alan@example.com"},
    ]
    req = send(client, tmp_path, signers=signers).json()
    assert [s["has_code"] for s in req["signers"]] == [True, False]
    invite = next(m for m in c.mailer.outbox if m["to"] == "grace@example.com")
    assert "access code" in invite["text"] and "4821" not in invite["text"]

    grace, alan = link_for(c, "grace@example.com"), link_for(c, "alan@example.com")
    anon = client.__class__(client.app)
    locked = anon.get(f"/api/esign/sign/{grace}").json()
    assert locked["needs_code"] and "fields" not in locked and locked["request"]["title"] == "Services agreement"
    assert anon.get(f"/api/esign/sign/{grace}/document").status_code == 401
    wrong = anon.get(f"/api/esign/sign/{grace}", headers={"X-Access-Code": "0000"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "bad_code"
    view = anon.get(f"/api/esign/sign/{grace}", headers={"X-Access-Code": "4821"}).json()
    assert not view["needs_code"] and len(view["fields"]) == 3
    assert anon.get(f"/api/esign/sign/{grace}/document?code=4821").content.startswith(b"%PDF")
    body = {"signature": signature_png(), "values": {"2": "CTO"}, "consent": True}
    assert anon.post(f"/api/esign/sign/{grace}", json=body).status_code == 401  # needed on every call
    assert anon.post(f"/api/esign/sign/{grace}", json=body, headers={"X-Access-Code": "4821"}).status_code == 200
    anon.post(f"/api/esign/sign/{alan}", json={"signature": signature_png(), "values": {"1": True}, "consent": True})

    detail = client.get(f"/api/esign/requests/{req['id']}").json()
    assert detail["status"] == "completed" and "code_failed" in [e["kind"] for e in detail["events"]]
    out = tmp_path / "signed.pdf"
    out.write_bytes(client.get(f"/api/esign/requests/{req['id']}/document").content)
    with pdfplumber.open(out) as pdf:
        for page in pdf.pages[:2]:
            assert f"ID {req['id']}" in page.extract_text()


def test_access_code_locks_after_repeated_guesses(app_env, tmp_path):
    c, client = app_env
    signup(client)
    signers = [{"name": "Grace Hopper", "email": "grace@example.com", "access_code": "secret-code"}]
    fields = [{"signer": 0, "type": "signature", "page": 1, "x": 0.1, "y": 0.7, "width": 0.3, "height": 0.08}]
    send(client, tmp_path, signers=signers, fields=fields, stamp_id=False)
    grace = link_for(c, "grace@example.com")
    for _ in range(10):
        assert client.get(f"/api/esign/sign/{grace}", headers={"X-Access-Code": "guess"}).status_code == 401
    locked = client.get(f"/api/esign/sign/{grace}", headers={"X-Access-Code": "secret-code"})
    assert locked.status_code == 403 and "Too many" in locked.json()["error"]["message"]


def test_templates(app_env, tmp_path):
    c, client = app_env
    assert client.get("/api/esign/templates").status_code == 401
    signup(client)
    pdf = make_pdf(tmp_path / "lease.pdf", 2)
    tpl_body = {
        "name": "Lease",
        "roles": ["Tenant", "Landlord"],
        "fields": [
            {"signer": 0, "type": "signature", "page": 1, "x": 0.1, "y": 0.7, "width": 0.3, "height": 0.08},
            {"signer": 1, "type": "signature", "page": 2, "x": 0.5, "y": 0.7, "width": 0.3, "height": 0.08},
        ],
        "sequential": True,
    }

    def save(body):
        with pdf.open("rb") as f:
            return client.post(
                "/api/esign/templates",
                data={"details": json.dumps(body)},
                files={"file": ("lease.pdf", f, "application/pdf")},
            )

    bad = save({**tpl_body, "roles": ["Tenant", "tenant"]})
    assert bad.status_code == 422 and "different name" in bad.json()["error"]["message"]
    missing = save({**tpl_body, "fields": tpl_body["fields"][:1]})
    assert missing.status_code == 422 and "Landlord" in missing.json()["error"]["message"]
    r = save(tpl_body)
    assert r.status_code == 201, r.text
    tpl = r.json()
    assert tpl["roles"] == ["Tenant", "Landlord"] and tpl["field_count"] == 2

    listed = client.get("/api/esign/templates").json()["templates"]
    assert [t["name"] for t in listed] == ["Lease"]
    full = client.get(f"/api/esign/templates/{tpl['id']}").json()
    assert full["fields"][1]["signer"] == 1 and full["sequential"]
    assert client.get(f"/api/esign/templates/{tpl['id']}/document").content == pdf.read_bytes()
    assert client.patch(f"/api/esign/templates/{tpl['id']}", json={"name": "Flat lease"}).json()["name"] == "Flat lease"

    export = client.get("/api/me/export").json()
    assert export["signature_templates"][0]["roles"] == ["Tenant", "Landlord"]

    assert client.delete(f"/api/esign/templates/{tpl['id']}").status_code == 204
    assert client.get(f"/api/esign/templates/{tpl['id']}").status_code == 404
    assert not list(c.settings.storage_dir.glob("esign-templates/*/*"))
