import pytest
import os
import website_social_structure as ss
from app_server import app

DATA_FILE = os.path.join(os.path.dirname(ss.__file__), "social_data.json")
HANDLE = "test-admin"


@pytest.fixture(autouse=True)
def clean_data():
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)
    yield
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _set_admin():
    return ss.set_admin_profile(HANDLE, "Test Admin", "Test Company", 1990, 1)


def test_set_admin_profile_creates_admin_with_fields():
    result = _set_admin()
    assert result == {"user_handle": HANDLE, "role": "admin"}
    data = ss._load()
    user = data["users"][HANDLE]
    assert user["role"] == "admin"
    assert user["profile"] == {
        "display_name": "Test Admin",
        "company": "Test Company",
        "birth_year": 1990,
        "birth_month": 1,
    }


def test_is_admin_true_for_admin_false_otherwise():
    _set_admin()
    ss.get_or_create_user("plain-member")
    assert ss.is_admin(HANDLE) is True
    assert ss.is_admin("plain-member") is False
    assert ss.is_admin("nobody-here") is False


def test_profile_rejects_bad_input():
    assert "error" in ss.set_admin_profile(HANDLE, "  ", "X", 1990, 1)
    assert "error" in ss.set_admin_profile(HANDLE, "Test", "X", 1990, 0)
    assert "error" in ss.set_admin_profile(HANDLE, "Test", "X", 1990, 13)
    assert "error" in ss.set_admin_profile(HANDLE, "Test", "X", 3000, 1)
    assert "error" in ss.set_admin_profile(HANDLE, "Test", "X", True, 1)
    assert "error" in ss.set_admin_profile(HANDLE, "Test", "X", "1990", 1)
    assert "error" in ss.set_admin_profile("", "Test", "X", 1990, 1)
    assert ss.is_admin(HANDLE) is False


def test_post_users_does_not_leak_profile(client):
    _set_admin()
    resp = client.post(f"/social/users/{HANDLE}")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 201
    assert "Test Company" not in body
    assert "profile" not in body
    assert "role" not in body


def test_get_users_does_not_leak_profile(client):
    _set_admin()
    body = client.get(f"/social/users/{HANDLE}").get_data(as_text=True)
    assert "Test Company" not in body
    assert "1990" not in body


def test_leaderboard_does_not_leak_profile(client):
    _set_admin()
    body = client.get("/social/leaderboard").get_data(as_text=True)
    assert "Test Company" not in body
    assert "1990" not in body


def test_points_route_cannot_elevate_role(client):
    ss.get_or_create_user(HANDLE)
    client.post(f"/social/users/{HANDLE}/points",
                json={"event": "tool_added", "role": "admin"})
    assert ss.is_admin(HANDLE) is False
