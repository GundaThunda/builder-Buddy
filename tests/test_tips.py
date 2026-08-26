import pytest
import os
import website_tips as tips
from app_server import app

DATA_FILE = os.path.join(os.path.dirname(tips.__file__), "tips_data.json")

EPOXY_TIP = {
    "title": "Epoxy leaking from bug holes",
    "problem": "I want to fill in these bug holes in my board but the epoxy keeps leaking out before the A/B mixture sets. What should I do?",
    "solution": "Tape the other side using specialized epoxy tape. It covers the affected area, sticks well to the surface, peels off cleanly, stops the leak, and is heat resistant for the heat buildup from the chemical reaction.",
    "category": "problem_solving",
    "process_tags": ["finishing", "epoxy"],
    "verified": True,
}


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


@pytest.fixture
def epoxy_tip():
    return tips.add_tip(**EPOXY_TIP)["tip"]


# --- add_tip ---

def test_add_tip_basic(epoxy_tip):
    assert epoxy_tip["title"] == EPOXY_TIP["title"]
    assert epoxy_tip["category"] == "problem_solving"
    assert epoxy_tip["verified"] is True


def test_add_tip_empty_title():
    result = tips.add_tip(title="", problem="Q", solution="A")
    assert "error" in result


def test_add_tip_empty_problem():
    result = tips.add_tip(title="T", problem="", solution="A")
    assert "error" in result


def test_add_tip_empty_solution():
    result = tips.add_tip(title="T", problem="Q", solution="")
    assert "error" in result


def test_add_tip_invalid_category_defaults():
    result = tips.add_tip(title="T", problem="Q", solution="A", category="nonsense")
    assert result["tip"]["category"] == "general"


def test_add_tip_process_tags():
    result = tips.add_tip(title="T", problem="Q", solution="A", process_tags=["sanding", "oak"])
    assert "sanding" in result["tip"]["process_tags"]


def test_add_tip_unverified():
    result = tips.add_tip(title="T", problem="Q", solution="A", verified=False)
    assert result["tip"]["verified"] is False


# --- get_tip ---

def test_get_tip(epoxy_tip):
    result = tips.get_tip(epoxy_tip["id"])
    assert result["tip"]["id"] == epoxy_tip["id"]


def test_get_tip_not_found():
    result = tips.get_tip("fake-id")
    assert result["error"] == "not_found"


# --- update_tip ---

def test_update_tip_solution(epoxy_tip):
    result = tips.update_tip(epoxy_tip["id"], solution="Use epoxy tape on the underside.")
    assert "epoxy tape" in result["tip"]["solution"]


def test_update_tip_category(epoxy_tip):
    result = tips.update_tip(epoxy_tip["id"], category="finishing")
    assert result["tip"]["category"] == "finishing"


def test_update_tip_empty_title_rejected(epoxy_tip):
    result = tips.update_tip(epoxy_tip["id"], title="")
    assert "error" in result


def test_update_tip_not_found():
    result = tips.update_tip("fake-id", solution="New solution")
    assert result["error"] == "not_found"


def test_update_tip_add_process_tags(epoxy_tip):
    result = tips.update_tip(epoxy_tip["id"], process_tags=["epoxy", "filling", "bug-holes"])
    assert "bug-holes" in result["tip"]["process_tags"]


# --- delete_tip ---

def test_delete_tip(epoxy_tip):
    tips.delete_tip(epoxy_tip["id"])
    assert tips.get_tip(epoxy_tip["id"])["error"] == "not_found"


def test_delete_tip_not_found():
    result = tips.delete_tip("fake-id")
    assert result["error"] == "not_found"


# --- list_tips ---

def test_list_tips_empty():
    result = tips.list_tips()
    assert result["count"] == 0


def test_list_tips_all(epoxy_tip):
    tips.add_tip(title="T2", problem="Q2", solution="A2", category="safety")
    result = tips.list_tips()
    assert result["count"] == 2


def test_list_tips_by_category(epoxy_tip):
    tips.add_tip(title="T2", problem="Q2", solution="A2", category="safety")
    result = tips.list_tips(category="problem_solving")
    assert result["count"] == 1


def test_list_tips_verified_only(epoxy_tip):
    tips.add_tip(title="Draft", problem="Q", solution="A", verified=False)
    result = tips.list_tips(verified=True)
    assert result["count"] == 1


def test_list_tips_unverified_only(epoxy_tip):
    tips.add_tip(title="Draft", problem="Q", solution="A", verified=False)
    result = tips.list_tips(verified=False)
    assert result["count"] == 1


# --- search_tips ---

def test_search_tips_by_title(epoxy_tip):
    result = tips.search_tips("epoxy")
    assert result["count"] == 1


def test_search_tips_by_problem(epoxy_tip):
    result = tips.search_tips("bug holes")
    assert result["count"] == 1


def test_search_tips_by_solution(epoxy_tip):
    result = tips.search_tips("heat resistant")
    assert result["count"] == 1


def test_search_tips_by_process_tag(epoxy_tip):
    result = tips.search_tips("finishing")
    assert result["count"] == 1


def test_search_tips_no_match(epoxy_tip):
    result = tips.search_tips("dovetail")
    assert result["count"] == 0


# --- HTTP routes ---

def test_http_add_tip(client):
    r = client.post("/tips/tips", json={
        "title": "Tear-out on crosscuts",
        "problem": "Getting tear-out when crosscutting plywood",
        "solution": "Score the cut line with a utility knife before cutting",
        "category": "tool_use",
    })
    assert r.status_code == 201
    assert r.get_json()["tip"]["category"] == "tool_use"


def test_http_get_tip(client, epoxy_tip):
    r = client.get(f"/tips/tips/{epoxy_tip['id']}")
    assert r.status_code == 200


def test_http_get_tip_not_found(client):
    r = client.get("/tips/tips/fake-id")
    assert r.status_code == 404


def test_http_list_tips(client, epoxy_tip):
    r = client.get("/tips/tips")
    assert r.status_code == 200
    assert r.get_json()["count"] == 1


def test_http_list_tips_by_category(client, epoxy_tip):
    r = client.get("/tips/tips?category=problem_solving")
    assert r.get_json()["count"] == 1


def test_http_search_tips(client, epoxy_tip):
    r = client.get("/tips/tips/search?q=epoxy")
    assert r.status_code == 200
    assert r.get_json()["count"] == 1


def test_http_search_missing_q(client):
    r = client.get("/tips/tips/search")
    assert r.status_code == 400


def test_http_update_tip(client, epoxy_tip):
    r = client.patch(f"/tips/tips/{epoxy_tip['id']}", json={"category": "finishing"})
    assert r.status_code == 200
    assert r.get_json()["tip"]["category"] == "finishing"


def test_http_delete_tip(client, epoxy_tip):
    r = client.delete(f"/tips/tips/{epoxy_tip['id']}")
    assert r.status_code == 200
