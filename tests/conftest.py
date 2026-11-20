import os

import pytest

import website_auth as auth
import website_social_structure as ss
from app_server import app

ADMIN_HANDLE = "boss"
ADMIN_PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def clean_auth_data():
    if os.path.exists(auth.AUTH_DATA_FILE):
        os.remove(auth.AUTH_DATA_FILE)
    yield
    if os.path.exists(auth.AUTH_DATA_FILE):
        os.remove(auth.AUTH_DATA_FILE)


@pytest.fixture(autouse=True)
def isolate_ron_g_access(tmp_path, monkeypatch):
    """Keep Ron G daily counters out of the repo file so tests cannot share allowance."""
    import website_ron_g_access as access
    monkeypatch.setattr(access, "ACCESS_FILE", str(tmp_path / "ron_g_access.json"))
    yield


@pytest.fixture
def admin_client():
    """Test client authenticated as an admin on every request."""
    app.config["TESTING"] = True
    ss.set_admin_profile(ADMIN_HANDLE, "Boss", "Boss Co", 1990, 1)
    auth.set_password(ADMIN_HANDLE, ADMIN_PASSWORD)
    c = app.test_client()
    resp = c.post("/auth/login", json={"user_handle": ADMIN_HANDLE, "password": ADMIN_PASSWORD})
    c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {resp.get_json()['token']}"
    yield c
