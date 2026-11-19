import os

import pytest

import website_builder_buddy as bb
import website_toolbox as tb
from app_server import app


@pytest.fixture(autouse=True)
def clean_data():
    for path in (bb.DATA_FILE, tb.DATA_FILE):
        if os.path.exists(path):
            os.remove(path)
    yield
    for path in (bb.DATA_FILE, tb.DATA_FILE):
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def recorder(monkeypatch):
    calls = []

    def fake_log(endpoint, record_id, actor, rejected):
        calls.append({"endpoint": endpoint, "record_id": record_id,
                      "actor": actor, "rejected": dict(rejected)})

    monkeypatch.setattr(bb, "log_unknown_fields", fake_log)
    monkeypatch.setattr(tb, "log_unknown_fields", fake_log)
    return calls


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# --- regression: body key named build_id used to raise TypeError (500) ---

def test_patch_build_with_build_id_key_does_not_crash(client):
    b = bb.add_build(name="Bench")["build"]
    resp = client.patch(f"/blueprint/builds/{b['id']}",
                        json={"build_id": "spoofed", "name": "Renamed"})
    assert resp.status_code == 200
    assert resp.get_json()["build"]["name"] == "Renamed"


# --- blueprint guard ---

def test_build_unknown_field_rejected_and_logged(recorder):
    b = bb.add_build(name="Bench")["build"]
    result = bb.update_build(b["id"], {"name": "Renamed", "owner_id": "u-9"})
    assert result["build"]["name"] == "Renamed"
    assert "owner_id" not in result["build"]
    assert len(recorder) == 1
    assert recorder[0]["rejected"] == {"owner_id": "u-9"}
    assert recorder[0]["record_id"] == b["id"]


def test_build_allowed_fields_not_logged(recorder):
    b = bb.add_build(name="Bench")["build"]
    bb.update_build(b["id"], {"name": "Renamed", "notes": "ok"})
    assert recorder == []


def test_build_keyword_call_still_works(recorder):
    b = bb.add_build(name="Bench")["build"]
    assert bb.update_build(b["id"], name="Kw")["build"]["name"] == "Kw"


# --- toolbox guard ---

def test_item_unknown_field_rejected_and_logged(recorder):
    item = tb.add_item("Old Name")["item"]
    result = tb.update_item(item["id"], {"name": "New Name", "is_admin": True})
    assert result["item"]["name"] == "New Name"
    assert "is_admin" not in result["item"]
    assert recorder[-1]["rejected"] == {"is_admin": True}


def test_item_allowed_fields_not_logged(recorder):
    item = tb.add_item("Old Name")["item"]
    tb.update_item(item["id"], {"name": "New Name", "tags": ["joinery"]})
    assert recorder == []


def test_item_patch_with_item_id_key_does_not_crash(client):
    item = tb.add_item("Old Name")["item"]
    resp = client.patch(f"/toolbox/items/{item['id']}",
                        json={"item_id": "spoofed", "name": "Renamed"})
    assert resp.status_code == 200
