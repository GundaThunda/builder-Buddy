import pytest
import os
import website_social_structure as ss
from app_server import app

DATA_FILE = os.path.join(os.path.dirname(ss.__file__), "social_data.json")


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


# --- users / points ---

def test_create_user():
    result = ss.get_or_create_user("nick")
    assert result["user"]["handle"] == "nick"
    assert result["user"]["points"] == 0


def test_create_user_idempotent():
    ss.get_or_create_user("nick")
    result = ss.get_or_create_user("nick")
    assert result["user"]["points"] == 0


def test_create_user_case_normalized():
    result = ss.get_or_create_user("NICK")
    assert result["user"]["handle"] == "nick"


def test_create_user_empty_handle():
    result = ss.get_or_create_user("")
    assert "error" in result


def test_award_points():
    ss.get_or_create_user("nick")
    result = ss.award_points("nick", "build_completed")
    assert result["points_awarded"] == 50
    assert result["total_points"] == 50


def test_award_points_accumulate():
    ss.get_or_create_user("nick")
    ss.award_points("nick", "tool_added")
    ss.award_points("nick", "tool_added")
    pts = ss.get_user_points("nick")["points"]
    assert pts == 20


def test_award_points_unknown_event():
    ss.get_or_create_user("nick")
    result = ss.award_points("nick", "invented_event")
    assert "error" in result


def test_award_points_auto_creates_user():
    result = ss.award_points("newuser", "step_completed")
    assert result["points_awarded"] == 5


def test_get_user_points():
    ss.get_or_create_user("nick")
    ss.award_points("nick", "build_finalized")
    result = ss.get_user_points("nick")
    assert result["points"] == 100


def test_get_user_not_found():
    result = ss.get_user_points("ghost")
    assert result["error"] == "not_found"


def test_point_log_recorded():
    ss.award_points("nick", "snapshot_created", ref_id="snap-123")
    log = ss.get_user_points("nick")["point_log"]
    assert len(log) == 1
    assert log[0]["event"] == "snapshot_created"
    assert log[0]["ref_id"] == "snap-123"


def test_all_point_events_valid():
    for event in ss.POINT_EVENTS:
        result = ss.award_points("tester", event)
        assert "points_awarded" in result


# --- leaderboard ---

def test_leaderboard_empty():
    result = ss.get_leaderboard()
    assert result["leaderboard"] == []


def test_leaderboard_ranked():
    ss.award_points("alice", "build_sold")
    ss.award_points("bob", "tool_added")
    board = ss.get_leaderboard()["leaderboard"]
    assert board[0]["handle"] == "alice"
    assert board[0]["rank"] == 1
    assert board[1]["handle"] == "bob"


def test_leaderboard_limit():
    for i in range(5):
        ss.award_points(f"user{i}", "tool_added")
    result = ss.get_leaderboard(limit=3)
    assert result["count"] == 3


# --- marketplace listings ---

def test_create_listing():
    result = ss.create_listing("nick", "build-123", "Workbench Plans", 19.99)
    assert result["listing"]["status"] == "active"
    assert result["listing"]["price_usd"] == 19.99


def test_create_listing_empty_title():
    result = ss.create_listing("nick", "build-123", "", 9.99)
    assert "error" in result


def test_create_listing_negative_price():
    result = ss.create_listing("nick", "build-123", "Plans", -5.0)
    assert "error" in result


def test_create_listing_zero_price_allowed():
    result = ss.create_listing("nick", "build-123", "Free Plans", 0.0)
    assert result["listing"]["price_usd"] == 0.0


def test_get_listing():
    listing = ss.create_listing("nick", "build-1", "Shelf Plans", 9.99)["listing"]
    result = ss.get_listing(listing["id"])
    assert result["listing"]["id"] == listing["id"]


def test_get_listing_not_found():
    result = ss.get_listing("fake-id")
    assert result["error"] == "not_found"


def test_list_listings():
    ss.create_listing("nick", "b1", "Plans A", 5.0)
    ss.create_listing("nick", "b2", "Plans B", 10.0)
    result = ss.list_listings()
    assert result["count"] == 2


def test_list_listings_filter_by_status():
    l1 = ss.create_listing("nick", "b1", "Active", 5.0)["listing"]
    ss.create_listing("nick", "b2", "Another", 5.0)
    ss.mark_listing_sold(l1["id"])
    result = ss.list_listings(status="sold")
    assert result["count"] == 1


def test_list_listings_filter_by_user():
    ss.create_listing("alice", "b1", "Alice Plans", 5.0)
    ss.create_listing("bob", "b2", "Bob Plans", 5.0)
    result = ss.list_listings(user_handle="alice")
    assert result["count"] == 1


def test_mark_listing_sold():
    listing = ss.create_listing("nick", "b1", "Plans", 25.0)["listing"]
    result = ss.mark_listing_sold(listing["id"])
    assert result["listing"]["status"] == "sold"
    assert result["listing"]["sold_at"] is not None


def test_mark_sold_twice_rejected():
    listing = ss.create_listing("nick", "b1", "Plans", 25.0)["listing"]
    ss.mark_listing_sold(listing["id"])
    result = ss.mark_listing_sold(listing["id"])
    assert "error" in result


def test_withdraw_listing():
    listing = ss.create_listing("nick", "b1", "Plans", 25.0)["listing"]
    result = ss.withdraw_listing(listing["id"])
    assert result["listing"]["status"] == "withdrawn"


def test_withdraw_sold_rejected():
    listing = ss.create_listing("nick", "b1", "Plans", 25.0)["listing"]
    ss.mark_listing_sold(listing["id"])
    result = ss.withdraw_listing(listing["id"])
    assert "error" in result


# --- HTTP routes ---

def test_http_create_user(client):
    r = client.post("/social/users/nick")
    assert r.status_code == 201
    assert r.get_json()["user"]["handle"] == "nick"


def test_http_get_user(client):
    client.post("/social/users/nick")
    r = client.get("/social/users/nick")
    assert r.status_code == 200


def test_http_get_user_not_found(client):
    r = client.get("/social/users/ghost")
    assert r.status_code == 404


def test_http_award_points(client):
    client.post("/social/users/nick")
    r = client.post("/social/users/nick/points", json={"event": "build_completed"})
    assert r.get_json()["points_awarded"] == 50


def test_http_leaderboard(client):
    client.post("/social/users/nick/points", json={"event": "build_sold"})
    r = client.get("/social/leaderboard")
    assert r.status_code == 200
    assert r.get_json()["leaderboard"][0]["handle"] == "nick"


def test_http_create_listing(client):
    r = client.post("/social/listings", json={
        "user_handle": "nick", "build_id": "b1",
        "title": "Cedar Chest Plans", "price_usd": 14.99
    })
    assert r.status_code == 201


def test_http_get_listing(client):
    r = client.post("/social/listings", json={
        "user_handle": "nick", "build_id": "b1", "title": "Plans", "price_usd": 5.0
    })
    lid = r.get_json()["listing"]["id"]
    r2 = client.get(f"/social/listings/{lid}")
    assert r2.status_code == 200


def test_http_sell_listing(client):
    r = client.post("/social/listings", json={
        "user_handle": "nick", "build_id": "b1", "title": "Plans", "price_usd": 5.0
    })
    lid = r.get_json()["listing"]["id"]
    r2 = client.patch(f"/social/listings/{lid}/sell")
    assert r2.get_json()["listing"]["status"] == "sold"


def test_http_withdraw_listing(client):
    r = client.post("/social/listings", json={
        "user_handle": "nick", "build_id": "b1", "title": "Plans", "price_usd": 5.0
    })
    lid = r.get_json()["listing"]["id"]
    r2 = client.patch(f"/social/listings/{lid}/withdraw")
    assert r2.get_json()["listing"]["status"] == "withdrawn"
