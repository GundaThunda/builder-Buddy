import pytest
import os
import website_builder_buddy as bb
from app_server import app

DATA_FILE = os.path.join(os.path.dirname(bb.__file__), "blueprint_data.json")


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


def make_build(**kwargs):
    return bb.add_build(name=kwargs.get("name", "Test Build"), **{k: v for k, v in kwargs.items() if k != "name"})


# --- add_build ---

def test_add_build_basic():
    result = make_build(name="Workbench")
    assert "build" in result
    assert result["build"]["status"] == "draft"
    assert result["build"]["steps"] == []
    assert result["build"]["cut_list"] == []


def test_add_build_empty_name():
    result = bb.add_build(name="")
    assert result["error"] == "name is required"


def test_add_build_whitespace_name():
    result = bb.add_build(name="   ")
    assert result["error"] == "name is required"


def test_add_build_with_hours():
    result = make_build(name="Cabinet", estimated_hours=12.5)
    assert result["build"]["estimated_hours"] == 12.5


def test_add_build_negative_hours():
    result = bb.add_build(name="Cabinet", estimated_hours=-1)
    assert "error" in result


def test_add_build_with_tags():
    result = make_build(name="Shelf", tags=["beginner", "storage"])
    assert "beginner" in result["build"]["tags"]


# --- get_build ---

def test_get_build():
    b = make_build(name="Dresser")["build"]
    result = bb.get_build(b["id"])
    assert result["build"]["id"] == b["id"]


def test_get_build_not_found():
    result = bb.get_build("fake-id")
    assert result["error"] == "not_found"


# --- update_build ---

def test_update_build_name():
    b = make_build(name="Old Name")["build"]
    result = bb.update_build(b["id"], name="New Name")
    assert result["build"]["name"] == "New Name"


def test_update_build_description():
    b = make_build()["build"]
    result = bb.update_build(b["id"], description="A sturdy bench")
    assert result["build"]["description"] == "A sturdy bench"


def test_update_build_empty_name_rejected():
    b = make_build()["build"]
    result = bb.update_build(b["id"], name="")
    assert "error" in result


def test_update_build_not_found():
    result = bb.update_build("fake-id", name="X")
    assert result["error"] == "not_found"


def test_update_finalized_build_rejected():
    b = make_build()["build"]
    bb.set_build_status(b["id"], "finalized")
    result = bb.update_build(b["id"], name="Changed")
    assert result["error"] == "locked"


# --- status transitions ---

def test_draft_to_active():
    b = make_build()["build"]
    result = bb.set_build_status(b["id"], "active")
    assert result["build"]["status"] == "active"


def test_active_to_finalized():
    b = make_build()["build"]
    bb.set_build_status(b["id"], "active")
    result = bb.set_build_status(b["id"], "finalized")
    assert result["build"]["status"] == "finalized"
    assert result["build"]["finalized_at"] is not None


def test_finalized_to_sold():
    b = make_build()["build"]
    bb.set_build_status(b["id"], "finalized")
    result = bb.set_build_status(b["id"], "sold")
    assert result["build"]["status"] == "sold"


def test_invalid_transition_draft_to_sold():
    b = make_build()["build"]
    result = bb.set_build_status(b["id"], "sold")
    assert "error" in result


def test_sold_cannot_transition():
    b = make_build()["build"]
    bb.set_build_status(b["id"], "finalized")
    bb.set_build_status(b["id"], "sold")
    result = bb.set_build_status(b["id"], "draft")
    assert "error" in result


def test_invalid_status_string():
    b = make_build()["build"]
    result = bb.set_build_status(b["id"], "broken")
    assert "error" in result


# --- delete_build ---

def test_delete_build():
    b = make_build()["build"]
    result = bb.delete_build(b["id"])
    assert "deleted" in result
    assert bb.get_build(b["id"])["error"] == "not_found"


def test_delete_build_not_found():
    result = bb.delete_build("fake-id")
    assert result["error"] == "not_found"


# --- list/search builds ---

def test_list_builds():
    make_build(name="A")
    make_build(name="B")
    result = bb.list_builds()
    assert result["count"] == 2


def test_list_filter_by_status():
    b = make_build(name="Active Build")["build"]
    make_build(name="Draft Build")
    bb.set_build_status(b["id"], "active")
    result = bb.list_builds(status="active")
    assert result["count"] == 1


def test_list_filter_by_tag():
    make_build(name="Tagged", tags=["pine"])
    make_build(name="Untagged")
    result = bb.list_builds(tag="pine")
    assert result["count"] == 1


def test_search_builds():
    make_build(name="Floating Shelf")
    make_build(name="Wall Cabinet")
    result = bb.search_builds("shelf")
    assert result["count"] == 1


def test_search_builds_by_description():
    b = make_build(name="Box")["build"]
    bb.update_build(b["id"], description="small pine keepsake box")
    result = bb.search_builds("keepsake")
    assert result["count"] == 1


# --- steps ---

def test_add_step():
    b = make_build()["build"]
    result = bb.add_step(b["id"], title="Mill lumber")
    assert result["step"]["order"] == 1
    assert result["step"]["completed"] is False


def test_add_step_empty_title():
    b = make_build()["build"]
    result = bb.add_step(b["id"], title="")
    assert "error" in result


def test_steps_auto_order():
    b = make_build()["build"]
    bb.add_step(b["id"], title="Step 1")
    bb.add_step(b["id"], title="Step 2")
    build = bb.get_build(b["id"])["build"]
    assert build["steps"][1]["order"] == 2


def test_complete_step():
    b = make_build()["build"]
    step = bb.add_step(b["id"], title="Cut boards")["step"]
    result = bb.complete_step(b["id"], step["id"], completed=True)
    assert result["step"]["completed"] is True
    assert result["step"]["completed_at"] is not None


def test_uncomplete_step():
    b = make_build()["build"]
    step = bb.add_step(b["id"], title="Sand")["step"]
    bb.complete_step(b["id"], step["id"], completed=True)
    result = bb.complete_step(b["id"], step["id"], completed=False)
    assert result["step"]["completed"] is False
    assert result["step"]["completed_at"] is None


def test_reorder_steps():
    b = make_build()["build"]
    s1 = bb.add_step(b["id"], title="First")["step"]
    s2 = bb.add_step(b["id"], title="Second")["step"]
    result = bb.reorder_steps(b["id"], [s2["id"], s1["id"]])
    assert result["steps"][0]["id"] == s2["id"]
    assert result["steps"][0]["order"] == 1


def test_reorder_mismatched_ids():
    b = make_build()["build"]
    bb.add_step(b["id"], title="Step")
    result = bb.reorder_steps(b["id"], ["wrong-id"])
    assert "error" in result


def test_delete_step():
    b = make_build()["build"]
    step = bb.add_step(b["id"], title="Rip boards")["step"]
    result = bb.delete_step(b["id"], step["id"])
    assert "deleted_step_id" in result


def test_delete_step_reorders_remaining():
    b = make_build()["build"]
    s1 = bb.add_step(b["id"], title="S1")["step"]
    bb.add_step(b["id"], title="S2")
    bb.delete_step(b["id"], s1["id"])
    build = bb.get_build(b["id"])["build"]
    assert build["steps"][0]["order"] == 1


def test_locked_build_blocks_step_add():
    b = make_build()["build"]
    bb.set_build_status(b["id"], "finalized")
    result = bb.add_step(b["id"], title="New Step")
    assert result["error"] == "locked"


# --- cut list ---

def test_add_cut():
    b = make_build()["build"]
    result = bb.add_cut(b["id"], material="Red Oak", qty=2, length=48.0, width=6.0, thickness=0.75)
    assert result["cut"]["material"] == "Red Oak"
    assert result["cut"]["qty"] == 2


def test_add_cut_invalid_unit():
    b = make_build()["build"]
    result = bb.add_cut(b["id"], material="Pine", unit="yards")
    assert "error" in result


def test_add_cut_invalid_qty():
    b = make_build()["build"]
    result = bb.add_cut(b["id"], material="Pine", qty=0)
    assert "error" in result


def test_add_cut_empty_material():
    b = make_build()["build"]
    result = bb.add_cut(b["id"], material="")
    assert "error" in result


def test_delete_cut():
    b = make_build()["build"]
    cut = bb.add_cut(b["id"], material="Walnut")["cut"]
    result = bb.delete_cut(b["id"], cut["id"])
    assert "deleted_cut_id" in result


def test_locked_build_blocks_cut_add():
    b = make_build()["build"]
    bb.set_build_status(b["id"], "finalized")
    result = bb.add_cut(b["id"], material="Maple")
    assert result["error"] == "locked"


def test_cut_mm_unit():
    b = make_build()["build"]
    result = bb.add_cut(b["id"], material="MDF", unit="mm", length=1200.0)
    assert result["cut"]["unit"] == "mm"


# --- required tools ---

def test_link_tool():
    b = make_build()["build"]
    result = bb.link_tool(b["id"], "tool-abc")
    assert "tool-abc" in result["required_tool_ids"]


def test_link_tool_duplicate():
    b = make_build()["build"]
    bb.link_tool(b["id"], "tool-abc")
    result = bb.link_tool(b["id"], "tool-abc")
    assert result["error"] == "tool_already_linked"


def test_unlink_tool():
    b = make_build()["build"]
    bb.link_tool(b["id"], "tool-abc")
    result = bb.unlink_tool(b["id"], "tool-abc")
    assert "tool-abc" not in result["required_tool_ids"]


def test_unlink_tool_not_linked():
    b = make_build()["build"]
    result = bb.unlink_tool(b["id"], "not-there")
    assert result["error"] == "tool_not_linked"


# --- HTTP routes ---

def test_http_add_build(client):
    r = client.post("/blueprint/builds", json={"name": "TV Stand"})
    assert r.status_code == 201
    assert r.get_json()["build"]["name"] == "TV Stand"


def test_http_get_build(client):
    r = client.post("/blueprint/builds", json={"name": "Bench"})
    bid = r.get_json()["build"]["id"]
    r2 = client.get(f"/blueprint/builds/{bid}")
    assert r2.status_code == 200


def test_http_list_builds(client):
    client.post("/blueprint/builds", json={"name": "A"})
    client.post("/blueprint/builds", json={"name": "B"})
    r = client.get("/blueprint/builds")
    assert r.get_json()["count"] == 2


def test_http_search_builds(client):
    client.post("/blueprint/builds", json={"name": "Floating Shelf"})
    r = client.get("/blueprint/builds/search?q=float")
    assert r.get_json()["count"] == 1


def test_http_search_missing_q(client):
    r = client.get("/blueprint/builds/search")
    assert r.status_code == 400


def test_http_set_status(client):
    r = client.post("/blueprint/builds", json={"name": "Cabinet"})
    bid = r.get_json()["build"]["id"]
    r2 = client.patch(f"/blueprint/builds/{bid}/status", json={"status": "active"})
    assert r2.get_json()["build"]["status"] == "active"


def test_http_add_step(client):
    r = client.post("/blueprint/builds", json={"name": "Stool"})
    bid = r.get_json()["build"]["id"]
    r2 = client.post(f"/blueprint/builds/{bid}/steps", json={"title": "Cut legs"})
    assert r2.status_code == 201


def test_http_add_cut(client):
    r = client.post("/blueprint/builds", json={"name": "Table"})
    bid = r.get_json()["build"]["id"]
    r2 = client.post(f"/blueprint/builds/{bid}/cuts",
                     json={"material": "Maple", "qty": 4, "length": 30.0, "unit": "in"})
    assert r2.status_code == 201


def test_http_delete_build(client):
    r = client.post("/blueprint/builds", json={"name": "Temp"})
    bid = r.get_json()["build"]["id"]
    r2 = client.delete(f"/blueprint/builds/{bid}")
    assert r2.status_code == 200
