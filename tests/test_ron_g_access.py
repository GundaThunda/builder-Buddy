from collections import defaultdict
from datetime import datetime, timezone

import pytest

import website_ron_g as rg
import website_ron_g_access as access
import website_social_structure as ss
import website_auth as auth
from app_server import app


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(access, "ACCESS_FILE", str(tmp_path / "access.json"))
    monkeypatch.setattr(rg, "ask_ron_g", lambda question, build_id="": {"answer": "ok"})


def test_free_user_gets_15_then_429(isolated):
    for _ in range(10):
        assert access.can_ask("alice")
        access.record_ask("alice")
    assert access.can_ask("alice") is False
    assert access.remaining_today("alice") == 0


def test_subscriber_is_unlimited(isolated):
    access.set_subscribed("alice", True)
    for _ in range(40):
        access.record_ask("alice")
    assert access.can_ask("alice") is True
    assert access.remaining_today("alice") is None


def test_counter_resets_on_new_utc_day(isolated, monkeypatch):
    for _ in range(10):
        access.record_ask("alice")
    assert access.can_ask("alice") is False
    monkeypatch.setattr(access, "_today", lambda: "2099-01-01")
    assert access.can_ask("alice") is True


def test_failed_ask_does_not_count(isolated, monkeypatch):
    monkeypatch.setattr(rg, "ask_ron_g", lambda question, build_id="": {"error": "empty_question"})
    app.config["TESTING"] = True
    with app.test_client() as c:
        ss.get_or_create_user("alice")
        auth.set_password("alice", "correct horse battery")
        tok = c.post("/auth/login", json={"user_handle": "alice",
                                          "password": "correct horse battery"}).get_json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        for _ in range(20):
            c.post("/ron-g/ask", headers=h, json={"question": ""})
        assert access.remaining_today("alice") == 10


def test_route_limits_free_user_and_reports_remaining(isolated):
    app.config["TESTING"] = True
    with app.test_client() as c:
        ss.get_or_create_user("alice")
        auth.set_password("alice", "correct horse battery")
        tok = c.post("/auth/login", json={"user_handle": "alice",
                                          "password": "correct horse battery"}).get_json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        codes = [c.post("/ron-g/ask", headers=h, json={"question": "q"}).status_code for _ in range(11)]
        assert codes[:10] == [200] * 10 and codes[10] == 429
        first = c.post("/ron-g/ask", headers=h, json={"question": "q"})
        assert first.get_json()["error"] == "daily_limit_reached"


def test_only_admin_can_set_subscription(admin_client):
    r = admin_client.post("/ron-g/subscriptions/alice", json={"subscribed": True})
    assert r.status_code == 200
    assert access.is_subscribed("alice") is True
    bad = admin_client.post("/ron-g/subscriptions/alice", json={"subscribed": "yes"})
    assert bad.status_code == 400
