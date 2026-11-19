import uuid
import json
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

social_routes = Blueprint("social", __name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "social_data.json")

POINT_EVENTS = {
    "build_completed": 50,
    "build_finalized": 100,
    "build_sold": 200,
    "tool_added": 10,
    "step_completed": 5,
    "snapshot_created": 15,
}

LISTING_STATUSES = {"active", "sold", "withdrawn"}


def _load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"users": {}, "listings": {}}


def _save(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- User / Points ---

def get_or_create_user(user_handle: str) -> dict:
    user_handle = user_handle.strip().lower()
    if not user_handle:
        return {"error": "user_handle is required"}
    data = _load()
    if user_handle not in data["users"]:
        data["users"][user_handle] = {
            "handle": user_handle,
            "points": 0,
            "point_log": [],
            "joined_at": _now(),
        }
        _save(data)
    return {"user": data["users"][user_handle]}


def award_points(user_handle: str, event: str, ref_id: str = "") -> dict:
    if event not in POINT_EVENTS:
        return {"error": f"unknown event '{event}'"}
    result = get_or_create_user(user_handle)
    if "error" in result:
        return result

    data = _load()
    user = data["users"][user_handle]
    pts = POINT_EVENTS[event]
    user["points"] += pts
    user["point_log"].append({
        "id": str(uuid.uuid4()),
        "event": event,
        "points": pts,
        "ref_id": ref_id,
        "awarded_at": _now(),
    })
    _save(data)
    return {"user_handle": user_handle, "event": event, "points_awarded": pts,
            "total_points": user["points"]}


def get_user_points(user_handle: str) -> dict:
    data = _load()
    user = data["users"].get(user_handle.strip().lower())
    if not user:
        return {"error": "not_found"}
    return {"user_handle": user["handle"], "points": user["points"],
            "point_log": user["point_log"]}


def get_leaderboard(limit: int = 10) -> dict:
    data = _load()
    ranked = sorted(data["users"].values(), key=lambda u: u["points"], reverse=True)[:limit]
    board = [{"rank": i + 1, "handle": u["handle"], "points": u["points"]}
             for i, u in enumerate(ranked)]
    return {"leaderboard": board, "count": len(board)}


# --- Marketplace listings ---

def create_listing(user_handle: str, build_id: str, title: str,
                   price_usd: float, description: str = "") -> dict:
    title = title.strip()
    if not title:
        return {"error": "title is required"}
    if price_usd < 0:
        return {"error": "price_usd must be non-negative"}
    result = get_or_create_user(user_handle)
    if "error" in result:
        return result

    listing_id = str(uuid.uuid4())
    now = _now()
    listing = {
        "id": listing_id,
        "user_handle": user_handle.strip().lower(),
        "build_id": build_id,
        "title": title,
        "description": description,
        "price_usd": price_usd,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "sold_at": None,
    }
    data = _load()
    data["listings"][listing_id] = listing
    _save(data)
    return {"listing": listing}


def get_listing(listing_id: str) -> dict:
    data = _load()
    listing = data["listings"].get(listing_id)
    if not listing:
        return {"error": "not_found"}
    return {"listing": listing}


def list_listings(status: str | None = None, user_handle: str | None = None) -> dict:
    data = _load()
    listings = list(data["listings"].values())
    if status:
        listings = [l for l in listings if l["status"] == status]
    if user_handle:
        listings = [l for l in listings if l["user_handle"] == user_handle.lower()]
    return {"listings": listings, "count": len(listings)}


def mark_listing_sold(listing_id: str) -> dict:
    data = _load()
    listing = data["listings"].get(listing_id)
    if not listing:
        return {"error": "not_found"}
    if listing["status"] != "active":
        return {"error": f"cannot mark as sold from status '{listing['status']}'"}
    listing["status"] = "sold"
    listing["sold_at"] = _now()
    listing["updated_at"] = _now()
    _save(data)
    return {"listing": listing}


def withdraw_listing(listing_id: str) -> dict:
    data = _load()
    listing = data["listings"].get(listing_id)
    if not listing:
        return {"error": "not_found"}
    if listing["status"] != "active":
        return {"error": f"cannot withdraw from status '{listing['status']}'"}
    listing["status"] = "withdrawn"
    listing["updated_at"] = _now()
    _save(data)
    return {"listing": listing}


# --- Admin profile (server-side only; no route exposes setter) ---

ROLE_ADMIN = "admin"
PRIVATE_USER_FIELDS = {"profile", "profile_updated_at", "role"}


def set_admin_profile(user_handle: str, display_name: str, company: str,
                      birth_year: int, birth_month: int) -> dict:
    handle = user_handle.strip().lower()
    if not handle:
        return {"error": "user_handle is required"}
    display_name = display_name.strip()
    company = company.strip()
    if not display_name:
        return {"error": "display_name is required"}
    if not (isinstance(birth_year, int) and not isinstance(birth_year, bool)
            and 1900 <= birth_year <= datetime.now(timezone.utc).year):
        return {"error": "birth_year out of range"}
    if not (isinstance(birth_month, int) and not isinstance(birth_month, bool)
            and 1 <= birth_month <= 12):
        return {"error": "birth_month must be 1-12"}
    result = get_or_create_user(handle)
    if "error" in result:
        return result
    data = _load()
    user = data["users"][handle]
    user["role"] = ROLE_ADMIN
    user["profile"] = {
        "display_name": display_name,
        "company": company,
        "birth_year": birth_year,
        "birth_month": birth_month,
    }
    user["profile_updated_at"] = _now()
    _save(data)
    return {"user_handle": handle, "role": ROLE_ADMIN}


def is_admin(user_handle: str) -> bool:
    data = _load()
    user = data["users"].get(user_handle.strip().lower())
    return bool(user) and user.get("role") == ROLE_ADMIN


ROLE_MEMBER = "member"
VALID_ROLES = {ROLE_ADMIN, ROLE_MEMBER}


def admin_handles() -> list:
    data = _load()
    return sorted(h for h, u in data["users"].items() if u.get("role") == ROLE_ADMIN)


def set_role(user_handle: str, role) -> dict:
    """Error codes: invalid_role, not_found, last_admin. Callers map these to HTTP."""
    handle = user_handle.strip().lower()
    if role not in VALID_ROLES:
        return {"error": "invalid_role"}
    data = _load()
    user = data["users"].get(handle)
    if not user:
        return {"error": "not_found"}
    if user.get("role") == ROLE_ADMIN and role != ROLE_ADMIN and len(admin_handles()) == 1:
        return {"error": "last_admin"}
    user["role"] = role
    _save(data)
    return {"user_handle": handle, "role": role}


def public_user_view(user: dict) -> dict:
    return {k: v for k, v in user.items() if k not in PRIVATE_USER_FIELDS}


# --- Flask routes ---

@social_routes.route("/users/<user_handle>", methods=["GET"])
def route_get_user(user_handle):
    result = get_user_points(user_handle)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@social_routes.route("/users/<user_handle>", methods=["POST"])
def route_create_user(user_handle):
    result = get_or_create_user(user_handle)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"user": public_user_view(result["user"])}), 201


@social_routes.route("/users/<user_handle>/points", methods=["POST"])
def route_award_points(user_handle):
    body = request.get_json(silent=True) or {}
    result = award_points(user_handle, body.get("event", ""), body.get("ref_id", ""))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@social_routes.route("/leaderboard", methods=["GET"])
def route_leaderboard():
    limit = int(request.args.get("limit", 10))
    return jsonify(get_leaderboard(limit))


@social_routes.route("/listings", methods=["GET"])
def route_list_listings():
    return jsonify(list_listings(
        status=request.args.get("status"),
        user_handle=request.args.get("user"),
    ))


@social_routes.route("/listings", methods=["POST"])
def route_create_listing():
    body = request.get_json(silent=True) or {}
    result = create_listing(
        user_handle=body.get("user_handle", ""),
        build_id=body.get("build_id", ""),
        title=body.get("title", ""),
        price_usd=body.get("price_usd", 0.0),
        description=body.get("description", ""),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 201


@social_routes.route("/listings/<listing_id>", methods=["GET"])
def route_get_listing(listing_id):
    result = get_listing(listing_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@social_routes.route("/listings/<listing_id>/sell", methods=["PATCH"])
def route_sell_listing(listing_id):
    result = mark_listing_sold(listing_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@social_routes.route("/listings/<listing_id>/withdraw", methods=["PATCH"])
def route_withdraw_listing(listing_id):
    result = withdraw_listing(listing_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
