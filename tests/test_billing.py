import pytest

import website_billing as billing
import website_ron_g_access as access
import website_ron_g as rg
import website_social_structure as ss
import website_auth as auth
from app_server import app

CONFIG = {
    "STRIPE_SECRET_KEY": "sk_test_dummy",
    "STRIPE_WEBHOOK_SECRET": "whsec_dummy",
    "STRIPE_RON_G_PRICE_ID": "price_dummy",
    "APP_BASE_URL": "https://example.test",
}


@pytest.fixture
def configured(monkeypatch, tmp_path):
    for k, v in CONFIG.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(access, "ACCESS_FILE", str(tmp_path / "access.json"))


@pytest.fixture
def unconfigured(monkeypatch, tmp_path):
    for k in CONFIG:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(access, "ACCESS_FILE", str(tmp_path / "access.json"))


def _sub_event(event_type, status, handle="alice"):
    return {"type": event_type, "data": {"object": {"status": status, "metadata": {"handle": handle}}}}


def test_checkout_fails_closed_when_unconfigured(unconfigured):
    with pytest.raises(billing.BillingNotConfigured):
        billing.create_checkout_url("alice")


def test_checkout_sends_handle_and_price(configured, monkeypatch):
    captured = {}

    class FakeSession:
        url = "https://checkout.test/s"

    def fake_create(params):
        captured.update(params)
        return FakeSession()

    monkeypatch.setattr(billing.stripe.checkout.Session, "create", fake_create)
    assert billing.create_checkout_url("alice") == "https://checkout.test/s"
    assert captured["mode"] == "subscription"
    assert captured["client_reference_id"] == "alice"
    assert captured["subscription_data"]["metadata"]["handle"] == "alice"
    assert captured["line_items"] == [{"price": "price_dummy", "quantity": 1}]


def test_active_subscription_sets_access_and_cancel_clears_it(configured, monkeypatch):
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event",
                        lambda payload, sig, secret: _sub_event("customer.subscription.created", "active"))
    billing.handle_webhook(b"{}", "sig")
    assert access.is_subscribed("alice") is True

    monkeypatch.setattr(billing.stripe.Webhook, "construct_event",
                        lambda payload, sig, secret: _sub_event("customer.subscription.deleted", "canceled"))
    billing.handle_webhook(b"{}", "sig")
    assert access.is_subscribed("alice") is False


def test_past_due_removes_access(configured, monkeypatch):
    access.set_subscribed("alice", True)
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event",
                        lambda payload, sig, secret: _sub_event("customer.subscription.updated", "past_due"))
    billing.handle_webhook(b"{}", "sig")
    assert access.is_subscribed("alice") is False


def test_event_without_handle_is_ignored(configured, monkeypatch):
    ev = {"type": "customer.subscription.created", "data": {"object": {"status": "active", "metadata": {}}}}
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda payload, sig, secret: ev)
    assert billing.handle_webhook(b"{}", "sig") == {"ignored": "no_handle"}
    assert access.is_subscribed("alice") is False


def test_webhook_route_rejects_bad_signature(configured, monkeypatch):
    def boom(payload, sig, secret):
        raise ValueError("bad signature")
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", boom)
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.post("/ron-g/billing/webhook", data=b"{}", headers={"Stripe-Signature": "x"})
        assert r.status_code == 400
        assert access.is_subscribed("alice") is False


def test_webhook_route_503_when_unconfigured(unconfigured):
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.post("/ron-g/billing/webhook", data=b"{}")
        assert r.status_code == 503


def test_checkout_route_requires_login(configured):
    app.config["TESTING"] = True
    with app.test_client() as c:
        assert c.post("/ron-g/billing/checkout").status_code == 401
