import pytest
import os
import website_builder_buddy as bb
import website_silhouette as sil
from app_server import app

BB_DATA = os.path.join(os.path.dirname(bb.__file__), "blueprint_data.json")
SIL_DATA = os.path.join(os.path.dirname(sil.__file__), "silhouette_data.json")


@pytest.fixture(autouse=True)
def clean_data():
    for f in (BB_DATA, SIL_DATA):
        if os.path.exists(f):
            os.remove(f)
    yield
    for f in (BB_DATA, SIL_DATA):
        if os.path.exists(f):
            os.remove(f)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def build():
    b = bb.add_build(name="Adirondack Chair", description="Classic outdoor chair",
                     estimated_hours=8.0, tags=["outdoor", "pine"])["build"]
    bb.add_step(b["id"], title="Mill lumber")
    s2 = bb.add_step(b["id"], title="Cut to length")["step"]
    bb.complete_step(b["id"], s2["id"], completed=True)
    bb.add_cut(b["id"], material="Pine", qty=4, length=36.0, width=4.0, thickness=0.75, unit="in")
    bb.add_cut(b["id"], material="Pine", qty=2, length=24.0, width=6.0, thickness=0.75, unit="in")
    bb.add_cut(b["id"], material="Oak", qty=1, length=18.0, width=4.0, thickness=1.5, unit="in")
    bb.link_tool(b["id"], "tool-table-saw")
    bb.link_tool(b["id"], "tool-drill")
    return b


# --- generate_overview ---

def test_overview_basic(build):
    result = sil.generate_overview(build["id"])
    assert "overview" in result
    assert result["overview"]["name"] == "Adirondack Chair"


def test_overview_progress(build):
    ov = sil.generate_overview(build["id"])["overview"]
    assert ov["total_steps"] == 2
    assert ov["completed_steps"] == 1
    assert ov["progress_pct"] == 50.0


def test_overview_not_found():
    result = sil.generate_overview("bad-id")
    assert result["error"] == "not_found"


def test_overview_zero_steps():
    b = bb.add_build(name="Empty Build")["build"]
    ov = sil.generate_overview(b["id"])["overview"]
    assert ov["progress_pct"] == 0.0


# --- generate_step_list ---

def test_step_list_ordered(build):
    result = sil.generate_step_list(build["id"])
    steps = result["steps"]
    assert steps[0]["order"] == 1
    assert steps[1]["order"] == 2


def test_step_list_totals(build):
    result = sil.generate_step_list(build["id"])
    assert result["total"] == 2
    assert result["completed"] == 1


def test_step_list_not_found():
    result = sil.generate_step_list("bad-id")
    assert "error" in result


# --- generate_cut_list ---

def test_cut_list_contains_all(build):
    result = sil.generate_cut_list(build["id"])
    assert len(result["cut_list"]) == 3


def test_cut_list_total_pieces(build):
    result = sil.generate_cut_list(build["id"])
    assert result["total_pieces"] == 7  # 4 + 2 + 1


def test_cut_list_grouped_by_material(build):
    result = sil.generate_cut_list(build["id"])
    assert "Pine" in result["by_material"]
    assert "Oak" in result["by_material"]
    assert len(result["by_material"]["Pine"]) == 2


def test_cut_list_not_found():
    result = sil.generate_cut_list("bad-id")
    assert "error" in result


# --- generate_tools_list ---

def test_tools_list(build):
    result = sil.generate_tools_list(build["id"])
    assert result["tool_count"] == 2
    assert "tool-table-saw" in result["required_tool_ids"]


def test_tools_list_empty():
    b = bb.add_build(name="No-Tool Build")["build"]
    result = sil.generate_tools_list(b["id"])
    assert result["tool_count"] == 0


def test_tools_list_not_found():
    result = sil.generate_tools_list("bad-id")
    assert "error" in result


# --- generate_presentation ---

def test_full_presentation(build):
    result = sil.generate_presentation(build["id"])
    assert "presentation" in result
    p = result["presentation"]
    assert "overview" in p
    assert "steps" in p
    assert "cut_list" in p
    assert "required_tool_ids" in p


def test_presentation_not_found():
    result = sil.generate_presentation("bad-id")
    assert "error" in result


# --- snapshots ---

def test_create_snapshot(build):
    result = sil.create_snapshot(build["id"], label="v1")
    assert "snapshot" in result
    assert result["snapshot"]["label"] == "v1"
    assert result["snapshot"]["build_id"] == build["id"]


def test_snapshot_is_immutable_capture(build):
    sil.create_snapshot(build["id"], label="before")
    bb.add_step(build["id"], title="New Step Added After")
    snaps = sil.list_snapshots(build["id"])["snapshots"]
    content_steps = snaps[0]["content"]["steps"]
    assert len(content_steps) == 2  # snapshot frozen before new step


def test_get_snapshot(build):
    snap_id = sil.create_snapshot(build["id"])["snapshot"]["id"]
    result = sil.get_snapshot(snap_id)
    assert result["snapshot"]["id"] == snap_id


def test_get_snapshot_not_found():
    result = sil.get_snapshot("bad-id")
    assert result["error"] == "not_found"


def test_list_snapshots_all(build):
    b2 = bb.add_build(name="Other Build")["build"]
    sil.create_snapshot(build["id"])
    sil.create_snapshot(b2["id"])
    result = sil.list_snapshots()
    assert result["count"] == 2


def test_list_snapshots_by_build(build):
    b2 = bb.add_build(name="Other")["build"]
    sil.create_snapshot(build["id"])
    sil.create_snapshot(b2["id"])
    result = sil.list_snapshots(build["id"])
    assert result["count"] == 1


def test_delete_snapshot(build):
    snap_id = sil.create_snapshot(build["id"])["snapshot"]["id"]
    sil.delete_snapshot(snap_id)
    assert sil.get_snapshot(snap_id)["error"] == "not_found"


# --- HTTP routes ---

def test_http_overview(client, build):
    r = client.get(f"/silhouette/overview/{build['id']}")
    assert r.status_code == 200
    assert r.get_json()["overview"]["name"] == "Adirondack Chair"


def test_http_steps(client, build):
    r = client.get(f"/silhouette/steps/{build['id']}")
    assert r.status_code == 200
    assert r.get_json()["total"] == 2


def test_http_cuts(client, build):
    r = client.get(f"/silhouette/cuts/{build['id']}")
    assert r.status_code == 200
    assert r.get_json()["total_pieces"] == 7


def test_http_tools(client, build):
    r = client.get(f"/silhouette/tools/{build['id']}")
    assert r.status_code == 200
    assert r.get_json()["tool_count"] == 2


def test_http_presentation(client, build):
    r = client.get(f"/silhouette/presentation/{build['id']}")
    assert r.status_code == 200
    assert "presentation" in r.get_json()


def test_http_create_snapshot(client, build):
    r = client.post("/silhouette/snapshots",
                    json={"build_id": build["id"], "label": "release-v1"})
    assert r.status_code == 201
    assert r.get_json()["snapshot"]["label"] == "release-v1"


def test_http_create_snapshot_missing_build_id(client):
    r = client.post("/silhouette/snapshots", json={})
    assert r.status_code == 400


def test_http_get_snapshot(client, build):
    r = client.post("/silhouette/snapshots", json={"build_id": build["id"]})
    snap_id = r.get_json()["snapshot"]["id"]
    r2 = client.get(f"/silhouette/snapshots/{snap_id}")
    assert r2.status_code == 200


def test_http_delete_snapshot(client, build):
    r = client.post("/silhouette/snapshots", json={"build_id": build["id"]})
    snap_id = r.get_json()["snapshot"]["id"]
    r2 = client.delete(f"/silhouette/snapshots/{snap_id}")
    assert r2.status_code == 200
