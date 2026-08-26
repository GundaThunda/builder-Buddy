import pytest
from app_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_404(client):
    r = client.get("/nonexistent")
    assert r.status_code == 404


def test_toolbox_prefix_exists(client):
    r = client.get("/toolbox/items")
    assert r.status_code == 200


def test_health_service_name(client):
    r = client.get("/health")
    assert r.get_json()["service"] == "builder-buddy"
