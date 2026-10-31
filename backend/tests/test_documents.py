import re

from tests.test_api import files, run, signup


def keep(client, path):
    r = client.post("/api/documents", files=[("files", (path.name, path.open("rb"), "application/pdf"))])
    assert r.status_code == 201, r.text
    return r.json()["documents"][0]


def test_documents_need_an_account_and_count_against_storage(app_env, pdf3):
    c, client = app_env
    assert client.get("/api/documents").status_code == 401
    signup(client)
    doc = keep(client, pdf3)
    listing = client.get("/api/documents").json()
    assert [d["id"] for d in listing["documents"]] == [doc["id"]]
    assert listing["usage"] == {"used_bytes": pdf3.stat().st_size, "limit_bytes": 500 * 1024 * 1024}
    assert client.get(f"/api/documents/{doc['id']}/file").content == pdf3.read_bytes()

    renamed = client.patch(f"/api/documents/{doc['id']}", json={"name": "Contract final"}).json()
    assert renamed["name"] == "Contract final.pdf"  # the extension is kept

    from app.plans import PLANS, PlanId

    plan = PLANS[PlanId.FREE]
    object.__setattr__(plan, "storage_bytes", pdf3.stat().st_size + 10)
    try:
        full = client.post("/api/documents", files=files(pdf3))
        assert full.status_code == 429 and full.json()["error"]["code"] == "storage_full"
    finally:
        object.__setattr__(plan, "storage_bytes", 500 * 1024 * 1024)

    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get("/api/documents").json()["documents"] == []


def test_keep_a_task_result(app_env, pdf3):
    _, client = app_env
    signup(client)
    job = run(client, "compress", [pdf3]).json()
    doc = client.post(f"/api/documents/from-job/{job['id']}").json()
    assert doc["name"] == job["output_name"] or doc["name"].endswith(".pdf")


def test_share_links(app_env, pdf3):
    c, client = app_env
    signup(client)
    doc = keep(client, pdf3)
    anon = client.__class__(client.app)

    open_link = client.post(f"/api/documents/{doc['id']}/shares", json={"max_downloads": 1}).json()
    token = open_link["url"].rsplit("/", 1)[1]
    meta = anon.get(f"/api/s/{token}").json()
    assert meta["name"] == "doc.pdf" and meta["shared_by"] == "Ada" and meta["grant"]
    assert anon.get(f"/api/s/{token}/file", params={"grant": meta["grant"]}).content == pdf3.read_bytes()
    assert anon.get(f"/api/s/{token}/file", params={"grant": meta["grant"], "download": True}).status_code == 200
    limited = anon.get(f"/api/s/{token}/file", params={"grant": meta["grant"], "download": True})
    assert limited.status_code == 403  # one download allowed
    assert anon.get(f"/api/s/{token}/file", params={"grant": "forged"}).status_code == 401

    locked = client.post(
        f"/api/documents/{doc['id']}/shares", json={"password": "open sesame", "expires_in_days": 3}
    ).json()
    token2 = locked["url"].rsplit("/", 1)[1]
    meta2 = anon.get(f"/api/s/{token2}").json()
    assert meta2["needs_password"] and meta2["grant"] is None
    assert anon.post(f"/api/s/{token2}/unlock", json={"password": "nope"}).status_code == 401
    grant = anon.post(f"/api/s/{token2}/unlock", json={"password": "open sesame"}).json()["grant"]
    assert anon.get(f"/api/s/{token2}/file", params={"grant": grant}).status_code == 200
    # A grant for one link doesn't open another.
    assert anon.get(f"/api/s/{token}/file", params={"grant": grant}).status_code == 401

    listed = client.get(f"/api/documents/{doc['id']}/shares").json()["shares"]
    assert {s["id"] for s in listed} == {open_link["id"], locked["id"]}
    assert next(s for s in listed if s["id"] == open_link["id"])["downloads"] == 1
    client.delete(f"/api/documents/{doc['id']}/shares/{locked['id']}")
    assert anon.get(f"/api/s/{token2}").status_code == 404


def test_send_by_email_and_gdpr(app_env, pdf3):
    c, client = app_env
    user = signup(client)
    doc = keep(client, pdf3)
    client.post(f"/api/documents/{doc['id']}/send", json={"email": "bob@example.com", "message": "Here you go"})
    mail = c.mailer.outbox[-1]
    assert mail["to"] == "bob@example.com" and "Here you go" in mail["text"]
    token = re.search(r"/s/([\w-]+)", mail["text"]).group(1)
    assert client.get(f"/api/s/{token}").status_code == 200
    assert c.privacy.export(user["id"])["documents"][0]["share_links"] == 1
    c.privacy.delete_account(user["id"])
    assert client.get(f"/api/s/{token}").status_code == 404
    assert not list((c.settings.storage_dir / "docs").glob("**/*.*"))
