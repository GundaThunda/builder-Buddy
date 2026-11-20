import pytest

from app_server import app


@pytest.fixture
def anon():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# Each entry: (method, path). Every one must reject an unauthenticated caller.
GATED = [
    ("POST", "/silhouette/snapshots"),
    ("DELETE", "/silhouette/snapshots/some-id"),
    ("POST", "/tips/tips"),
    ("PATCH", "/tips/tips/some-id"),
    ("DELETE", "/tips/tips/some-id"),
    ("POST", "/ron-g/ask"),
    ("GET", "/ron-g/log"),
]


@pytest.mark.parametrize("method,path", GATED)
def test_unauthenticated_request_is_rejected(anon, method, path):
    resp = anon.open(path, method=method, json={})
    assert resp.status_code == 401
