import os

import pytest

import website_auth as auth
import website_social_structure as ss
from app_server import app

HANDLE = "nick"
GOOD = "correct horse battery"
GENERIC = "invalid_credentials"


@pytest.fixture(autouse=True)
def clean_data():
    for path in (auth.AUTH_DATA_FILE, ss.DATA_FILE):
        if os.path.exists(path):
            os.remove(path)
    yield
    for path in (auth.AUTH_DATA_FILE, ss.DATA_FILE):
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def clock(monkeypatch):
    state = {"t": 1_000_000.0}
    monkeypatch.setattr(auth, "_now", lambda: state["t"])
    return state


def _user(handle=HANDLE):
    ss.get_or_create_user(handle)
    assert auth.set_password(handle, GOOD) == {"user_handle": handle}


def _admin(handle="boss"):
    ss.set_admin_profile(handle, "Boss", "Boss Co", 1990, 1)
    assert auth.set_password(handle, GOOD) == {"user_handle": handle}


def _token(client, handle=HANDLE, password=GOOD):
    resp = client.post("/auth/login", json={"user_handle": handle, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["token"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- hashing ---

def test_hash_verifies_and_differs_per_salt():
    h1 = auth._hash_password(GOOD)
    h2 = auth._hash_password(GOOD)
    assert h1 != h2
    assert auth._verify_password(GOOD, h1)
    assert not auth._verify_password("wrong password here", h1)


def test_verify_rejects_malformed_hash():
    assert not auth._verify_password(GOOD, "not-a-hash")


def test_password_not_stored_in_plaintext():
    _user()
    with open(auth.AUTH_DATA_FILE) as f:
        assert GOOD not in f.read()


# --- set_password ---

def test_set_password_requires_existing_user():
    assert auth.set_password("ghost", GOOD) == {"error": "not_found"}


def test_set_password_rejects_short_password():
    ss.get_or_create_user(HANDLE)
    assert auth.set_password(HANDLE, "short") == {
        "error": f"password must be at least {auth.MIN_PASSWORD_LENGTH} characters"}


# --- login ---

def test_login_returns_token_and_expiry(client):
    _user()
    resp = client.post("/auth/login", json={"user_handle": HANDLE, "password": GOOD})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["user_handle"] == HANDLE
    assert body["token"]
    assert "expires_at" in body


def test_token_stored_only_as_digest(client):
    _user()
    token = _token(client)
    with open(auth.AUTH_DATA_FILE) as f:
        raw = f.read()
    assert token not in raw
    assert auth._token_key(token) in raw


def test_wrong_password_and_unknown_user_identical_responses(client):
    _user()
    wrong = client.post("/auth/login", json={"user_handle": HANDLE, "password": "wrong password here"})
    unknown = client.post("/auth/login", json={"user_handle": "ghost", "password": "wrong password here"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json() == {"error": GENERIC}


def test_login_rejects_non_json_body(client):
    resp = client.post("/auth/login", data="nope", content_type="text/plain")
    assert resp.status_code == 400


def test_lockout_after_five_failures_blocks_even_correct_password(clock):
    _user()
    for _ in range(auth.MAX_FAILED_LOGINS):
        assert auth.login(HANDLE, "wrong password here") == {"error": GENERIC}
    assert auth.login(HANDLE, GOOD) == {"error": GENERIC}
    clock["t"] += auth.LOCKOUT_SECONDS + 1
    assert "token" in auth.login(HANDLE, GOOD)


def test_success_resets_failure_count(clock):
    _user()
    for _ in range(auth.MAX_FAILED_LOGINS - 1):
        auth.login(HANDLE, "wrong password here")
    assert "token" in auth.login(HANDLE, GOOD)
    for _ in range(auth.MAX_FAILED_LOGINS - 1):
        auth.login(HANDLE, "wrong password here")
    assert "token" in auth.login(HANDLE, GOOD)


# --- sessions ---

def test_session_expires(client, clock):
    _user()
    token = _token(client)
    assert auth.authenticate_token(token) == HANDLE
    clock["t"] += auth.SESSION_TTL_SECONDS + 1
    assert auth.authenticate_token(token) is None
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 401


def test_logout_revokes_token(client):
    _user()
    token = _token(client)
    assert client.post("/auth/logout", headers=_bearer(token)).status_code == 200
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 401


def test_password_change_revokes_all_sessions_and_issues_new_token(client):
    _user()
    old = _token(client)
    other = _token(client)
    new_pw = "a different passphrase"
    resp = client.post("/auth/password", headers=_bearer(old),
                       json={"current_password": GOOD, "new_password": new_pw})
    assert resp.status_code == 200
    fresh = resp.get_json()["token"]
    assert client.get("/auth/me", headers=_bearer(old)).status_code == 401
    assert client.get("/auth/me", headers=_bearer(other)).status_code == 401
    assert client.get("/auth/me", headers=_bearer(fresh)).status_code == 200
    assert "token" in auth.login(HANDLE, new_pw)
    assert auth.login(HANDLE, GOOD) == {"error": GENERIC}


def test_password_change_wrong_current_is_forbidden(client):
    _user()
    token = _token(client)
    resp = client.post("/auth/password", headers=_bearer(token),
                       json={"current_password": "wrong password here",
                             "new_password": "a different passphrase"})
    assert resp.status_code == 403
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 200


def test_password_change_rejects_same_password(client):
    _user()
    token = _token(client)
    resp = client.post("/auth/password", headers=_bearer(token),
                       json={"current_password": GOOD, "new_password": GOOD})
    assert resp.status_code == 400


# --- route enforcement ---

def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_bad_token(client):
    assert client.get("/auth/me", headers=_bearer("bogus")).status_code == 401


def test_me_returns_identity_and_role(client):
    _admin()
    token = _token(client, handle="boss")
    body = client.get("/auth/me", headers=_bearer(token)).get_json()
    assert body == {"user_handle": "boss", "role": "admin"}


def test_member_cannot_set_roles(client):
    _user()
    token = _token(client)
    resp = client.post("/auth/roles/someone", headers=_bearer(token), json={"role": "admin"})
    assert resp.status_code == 403


def test_unauthenticated_cannot_set_roles(client):
    _user()
    resp = client.post("/auth/roles/nick", json={"role": "admin"})
    assert resp.status_code == 401


def test_admin_grants_role(client):
    _admin()
    _user()
    token = _token(client, handle="boss")
    resp = client.post("/auth/roles/nick", headers=_bearer(token), json={"role": "admin"})
    assert resp.status_code == 200
    assert ss.is_admin("nick")


def test_admin_set_role_unknown_user_is_404(client):
    _admin()
    token = _token(client, handle="boss")
    resp = client.post("/auth/roles/ghost", headers=_bearer(token), json={"role": "admin"})
    assert resp.status_code == 404


def test_admin_set_role_invalid_role_is_400(client):
    _admin()
    token = _token(client, handle="boss")
    resp = client.post("/auth/roles/boss", headers=_bearer(token), json={"role": "superuser"})
    assert resp.status_code == 400


# --- last-admin guard ---

def test_cannot_demote_last_admin(client):
    _admin()
    token = _token(client, handle="boss")
    resp = client.post("/auth/roles/boss", headers=_bearer(token), json={"role": "member"})
    assert resp.status_code == 409
    assert ss.is_admin("boss")


def test_can_demote_admin_when_another_admin_exists(client):
    _admin()
    _admin("second")
    token = _token(client, handle="boss")
    resp = client.post("/auth/roles/second", headers=_bearer(token), json={"role": "member"})
    assert resp.status_code == 200
    assert not ss.is_admin("second")
    assert ss.is_admin("boss")
