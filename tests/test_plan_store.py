import json
import os

import pytest

import migrate_plan_store as migrate
import website_auth as auth
import website_plan_store as store
import website_social_structure as ss
from app_server import app

GOOD = "correct horse battery"


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path / "plan_store"))
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _body(**overrides):
    body = {
        "steps": [{"title": "Cut sides", "process_type": "crosscutting", "estimated_minutes": 10},
                  {"title": "Glue up", "process_type": "gluing", "estimated_minutes": 30}],
        "materials": [{"name": "Pine 1x12", "qty": 2, "unit": "bf", "species_or_grade": "#2"},
                      {"name": "Screws", "qty": 1, "unit": "bag"}],
        "dimensions": {"width_in": 24},
    }
    body.update(overrides)
    return body


def _member(handle):
    ss.get_or_create_user(handle)
    auth.set_password(handle, GOOD)


def _tok(client, handle):
    return client.post("/auth/login", json={"user_handle": handle, "password": GOOD}).get_json()["token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# --- canonical hash ---

def test_hash_ignores_ids_timestamps_and_unknown_keys():
    a = _body()
    b = _body()
    b["steps"][0].update({"id": "x1", "order": 1, "created_at": "2026-01-01", "bogus": True})
    b["materials"][0]["id"] = "m9"
    assert store.content_hash(a) == store.content_hash(b)


def test_material_order_does_not_change_hash_but_step_order_does():
    a = _body()
    reordered_materials = _body(materials=list(reversed(_body()["materials"])))
    assert store.content_hash(a) == store.content_hash(reordered_materials)
    reordered_steps = _body(steps=list(reversed(_body()["steps"])))
    assert store.content_hash(a) != store.content_hash(reordered_steps)


# --- validation ---

@pytest.mark.parametrize("bad", [
    None, [], {"steps": "nope"}, {"steps": [{"notes": "no title"}]},
    {"materials": [{"qty": 1}]}, {}, {"steps": [], "materials": []},
    {"steps": [{"title": "x"}], "dimensions": []},
])
def test_invalid_bodies_rejected(bad):
    assert "error" in store.submit_plan("alice", bad)


# --- reposts and attribution ---

def test_identical_plan_stored_once_and_keeps_original_author():
    first = store.submit_plan("alice", _body())
    second = store.submit_plan("bob", _body())
    assert first["status"] == "new"
    assert second["status"] == "exact_duplicate"
    assert second["content_id"] == first["content_id"]
    plan = store.get_plan(first["content_id"])
    assert plan["original_author"] == "alice"
    assert plan["post_count"] == 2


def test_only_one_content_file_for_reposts():
    first = store.submit_plan("alice", _body())
    store.submit_plan("bob", _body())
    files = [f for f in os.listdir(store.STORE_DIR) if f.endswith(".json") and f != "index.json"]
    assert files == [f"{first['content_id']}.json"]


# --- downloads ---

def test_repost_downloads_count_toward_original_x():
    cid = store.submit_plan("alice", _body())["content_id"]
    store.submit_plan("bob", _body())
    store.record_download(cid)
    store.record_download(cid)
    plan = store.get_plan(cid)
    assert plan["downloads_x"] == 2
    assert plan["downloads_y"] == 0


# --- branches ---

def test_branch_stored_in_own_file_with_its_uploader():
    cid = store.submit_plan("alice", _body())["content_id"]
    tweak = _body(dimensions={"width_in": 26})
    result = store.add_branch("bob", cid, tweak)
    assert "branch_id" in result
    plan = store.get_plan(cid)
    assert plan["original_author"] == "alice"
    assert plan["branches"][0]["uploader"] == "bob"
    assert os.path.exists(os.path.join(store.STORE_DIR, f"{cid}.json"))


def test_identical_branch_refused_as_exact_duplicate():
    cid = store.submit_plan("alice", _body())["content_id"]
    assert store.add_branch("bob", cid, _body())["error"] == "exact_duplicate"


def test_same_branch_twice_refused():
    cid = store.submit_plan("alice", _body())["content_id"]
    tweak = _body(dimensions={"width_in": 26})
    store.add_branch("bob", cid, tweak)
    assert store.add_branch("carol", cid, tweak)["error"] == "duplicate_branch"


def test_branch_downloads_roll_into_y_not_x():
    cid = store.submit_plan("alice", _body())["content_id"]
    bid = store.add_branch("bob", cid, _body(dimensions={"width_in": 26}))["branch_id"]
    store.record_download(cid, bid)
    store.record_download(cid, bid)
    plan = store.get_plan(cid)
    assert plan["downloads_y"] == 2
    assert plan["downloads_x"] == 0
    assert plan["branches"][0]["downloads"] == 2


def test_unknown_content_or_branch_is_not_found():
    assert store.get_plan("not-a-uuid")["error"] == "not_found"
    assert store.record_download("00000000-0000-0000-0000-000000000000")["error"] == "not_found"


# --- routes ---

def test_submit_requires_token(client):
    assert client.post("/plans", json=_body()).status_code == 401


def test_member_submits_and_reposts_via_routes(client):
    _member("alice")
    _member("bob")
    a = client.post("/plans", headers=_h(_tok(client, "alice")), json=_body())
    b = client.post("/plans", headers=_h(_tok(client, "bob")), json=_body())
    assert a.status_code == 201 and a.get_json()["status"] == "new"
    assert b.get_json()["status"] == "exact_duplicate"


def test_branch_route_status_codes(client):
    _member("alice")
    _member("bob")
    cid = client.post("/plans", headers=_h(_tok(client, "alice")), json=_body()).get_json()["content_id"]
    bob = _h(_tok(client, "bob"))
    assert client.post(f"/plans/{cid}/branches", headers=bob, json=_body()).status_code == 409
    assert client.post(f"/plans/{cid}/branches", headers=bob,
                       json=_body(dimensions={"width_in": 26})).status_code == 201
    assert client.post("/plans/not-a-uuid/branches", headers=bob, json=_body()).status_code == 404


def test_download_route_requires_token_and_counts(client):
    _member("alice")
    _member("bob")
    cid = client.post("/plans", headers=_h(_tok(client, "alice")), json=_body()).get_json()["content_id"]
    assert client.post(f"/plans/{cid}/download").status_code == 401
    resp = client.post(f"/plans/{cid}/download", headers=_h(_tok(client, "bob")))
    assert resp.get_json()["downloads_x"] == 1


def test_public_plan_view(client):
    _member("alice")
    cid = client.post("/plans", headers=_h(_tok(client, "alice")), json=_body()).get_json()["content_id"]
    resp = client.get(f"/plans/{cid}")
    assert resp.status_code == 200
    assert resp.get_json()["original_author"] == "alice"
    assert client.get("/plans/..%2Fsecrets").status_code == 404


# --- migration ---

def _blueprint_build(build_id, **overrides):
    build = {
        "id": build_id,
        "steps": [{"id": "s1", "order": 1, "title": "Cut sides", "process_type": "crosscutting",
                   "estimated_minutes": 10, "notes": "", "alternatives": ""}],
        "materials": [{"id": "m1", "name": "Pine 1x12", "qty": 2, "unit": "bf",
                       "species_or_grade": "#2", "dimensions": {}, "cost_per_unit": 0,
                       "vendor": "", "notes": "", "sourced": False}],
        "dimensions": {"width_in": 24},
    }
    build.update(overrides)
    return build


def test_migration_dry_run_writes_nothing():
    social = {"published_builds": {"b1": {"owner": "alice"}}}
    blueprint = {"builds": {"b1": _blueprint_build("b1")}}
    report = migrate.plan_migration(social, blueprint, apply=False)
    assert report["migrated_new"] == 1
    assert report["dry_run"] is True
    assert not os.path.exists(os.path.join(store.STORE_DIR, "index.json"))


def test_migration_apply_attributes_to_posting_owner():
    social = {"published_builds": {"b1": {"owner": "alice"}, "b2": {"owner": "bob"}}}
    blueprint = {"builds": {"b1": _blueprint_build("b1"), "b2": _blueprint_build("b2")}}
    report = migrate.plan_migration(social, blueprint, apply=True)
    assert report["migrated_reposts"] == 1  # identical bodies collapse to one content record
    idx = store._load_index()
    cid = next(iter(idx["by_hash"].values()))
    assert store.get_plan(cid)["original_author"] == "alice"


def test_unposted_and_missing_builds_are_skipped():
    social = {"published_builds": {"gone": {"owner": "alice"}}}
    blueprint = {"builds": {}}
    report = migrate.plan_migration(social, blueprint, apply=True)
    assert report["skipped_missing_build"] == ["gone"]
    assert report["migrated_new"] == 0


def test_backup_copies_existing_files(tmp_path):
    src = tmp_path / "blueprint_data.json"
    src.write_text(json.dumps({"builds": {}}))
    copies = migrate.backup([str(src), str(tmp_path / "missing.json")], str(tmp_path / "bk"))
    assert len(copies) == 1
    assert os.path.exists(copies[0])
