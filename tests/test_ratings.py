import os

import pytest

import website_auth as auth
import website_social_structure as ss
from app_server import app

GOOD = "correct horse battery"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) Firefox/120.0"


@pytest.fixture(autouse=True)
def clean_data():
    for path in (ss.DATA_FILE,):
        if os.path.exists(path):
            os.remove(path)
    yield
    if os.path.exists(ss.DATA_FILE):
        os.remove(ss.DATA_FILE)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _member(handle):
    ss.get_or_create_user(handle)
    assert auth.set_password(handle, GOOD) == {"user_handle": handle}


def _tok(client, handle):
    resp = client.post("/auth/login", json={"user_handle": handle, "password": GOOD})
    return resp.get_json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _publish(client, token, build_id, title="Bench"):
    return client.post("/social/published-builds", headers=_h(token),
                       json={"build_id": build_id, "title": title})


def _rate(client, token, build_id, score, ua=BROWSER_UA):
    return client.post(f"/social/published-builds/{build_id}/ratings", headers=_h(token),
                       json={"score": score}, environ_base={"HTTP_USER_AGENT": ua})


def _admin_flags(client):
    ss.set_admin_profile("boss", "Boss", "Boss Co", 1990, 1)
    auth.set_password("boss", GOOD)
    token = _tok(client, "boss")
    resp = client.get("/social/admin/rating-flags", headers=_h(token))
    assert resp.status_code == 200
    return resp.get_json()["ratings"]


# --- publishing ---

def test_publish_requires_token(client):
    assert client.post("/social/published-builds",
                       json={"build_id": "b1", "title": "Bench"}).status_code == 401


def test_publish_sets_owner_and_blocks_takeover(client):
    _member("owner")
    _member("other")
    resp = _publish(client, _tok(client, "owner"), "b1")
    assert resp.status_code == 201
    assert resp.get_json()["published_build"]["owner"] == "owner"
    assert _publish(client, _tok(client, "other"), "b1").status_code == 409


# --- rating rules ---

def test_cannot_rate_own_build(client):
    _member("owner")
    token = _tok(client, "owner")
    _publish(client, token, "b1")
    assert _rate(client, token, "b1", 5).status_code == 403


@pytest.mark.parametrize("bad", [0, 6, "5", True, None, 4.5])
def test_score_must_be_integer_1_to_5(client, bad):
    _member("owner")
    _member("rater")
    _publish(client, _tok(client, "owner"), "b1")
    resp = client.post("/social/published-builds/b1/ratings",
                       headers=_h(_tok(client, "rater")), json={"score": bad})
    assert resp.status_code == 400


def test_rating_summary_and_upsert(client):
    _member("owner")
    _member("a")
    _member("b")
    _publish(client, _tok(client, "owner"), "b1")
    assert _rate(client, _tok(client, "a"), "b1", 4).status_code == 201
    assert _rate(client, _tok(client, "b"), "b1", 2).status_code == 201
    summary = client.get("/social/published-builds/b1").get_json()
    assert summary["rating_avg"] == 3.0 and summary["rating_count"] == 2
    # Same rater again replaces their rating; count does not grow.
    _rate(client, _tok(client, "a"), "b1", 5)
    summary = client.get("/social/published-builds/b1").get_json()
    assert summary["rating_avg"] == 3.5 and summary["rating_count"] == 2


def test_rating_unknown_build_is_404(client):
    _member("rater")
    assert _rate(client, _tok(client, "rater"), "nope", 3).status_code == 404


# --- farm analytics ---

def test_bot_rating_is_likely_farmed_and_excluded(client):
    _member("owner")
    _publish(client, _tok(client, "owner"), "b1")
    _member("bot")
    # New account + automation UA = two flags -> likely_farmed, excluded from averages.
    _rate(client, _tok(client, "bot"), "b1", 1, ua="python-requests/2.31")
    summary = client.get("/social/published-builds/b1").get_json()
    assert summary["rating_count"] == 0
    flags = {r["rater"]: r for r in _admin_flags(client)}
    assert flags["bot"]["severity"] == "likely_farmed"
    assert {"new_account", "automation_client"} <= set(flags["bot"]["flags"])


def test_missing_user_agent_flagged_as_automation(client):
    _member("owner")
    _member("rater")
    _publish(client, _tok(client, "owner"), "b1")
    _rate(client, _tok(client, "rater"), "b1", 3, ua="")
    flagged = _admin_flags(client)
    assert "automation_client" in flagged[0]["flags"]


def test_rapid_fire_flagged(client):
    _member("owner")
    _member("rater")
    owner = _tok(client, "owner")
    rater = _tok(client, "rater")
    for i in range(5):
        _publish(client, owner, f"b{i}")
        _rate(client, rater, f"b{i}", 4)
    flags = [f for r in _admin_flags(client) for f in r["flags"]]
    assert "rapid_fire" in flags


def test_reciprocal_pair_flagged(client):
    _member("owner")
    _member("rater")
    owner = _tok(client, "owner")
    rater = _tok(client, "rater")
    for i in range(3):
        _publish(client, owner, f"o{i}")
        _publish(client, rater, f"r{i}")
    for i in range(3):
        _rate(client, rater, f"o{i}", 5)
    for i in range(3):
        _rate(client, owner, f"r{i}", 5)
    flags = [f for r in _admin_flags(client) for f in r["flags"]]
    assert "reciprocal_pair" in flags


def test_uniform_scores_flagged(client):
    _member("owner")
    _member("rater")
    owner = _tok(client, "owner")
    rater = _tok(client, "rater")
    for i in range(10):
        _publish(client, owner, f"b{i}")
        _rate(client, rater, f"b{i}", 3)
    flags = [f for r in _admin_flags(client) for f in r["flags"]]
    assert "uniform_scores" in flags


# --- visibility ---

def test_flags_are_admin_only(client):
    _member("member")
    assert client.get("/social/admin/rating-flags").status_code == 401
    assert client.get("/social/admin/rating-flags",
                      headers=_h(_tok(client, "member"))).status_code == 403


def test_rater_response_does_not_expose_flags(client):
    _member("owner")
    _member("rater")
    _publish(client, _tok(client, "owner"), "b1")
    resp = _rate(client, _tok(client, "rater"), "b1", 4)
    assert "flags" not in resp.get_json()
    assert "severity" not in resp.get_json()


def test_user_rating_summary(client):
    assert client.get("/social/users/ghost/rating-summary").status_code == 404
    _member("owner")
    _member("rater")
    _publish(client, _tok(client, "owner"), "b1")
    _rate(client, _tok(client, "rater"), "b1", 4)
    body = client.get("/social/users/owner/rating-summary").get_json()
    assert body["published_builds"] == 1
    assert body["rating_count"] == 1 and body["rating_avg"] == 4.0
