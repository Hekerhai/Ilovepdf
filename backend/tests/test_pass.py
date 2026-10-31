import hashlib
import hmac
import json
from datetime import timedelta

from app.infra.db import Subscription, as_utc, utcnow
from tests.test_api import signup


def paid(client, user_id, link_id):
    payload = json.dumps({
        "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {
            "id": link_id, "notes": {"kind": "pass", "owner_type": "user", "owner_id": user_id, "plan_id": "pro"},
        }}},
    }).encode()  # fmt: skip
    sig = hmac.new(b"whsec", payload, hashlib.sha256).hexdigest()
    return client.post("/api/billing/webhooks/razorpay", content=payload, headers={"X-Razorpay-Signature": sig})


def test_week_pass_gives_pro_then_expires(app_env):
    c, client = app_env
    user = signup(client)
    assert client.get("/api/billing/plans").json()["pass"] == {"plan": "pro", "days": 7, "usd": 300, "inr": 19900}
    assert client.post("/api/billing/pass", json={"provider": "stripe"}).status_code == 503  # not configured here

    assert paid(client, user["id"], "plink_1").json()["kind"] == "paid"
    assert client.get("/api/auth/session").json()["plan"]["id"] == "pro"
    paid(client, user["id"], "plink_1")  # a retried webhook doesn't add another week
    paid(client, user["id"], "plink_2")  # a second pass extends the first
    with c.db.session() as s:
        ends = sorted(as_utc(x.current_period_end) for x in s.query(Subscription).filter_by(status="pass"))
    assert len(ends) == 2 and timedelta(days=13) < ends[1] - utcnow() < timedelta(days=14, minutes=1)

    with c.db.session() as s:
        for sub in s.query(Subscription).filter_by(status="pass"):
            sub.current_period_end = utcnow() - timedelta(minutes=1)
    assert client.get("/api/auth/session").json()["plan"]["id"] == "free"
    # A pass can't be "cancelled" like a subscription, and doesn't count as an active one.
    subs = client.get("/api/billing/subscriptions").json()["subscriptions"]
    assert {s["status"] for s in subs} == {"pass"}
