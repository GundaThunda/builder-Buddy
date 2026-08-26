import pytest
import os
import json
from app_server import app
import website_toolbox as tb


TEST_DATA_FILE = os.path.join(os.path.dirname(tb.__file__), "toolbox_data.json")


@pytest.fixture(autouse=True)
def clean_data():
    """Reset data file before each test."""
    if os.path.exists(TEST_DATA_FILE):
        os.remove(TEST_DATA_FILE)
    yield
    if os.path.exists(TEST_DATA_FILE):
        os.remove(TEST_DATA_FILE)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# --- add_item ---

def test_add_owned_tool():
    result = tb.add_item("Table Saw", item_type="tool", category="Power Tools", status="owned")
    assert "item" in result
    assert result["item"]["status"] == "owned"
    assert result["item"]["type"] == "tool"
    assert result["item"]["wishlist_rating"] is None


def test_add_wishlist_tool_with_rating():
    result = tb.add_item("Bandsaw", status="wishlist", wishlist_rating=4)
    assert result["item"]["status"] == "wishlist"
    assert result["item"]["wishlist_rating"] == 4


def test_wishlist_rating_cleared_on_owned():
    result = tb.add_item("Drill Press", status="owned", wishlist_rating=3)
    assert result["item"]["wishlist_rating"] is None


def test_wishlist_rating_out_of_range():
    result = tb.add_item("Jigsaw", status="wishlist", wishlist_rating=6)
    assert "error" in result


def test_wishlist_rating_zero():
    result = tb.add_item("Jigsaw", status="wishlist", wishlist_rating=0)
    assert "error" in result


def test_add_item_empty_name():
    result = tb.add_item("")
    assert result["error"] == "name is required"


def test_add_item_whitespace_name():
    result = tb.add_item("   ")
    assert result["error"] == "name is required"


# --- smart routing ---

def test_smart_route_hardware_screw():
    result = tb.add_item("Wood Screw 2in")
    assert result["item"]["type"] == "hardware"


def test_smart_route_hardware_bolt():
    result = tb.add_item("Hex Bolt M8")
    assert result["item"]["type"] == "hardware"


def test_smart_route_upgrade_blade():
    result = tb.add_item("Table Saw Blade 40T")
    assert result["item"]["type"] == "upgrade"


def test_smart_route_upgrade_sandpaper():
    result = tb.add_item("220 Grit Sandpaper")
    assert result["item"]["type"] == "upgrade"


def test_smart_route_material_wood():
    result = tb.add_item("Red Oak Board")
    assert result["item"]["type"] == "material"


def test_smart_route_material_plywood():
    result = tb.add_item("3/4 Plywood Sheet")
    assert result["item"]["type"] == "material"


def test_smart_route_defaults_to_tool():
    result = tb.add_item("Mystery Gadget")
    assert result["item"]["type"] == "tool"


def test_explicit_type_overrides_smart_route():
    result = tb.add_item("Special Screw", item_type="tool")
    assert result["item"]["type"] == "tool"


# --- duplicate detection ---

def test_duplicate_blocked():
    tb.add_item("Router", item_type="tool", status="owned")
    result = tb.add_item("Router", item_type="tool", status="owned")
    assert result["error"] == "duplicate_detected"
    assert len(result["duplicates"]) == 1


def test_duplicate_case_insensitive():
    tb.add_item("router", item_type="tool")
    result = tb.add_item("Router", item_type="tool")
    assert result["error"] == "duplicate_detected"


def test_same_name_different_type_allowed():
    tb.add_item("Extension", item_type="tool")
    result = tb.add_item("Extension", item_type="hardware")
    assert "item" in result


def test_duplicate_returns_existing_items():
    tb.add_item("Chisel Set", item_type="tool")
    result = tb.add_item("Chisel Set", item_type="tool")
    assert "duplicates" in result
    assert result["duplicates"][0]["name"] == "Chisel Set"


# --- category handling ---

def test_valid_category_stored():
    result = tb.add_item("Mallet", category="Hand Tools")
    assert result["item"]["category"] == "Hand Tools"


def test_invalid_category_becomes_uncategorized():
    result = tb.add_item("Weird Tool", category="Banana Category")
    assert result["item"]["category"] == "Uncategorized"


def test_no_category_defaults_uncategorized():
    result = tb.add_item("Unknown Thing")
    assert result["item"]["category"] == "Uncategorized"


# --- get_item ---

def test_get_item_exists():
    added = tb.add_item("Clamp", item_type="tool")["item"]
    result = tb.get_item(added["id"])
    assert result["item"]["id"] == added["id"]


def test_get_item_not_found():
    result = tb.get_item("nonexistent-id")
    assert result["error"] == "not_found"


# --- update_item ---

def test_update_name():
    item = tb.add_item("Old Name")["item"]
    result = tb.update_item(item["id"], name="New Name")
    assert result["item"]["name"] == "New Name"


def test_update_status_owned_clears_rating():
    item = tb.add_item("Planer", status="wishlist", wishlist_rating=3)["item"]
    result = tb.update_item(item["id"], status="owned")
    assert result["item"]["status"] == "owned"
    assert result["item"]["wishlist_rating"] is None


def test_update_wishlist_rating():
    item = tb.add_item("Jointer", status="wishlist", wishlist_rating=2)["item"]
    result = tb.update_item(item["id"], wishlist_rating=5)
    assert result["item"]["wishlist_rating"] == 5


def test_update_invalid_status():
    item = tb.add_item("Saw")["item"]
    result = tb.update_item(item["id"], status="broken")
    assert "error" in result


def test_update_invalid_wishlist_rating():
    item = tb.add_item("Saw", status="wishlist", wishlist_rating=2)["item"]
    result = tb.update_item(item["id"], wishlist_rating=10)
    assert "error" in result


def test_update_not_found():
    result = tb.update_item("fake-id", name="Whatever")
    assert result["error"] == "not_found"


def test_update_tags():
    item = tb.add_item("Router Bit")["item"]
    result = tb.update_item(item["id"], tags=["routing", "joinery"])
    assert "routing" in result["item"]["tags"]


def test_update_linked_items():
    a = tb.add_item("Router Table")["item"]
    b = tb.add_item("Router Bit Set")["item"]
    result = tb.update_item(a["id"], linked_items=[b["id"]])
    assert b["id"] in result["item"]["linked_items"]


def test_update_timestamps_change():
    import time
    item = tb.add_item("Workbench")["item"]
    original_ts = item["updated_at"]
    time.sleep(0.01)
    result = tb.update_item(item["id"], name="Heavy Workbench")
    assert result["item"]["updated_at"] >= original_ts


# --- delete_item ---

def test_delete_item():
    item = tb.add_item("Disposable Tool")["item"]
    result = tb.delete_item(item["id"])
    assert "deleted" in result
    assert tb.get_item(item["id"])["error"] == "not_found"


def test_delete_not_found():
    result = tb.delete_item("fake-id")
    assert result["error"] == "not_found"


# --- list_items ---

def test_list_all_items():
    tb.add_item("Tool A", item_type="tool")
    tb.add_item("Screw Pack")
    result = tb.list_items()
    assert result["count"] == 2


def test_list_filter_by_type():
    tb.add_item("Drill", item_type="tool")
    tb.add_item("Oak Plank")
    result = tb.list_items(item_type="tool")
    assert all(i["type"] == "tool" for i in result["items"])


def test_list_filter_by_status():
    tb.add_item("Lathe", status="owned")
    tb.add_item("CNC Router", status="wishlist", wishlist_rating=5)
    result = tb.list_items(status="wishlist")
    assert all(i["status"] == "wishlist" for i in result["items"])
    assert result["count"] == 1


def test_list_filter_by_category():
    tb.add_item("Chisel", category="Hand Tools")
    tb.add_item("Circular Saw", category="Power Tools")
    result = tb.list_items(category="Hand Tools")
    assert result["count"] == 1
    assert result["items"][0]["name"] == "Chisel"


def test_list_empty():
    result = tb.list_items()
    assert result["count"] == 0
    assert result["items"] == []


# --- search_items ---

def test_search_by_name():
    tb.add_item("Orbital Sander")
    tb.add_item("Belt Sander")
    tb.add_item("Table Saw")
    result = tb.search_items("sander")
    assert result["count"] == 2


def test_search_case_insensitive():
    tb.add_item("Dovetail Jig")
    result = tb.search_items("DOVETAIL")
    assert result["count"] == 1


def test_search_by_tag():
    item = tb.add_item("Pocket Hole Jig")["item"]
    tb.update_item(item["id"], tags=["joinery", "kreg"])
    result = tb.search_items("joinery")
    assert result["count"] == 1


def test_search_no_results():
    tb.add_item("Hand Plane")
    result = tb.search_items("zzznomatch")
    assert result["count"] == 0


# --- HTTP routes ---

def test_http_add_item(client):
    r = client.post("/toolbox/items", json={"name": "Scroll Saw", "type": "tool", "status": "owned"})
    assert r.status_code == 201
    assert r.get_json()["item"]["name"] == "Scroll Saw"


def test_http_add_item_missing_name(client):
    r = client.post("/toolbox/items", json={})
    assert r.status_code == 400


def test_http_add_duplicate_returns_409(client):
    client.post("/toolbox/items", json={"name": "Band Saw", "type": "tool"})
    r = client.post("/toolbox/items", json={"name": "Band Saw", "type": "tool"})
    assert r.status_code == 409


def test_http_get_item(client):
    r = client.post("/toolbox/items", json={"name": "Spokeshave"})
    item_id = r.get_json()["item"]["id"]
    r2 = client.get(f"/toolbox/items/{item_id}")
    assert r2.status_code == 200
    assert r2.get_json()["item"]["name"] == "Spokeshave"


def test_http_get_item_not_found(client):
    r = client.get("/toolbox/items/does-not-exist")
    assert r.status_code == 404


def test_http_update_item(client):
    r = client.post("/toolbox/items", json={"name": "Miter Saw"})
    item_id = r.get_json()["item"]["id"]
    r2 = client.patch(f"/toolbox/items/{item_id}", json={"name": "Compound Miter Saw"})
    assert r2.status_code == 200
    assert r2.get_json()["item"]["name"] == "Compound Miter Saw"


def test_http_delete_item(client):
    r = client.post("/toolbox/items", json={"name": "Old Saw"})
    item_id = r.get_json()["item"]["id"]
    r2 = client.delete(f"/toolbox/items/{item_id}")
    assert r2.status_code == 200
    r3 = client.get(f"/toolbox/items/{item_id}")
    assert r3.status_code == 404


def test_http_list_items(client):
    client.post("/toolbox/items", json={"name": "Item One"})
    client.post("/toolbox/items", json={"name": "Item Two"})
    r = client.get("/toolbox/items")
    assert r.get_json()["count"] == 2


def test_http_list_filter_type(client):
    client.post("/toolbox/items", json={"name": "Drill", "type": "tool"})
    client.post("/toolbox/items", json={"name": "Pine Board"})
    r = client.get("/toolbox/items?type=tool")
    data = r.get_json()
    assert all(i["type"] == "tool" for i in data["items"])


def test_http_search(client):
    client.post("/toolbox/items", json={"name": "Japanese Pull Saw"})
    r = client.get("/toolbox/items/search?q=pull")
    assert r.get_json()["count"] == 1


def test_http_search_missing_q(client):
    r = client.get("/toolbox/items/search")
    assert r.status_code == 400
