"""Record ownership: builders own their blueprints and toolbox items; admins can act on any record."""
import pytest

import website_auth as auth
import website_builder_buddy as bb
import website_social_structure as ss
import website_toolbox as tb
from app_server import app


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(bb, "DATA_FILE", str(tmp_path / "blueprint.json"))
    monkeypatch.setattr(tb, "DATA_FILE", str(tmp_path / "toolbox.json"))
    yield


def _login(c, handle):
    ss.get_or_create_user(handle)
    auth.set_password(handle, "correct horse battery")
    tok = c.post("/auth/login", json={"user_handle": handle,
                                      "password": "correct horse battery"}).get_json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def members(isolated):
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield {"alice": _login(c, "alice"), "bob": _login(c, "bob")}, c


def test_creator_is_stamped_as_owner_and_body_cannot_set_owner(members):
    h, c = members
    r = c.post("/blueprint/builds", headers=h["alice"], json={"name": "Desk", "owner": "bob"})
    assert r.status_code == 201
    assert r.get_json()["build"]["owner"] == "alice"


def test_non_owner_cannot_edit_or_delete_a_build(members):
    h, c = members
    bid = c.post("/blueprint/builds", headers=h["alice"], json={"name": "Desk"}).get_json()["build"]["id"]
    assert c.patch(f"/blueprint/builds/{bid}", headers=h["bob"], json={"name": "x"}).status_code == 403
    assert c.delete(f"/blueprint/builds/{bid}", headers=h["bob"]).status_code == 403
    assert c.post(f"/blueprint/builds/{bid}/steps", headers=h["bob"], json={"title": "s"}).status_code == 403


def test_owner_can_edit_their_build(members):
    h, c = members
    bid = c.post("/blueprint/builds", headers=h["alice"], json={"name": "Desk"}).get_json()["build"]["id"]
    assert c.patch(f"/blueprint/builds/{bid}", headers=h["alice"], json={"name": "Desk v2"}).status_code == 200


def test_legacy_build_without_owner_is_admin_only(members, admin_client):
    h, c = members
    data = bb._load()
    data["builds"]["legacy"] = {"id": "legacy", "name": "Old", "steps": [], "materials": [], "tools": []}
    bb._save(data)
    assert c.patch("/blueprint/builds/legacy", headers=h["alice"], json={"name": "x"}).status_code == 403


def test_non_owner_cannot_edit_a_toolbox_item(members):
    h, c = members
    iid = c.post("/toolbox/items", headers=h["alice"], json={"name": "Chisel", "type": "tool"}).get_json()["item"]["id"]
    assert c.patch(f"/toolbox/items/{iid}", headers=h["bob"], json={"name": "x"}).status_code == 403
    assert c.delete(f"/toolbox/items/{iid}", headers=h["bob"]).status_code == 403
    assert c.patch(f"/toolbox/items/{iid}", headers=h["alice"], json={"name": "Chisel 2"}).status_code == 200


def test_admin_can_act_on_any_record(members, admin_client):
    h, c = members
    bid = c.post("/blueprint/builds", headers=h["alice"], json={"name": "Desk"}).get_json()["build"]["id"]
    assert admin_client.patch(f"/blueprint/builds/{bid}", json={"name": "Admin edit"}).status_code == 200


def test_owner_field_cannot_be_changed_by_update(members):
    h, c = members
    bid = c.post("/blueprint/builds", headers=h["alice"], json={"name": "Desk"}).get_json()["build"]["id"]
    c.patch(f"/blueprint/builds/{bid}", headers=h["alice"], json={"owner": "bob"})
    assert bb.get_build(bid)["build"]["owner"] == "alice"
