"""
Payment tests (Razorpay): the frontend can never mark a payment as successful,
the price comes from the database, signatures are verified, verifying twice
grants nothing twice, and webhooks are signed and idempotent.

The Razorpay network calls are replaced by fakes. Signatures are computed with
the same HMAC rule Razorpay uses, so signature checking is tested for real.
"""

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.credit_transaction import CreditTransaction
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.webhook_event import WebhookEvent
from app.services.payments import razorpay_client


def sign_payment(order_id: str, payment_id: str) -> str:
    return hmac.new(
        settings.razorpay_key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


def sign_webhook(body: bytes) -> str:
    return hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def razorpay(monkeypatch):
    """Fake Razorpay: orders are created locally; fetch_payment reports what the test sets."""

    class Fake:
        def __init__(self):
            self.payments: dict[str, dict] = {}
            self.created: list[dict] = []

    fake = Fake()

    def create_order(*, amount, currency, receipt, notes=None):
        order = {"id": f"order_{uuid.uuid4().hex[:14]}", "amount": amount, "currency": currency, "receipt": receipt}
        fake.created.append(order)
        return order

    monkeypatch.setattr(razorpay_client, "create_order", create_order)
    monkeypatch.setattr(razorpay_client, "fetch_payment", lambda pid: fake.payments[pid])
    return fake


def order_for(client, account, plan="PRO"):
    r = client.post("/api/v1/payments/create-order", headers=account.headers, json={"plan_code": plan})
    assert r.status_code == 200, r.text
    return r.json()


def captured(razorpay, order, payment_id=None, amount=None, currency="INR"):
    pid = payment_id or f"pay_{uuid.uuid4().hex[:14]}"
    razorpay.payments[pid] = {
        "id": pid, "order_id": order["order_id"], "status": "captured",
        "amount": order["amount"] if amount is None else amount, "currency": currency, "method": "upi",
    }
    return pid


def verify(client, account, order, pid, signature=None):
    return client.post(
        "/api/v1/payments/verify",
        headers=account.headers,
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": pid,
            "razorpay_signature": signature or sign_payment(order["order_id"], pid),
        },
    )


def credits(client, account):
    return client.get("/api/v1/usage", headers=account.headers).json()


# ---------------- create order ----------------
def test_create_order_uses_database_price(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    assert order["amount"] == 44900 and order["currency"] == "INR"
    assert order["key_id"] == settings.razorpay_key_id
    assert "secret" not in json.dumps(order).lower()


def test_price_in_request_is_ignored(client, user_a, razorpay):
    r = client.post("/api/v1/payments/create-order", headers=user_a.headers,
                    json={"plan_code": "PRO", "amount": 1})
    assert r.json()["amount"] == 44900


def test_price_follows_database_change(client, user_a, razorpay, db):
    db.execute(Plan.__table__.update().where(Plan.code == "GO").values(price_amount=12300))
    db.commit()
    assert order_for(client, user_a, "GO")["amount"] == 12300


def test_free_and_unknown_plans_cannot_be_bought(client, user_a, razorpay):
    assert client.post("/api/v1/payments/create-order", headers=user_a.headers,
                       json={"plan_code": "FREE"}).status_code == 402
    assert client.post("/api/v1/payments/create-order", headers=user_a.headers,
                       json={"plan_code": "NOPE"}).status_code == 404


def test_create_order_requires_auth(client):
    assert client.post("/api/v1/payments/create-order", json={"plan_code": "PRO"}).status_code == 401


# ---------------- verify ----------------
def test_verified_payment_activates_plan_and_credits(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    pid = captured(razorpay, order)
    r = verify(client, user_a, order, pid)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PAID" and body["already_processed"] is False
    assert body["subscription"]["plan"]["code"] == "PRO"
    assert credits(client, user_a)["plan_code"] == "PRO"
    assert credits(client, user_a)["limit"] == 100


def test_frontend_cannot_fake_success_without_valid_signature(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    pid = captured(razorpay, order)
    r = verify(client, user_a, order, pid, signature="f" * 64)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "PAYMENT_VERIFICATION_FAILED"
    assert credits(client, user_a)["plan_code"] == "FREE"


def test_signature_for_a_different_payment_is_rejected(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    pid = captured(razorpay, order)
    r = verify(client, user_a, order, pid, signature=sign_payment(order["order_id"], "pay_other"))
    assert r.status_code == 400
    assert credits(client, user_a)["plan_code"] == "FREE"


def test_amount_mismatch_is_rejected(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    pid = captured(razorpay, order, amount=100)   # paid far too little
    assert verify(client, user_a, order, pid).status_code == 400
    assert credits(client, user_a)["plan_code"] == "FREE"


def test_uncaptured_payment_does_not_activate(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    pid = captured(razorpay, order)
    razorpay.payments[pid]["status"] = "authorized"
    assert verify(client, user_a, order, pid).status_code == 400
    assert credits(client, user_a)["plan_code"] == "FREE"


def test_verifying_twice_grants_once(client, user_a, razorpay, db):
    order = order_for(client, user_a, "GO")
    pid = captured(razorpay, order)
    first = verify(client, user_a, order, pid).json()
    second = verify(client, user_a, order, pid).json()
    assert first["already_processed"] is False and second["already_processed"] is True
    assert credits(client, user_a)["limit"] == 30 and credits(client, user_a)["remaining"] == 30
    grants = db.scalars(select(CreditTransaction).where(
        CreditTransaction.idempotency_key == f"grant:payment:{pid}")).all()
    assert len(grants) == 1


def test_other_user_cannot_verify_my_order(client, user_a, user_b, razorpay):
    order = order_for(client, user_a, "PRO")
    pid = captured(razorpay, order)
    assert verify(client, user_b, order, pid).status_code == 404
    assert credits(client, user_b)["plan_code"] == "FREE"


def test_one_payment_id_cannot_pay_two_orders(client, user_a, razorpay):
    first, second = order_for(client, user_a, "GO"), order_for(client, user_a, "GO")
    pid = captured(razorpay, first)
    assert verify(client, user_a, first, pid).status_code == 200
    razorpay.payments[pid]["order_id"] = second["order_id"]
    assert verify(client, user_a, second, pid).status_code == 400


def test_payment_history(client, user_a, razorpay):
    order = order_for(client, user_a, "GO")
    verify(client, user_a, order, captured(razorpay, order))
    order_for(client, user_a, "PRO")   # abandoned: never paid
    history = client.get("/api/v1/payments", headers=user_a.headers).json()
    assert history["total"] == 1 and history["items"][0]["status"] == "PAID"


# ---------------- webhooks ----------------
def webhook(client, event, order_id, payment_id, event_id=None, signature=None, amount=44900, status="captured"):
    body = json.dumps({
        "event": event,
        "payload": {"payment": {"entity": {
            "id": payment_id, "order_id": order_id, "status": status,
            "amount": amount, "currency": "INR", "method": "card",
        }}},
    }).encode()
    return client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": signature or sign_webhook(body),
            "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex[:10]}",
            "Content-Type": "application/json",
        },
    )


def test_webhook_rejects_bad_or_missing_signature(client, user_a, razorpay, db):
    order = order_for(client, user_a, "PRO")
    assert webhook(client, "payment.captured", order["order_id"], "pay_x1234", signature="0" * 64).status_code == 400
    body = b"{}"
    assert client.post("/api/v1/webhooks/razorpay", content=body).status_code == 400
    assert credits(client, user_a)["plan_code"] == "FREE"
    assert db.scalars(select(WebhookEvent)).all() == []   # nothing stored for forged calls


def test_webhook_rejected_when_secret_not_configured(client, user_a, razorpay, monkeypatch):
    order = order_for(client, user_a, "PRO")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "")
    r = webhook(client, "payment.captured", order["order_id"], "pay_x1234", signature="anything")
    assert r.status_code == 400


def test_signed_webhook_activates_plan(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    r = webhook(client, "payment.captured", order["order_id"], "pay_hook12345")
    assert r.status_code == 200 and r.json()["outcome"] == "processed"
    assert credits(client, user_a)["plan_code"] == "PRO"


def test_duplicate_webhook_is_processed_once(client, user_a, razorpay, db):
    order = order_for(client, user_a, "GO")
    first = webhook(client, "payment.captured", order["order_id"], "pay_dup123456", event_id="evt_same", amount=19900)
    second = webhook(client, "payment.captured", order["order_id"], "pay_dup123456", event_id="evt_same", amount=19900)
    assert first.json()["outcome"] == "processed" and second.json()["outcome"] == "duplicate"
    assert len(db.scalars(select(WebhookEvent)).all()) == 1
    assert credits(client, user_a)["remaining"] == 30


def test_webhook_and_verify_together_grant_once(client, user_a, razorpay):
    order = order_for(client, user_a, "GO")
    pid = captured(razorpay, order)
    webhook(client, "payment.captured", order["order_id"], pid, amount=19900)
    again = verify(client, user_a, order, pid).json()
    assert again["already_processed"] is True
    assert credits(client, user_a)["remaining"] == 30


def test_webhook_amount_mismatch_does_not_activate(client, user_a, razorpay):
    order = order_for(client, user_a, "PRO")
    webhook(client, "payment.captured", order["order_id"], "pay_cheap1234", amount=100)
    assert credits(client, user_a)["plan_code"] == "FREE"


def test_failed_webhook_never_undoes_a_paid_payment(client, user_a, razorpay, db):
    order = order_for(client, user_a, "GO")
    verify(client, user_a, order, captured(razorpay, order))
    webhook(client, "payment.failed", order["order_id"], "pay_late12345", status="failed")
    payment = db.scalar(select(Payment).where(Payment.razorpay_order_id == order["order_id"]))
    db.refresh(payment)
    assert payment.status == "PAID"
    assert credits(client, user_a)["plan_code"] == "GO"


def test_unknown_event_is_recorded_and_ignored(client, user_a):
    body = json.dumps({"event": "refund.created", "payload": {}}).encode()
    r = client.post("/api/v1/webhooks/razorpay", content=body,
                    headers={"X-Razorpay-Signature": sign_webhook(body), "X-Razorpay-Event-Id": "evt_unknown1"})
    assert r.status_code == 200 and r.json()["outcome"] == "ignored"


# ---------------- plans ----------------
def test_plans_are_public_and_from_database(client):
    r = client.get("/api/v1/subscriptions/plans")
    assert r.status_code == 200
    assert [p["code"] for p in r.json()] == ["FREE", "GO", "PRO"]
    assert r.json()[2]["price"] == 449.0 and r.json()[2]["is_popular"] is True


def test_current_plan_is_marked_when_signed_in(client, user_a):
    plans = client.get("/api/v1/subscriptions/plans", headers=user_a.headers).json()
    assert [p["code"] for p in plans if p["is_current"]] == ["FREE"]


def test_there_is_no_self_activation_route(client, user_a):
    assert client.post("/api/v1/subscriptions/upgrade", headers=user_a.headers, json={"plan": "PRO"}).status_code in (404, 405)
