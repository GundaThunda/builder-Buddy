"""Field guard on step/material updates, collision-safe args, and the plan download rate limit."""
from collections import deque
from collections import defaultdict

import pytest

import website_builder_buddy as bb
import website_plan_store as store
import website_safety as safety
from app_server import app


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(bb, "DATA_FILE", str(tmp_path / "blueprint.json"))
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path / "plan_store"))
    monkeypatch.setattr(store, "_download_hits", defaultdict(deque))
    monkeypatch.setattr(safety, "GENERIC_RULES", [])
    yield


def _build_with_step_and_material():
    build = bb.add_build("Test Box")["build"]
    step = bb.add_step(build["id"], "Assemble the frame")["step"]
    mat = bb.add_material(build["id"], "Pine board")["material"]
    return build["id"], step["id"], mat["id"]


# --- field guard on step and material updates ---

def test_step_update_ignores_unknown_field(isolated):
    build_id, step_id, _ = _build_with_step_and_material()
    result = bb.update_step(build_id, step_id, {"title": "Assemble", "owner": "mallory"})
    assert "error" not in result
    step = bb.get_build(build_id)["build"]["steps"][0]
    assert step["title"] == "Assemble"
    assert "owner" not in step


def test_material_update_ignores_unknown_field(isolated):
    build_id, _, mat_id = _build_with_step_and_material()
    bb.update_material(build_id, mat_id, {"qty": 2, "owner": "mallory"})
    mat = bb.get_build(build_id)["build"]["materials"][0]
    assert mat["qty"] == 2
    assert "owner" not in mat


def test_step_body_keys_named_like_arguments_do_not_crash(isolated):
    build_id, step_id, _ = _build_with_step_and_material()
    result = bb.update_step(build_id, step_id, {"build_id": "x", "step_id": "y", "title": "Frame"})
    assert result.get("step") is not None or "error" not in result
    assert bb.get_build(build_id)["build"]["steps"][0]["title"] == "Frame"


def test_material_body_keys_named_like_arguments_do_not_crash(isolated):
    build_id, _, mat_id = _build_with_step_and_material()
    bb.update_material(build_id, mat_id, {"build_id": "x", "material_id": "y", "qty": 3})
    assert bb.get_build(build_id)["build"]["materials"][0]["qty"] == 3


# --- download rate limit ---

def test_download_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setattr(store, "_download_hits", defaultdict(deque))
    monkeypatch.setattr(store, "DOWNLOAD_LIMIT", 3)
    assert [store.download_allowed("alice", "plan1", now=0) for _ in range(4)] == [True, True, True, False]


def test_download_limit_is_per_user_and_per_plan(monkeypatch):
    monkeypatch.setattr(store, "_download_hits", defaultdict(deque))
    monkeypatch.setattr(store, "DOWNLOAD_LIMIT", 1)
    assert store.download_allowed("alice", "plan1", now=0) is True
    assert store.download_allowed("alice", "plan1", now=1) is False
    assert store.download_allowed("bob", "plan1", now=1) is True
    assert store.download_allowed("alice", "plan2", now=1) is True


def test_download_limit_window_resets(monkeypatch):
    monkeypatch.setattr(store, "_download_hits", defaultdict(deque))
    monkeypatch.setattr(store, "DOWNLOAD_LIMIT", 1)
    monkeypatch.setattr(store, "DOWNLOAD_WINDOW_SECONDS", 60)
    assert store.download_allowed("alice", "plan1", now=0) is True
    assert store.download_allowed("alice", "plan1", now=30) is False
    assert store.download_allowed("alice", "plan1", now=60) is True


def test_route_returns_429_and_does_not_count(isolated, monkeypatch):
    monkeypatch.setattr(store, "DOWNLOAD_LIMIT", 2)
    import website_social_structure as ss
    import website_auth as auth
    ss.get_or_create_user("alice")
    auth.set_password("alice", "correct horse battery")
    app.config["TESTING"] = True
    with app.test_client() as c:
        tok = c.post("/auth/login", json={"user_handle": "alice",
                                          "password": "correct horse battery"}).get_json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        cid = c.post("/plans", headers=h, json={
            "steps": [{"title": "Assemble the frame", "process_type": "assembly"}]}).get_json()["content_id"]
        codes = [c.post(f"/plans/{cid}/download", headers=h).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert store.get_plan(cid)["downloads_x"] == 2
