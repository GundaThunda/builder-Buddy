import uuid
import json
import os
import time
from datetime import datetime, timezone
from flask import Blueprint, g, request, jsonify

from website_gate import require_auth

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


def _owner_from_route_user(kwargs):
    return kwargs["user_handle"]


def _owner_from_body(kwargs):
    body = request.get_json(silent=True) or {}
    return body.get("user_handle", "")


def _owner_of_listing(kwargs):
    listing = get_listing(kwargs["listing_id"]).get("listing") or {}
    return listing.get("user_handle", "")


@social_routes.route("/users/<user_handle>", methods=["POST"])
@require_auth(owner_of=_owner_from_route_user)
def route_create_user(user_handle):
    result = get_or_create_user(user_handle)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"user": public_user_view(result["user"])}), 201


@social_routes.route("/users/<user_handle>/points", methods=["POST"])
@require_auth(admin_only=True)
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
@require_auth(owner_of=_owner_from_body)
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
@require_auth(owner_of=_owner_of_listing)
def route_sell_listing(listing_id):
    result = mark_listing_sold(listing_id)
    if result.get("error") == "not_found":
        return jsonify(result), 404
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@social_routes.route("/listings/<listing_id>/withdraw", methods=["PATCH"])
@require_auth(owner_of=_owner_of_listing)
def route_withdraw_listing(listing_id):
    result = withdraw_listing(listing_id)
    if result.get("error") == "not_found":
        return jsonify(result), 404
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# --- Ratings: separate metric from points. Members rate others' published builds. ---
# Points remain admin/system-awarded only.

RATING_SCORES = {1, 2, 3, 4, 5}
RAPID_WINDOW_SECONDS = 60
RAPID_THRESHOLD = 5
NEW_ACCOUNT_SECONDS = 24 * 60 * 60
RECIPROCAL_MIN = 3
CONCENTRATION_MIN = 5
CONCENTRATION_SHARE = 0.8
UNIFORM_MIN = 10
BOT_UA_TOKENS = ("bot", "crawler", "spider", "curl", "wget", "python-requests",
                 "httpx", "aiohttp", "go-http-client", "okhttp", "agent")
FARM_LIKELY_FLAGS = 2


def _now_ts() -> float:
    return time.time()


def _ratings_data() -> dict:
    data = _load()
    data.setdefault("published_builds", {})
    data.setdefault("ratings", {})
    return data


def publish_build(owner: str, build_id, title) -> dict:
    """Owner is always the authenticated caller. Known gap: build existence is not
    verified against Blueprint (module independence), so a build_id can be claimed first."""
    build_id = (build_id or "").strip()
    title = (title or "").strip()
    if not build_id:
        return {"error": "build_id is required"}
    if not title:
        return {"error": "title is required"}
    data = _ratings_data()
    existing = data["published_builds"].get(build_id)
    if existing:
        if existing["owner"] != owner:
            return {"error": "already_published"}
        return {"published_build": existing}
    entry = {"build_id": build_id, "owner": owner, "title": title, "published_at": _now()}
    data["published_builds"][build_id] = entry
    _save(data)
    return {"published_build": entry}


def _farm_flags(rater: str, owner: str, build_id: str, score: int,
                user_agent: str, data: dict, now: float) -> list:
    key = f"{build_id}:{rater}"
    ratings = list(data["ratings"].values())
    others = [r for r in ratings if r["key"] != key]
    by_rater = [r for r in others if r["rater"] == rater]
    to_owner = [r for r in by_rater if r["owner"] == owner]
    from_owner = [r for r in others if r["rater"] == owner and r["owner"] == rater]
    user = data["users"].get(rater, {})
    flags = []

    joined = user.get("joined_at")
    if joined and now - datetime.fromisoformat(joined).timestamp() < NEW_ACCOUNT_SECONDS:
        flags.append("new_account")
    recent = [r for r in by_rater if now - r["created_ts"] <= RAPID_WINDOW_SECONDS]
    if len(recent) + 1 >= RAPID_THRESHOLD:
        flags.append("rapid_fire")
    if len(to_owner) + 1 >= RECIPROCAL_MIN and len(from_owner) >= RECIPROCAL_MIN:
        flags.append("reciprocal_pair")
    if (len(by_rater) + 1 >= CONCENTRATION_MIN
            and (len(to_owner) + 1) / (len(by_rater) + 1) >= CONCENTRATION_SHARE):
        flags.append("concentrated_target")
    if len(by_rater) + 1 >= UNIFORM_MIN:
        last = sorted(by_rater, key=lambda r: r["created_ts"])[-(UNIFORM_MIN - 1):]
        if len({r["score"] for r in last} | {score}) == 1:
            flags.append("uniform_scores")
    ua = (user_agent or "").lower()
    if not ua or any(token in ua for token in BOT_UA_TOKENS):
        flags.append("automation_client")
    return flags


def _severity(flags: list) -> str:
    if len(flags) >= FARM_LIKELY_FLAGS:
        return "likely_farmed"
    return "review" if flags else "clean"


def rate_build(rater: str, build_id: str, score, user_agent: str = "") -> dict:
    data = _ratings_data()
    pub = data["published_builds"].get(build_id)
    if not pub:
        return {"error": "not_found"}
    if pub["owner"] == rater:
        return {"error": "cannot_rate_own"}
    if not (isinstance(score, int) and not isinstance(score, bool) and score in RATING_SCORES):
        return {"error": "score must be an integer 1-5"}
    now = _now_ts()
    flags = _farm_flags(rater, pub["owner"], build_id, score, user_agent, data, now)
    key = f"{build_id}:{rater}"
    data["ratings"][key] = {
        "key": key, "build_id": build_id, "owner": pub["owner"], "rater": rater,
        "score": score, "created_ts": now, "flags": flags, "severity": _severity(flags),
    }
    _save(data)
    # Flags are deliberately not returned to the rater.
    return {"status": "recorded", "build_id": build_id}


def _counted(ratings: list) -> list:
    return [r for r in ratings if r["severity"] != "likely_farmed"]


def _average(ratings: list):
    return round(sum(r["score"] for r in ratings) / len(ratings), 2) if ratings else None


def build_rating_summary(build_id: str) -> dict:
    data = _ratings_data()
    pub = data["published_builds"].get(build_id)
    if not pub:
        return {"error": "not_found"}
    counted = _counted([r for r in data["ratings"].values() if r["build_id"] == build_id])
    return {"build_id": build_id, "title": pub["title"], "owner": pub["owner"],
            "rating_avg": _average(counted), "rating_count": len(counted)}


def user_rating_summary(user_handle: str) -> dict:
    handle = user_handle.strip().lower()
    data = _ratings_data()
    if handle not in data["users"]:
        return {"error": "not_found"}
    builds = [b for b in data["published_builds"].values() if b["owner"] == handle]
    counted = _counted([r for r in data["ratings"].values() if r["owner"] == handle])
    return {"user_handle": handle, "published_builds": len(builds),
            "rating_avg": _average(counted), "rating_count": len(counted)}


def list_flagged_ratings() -> dict:
    data = _ratings_data()
    flagged = [r for r in data["ratings"].values() if r["severity"] != "clean"]
    flagged.sort(key=lambda r: (r["severity"] != "likely_farmed", -r["created_ts"]))
    return {"ratings": flagged, "count": len(flagged)}


@social_routes.route("/published-builds", methods=["POST"])
@require_auth()
def route_publish_build():
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    result = publish_build(g.auth_user, body.get("build_id"), body.get("title"))
    if "error" in result:
        return jsonify(result), (409 if result["error"] == "already_published" else 400)
    return jsonify(result), 201


@social_routes.route("/published-builds/<build_id>", methods=["GET"])
def route_get_published_build(build_id):
    result = build_rating_summary(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@social_routes.route("/published-builds/<build_id>/ratings", methods=["POST"])
@require_auth()
def route_rate_build(build_id):
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    result = rate_build(g.auth_user, build_id, body.get("score"),
                        request.headers.get("User-Agent", ""))
    if "error" in result:
        status = {"not_found": 404, "cannot_rate_own": 403}.get(result["error"], 400)
        return jsonify(result), status
    return jsonify(result), 201


@social_routes.route("/users/<user_handle>/rating-summary", methods=["GET"])
def route_user_rating_summary(user_handle):
    result = user_rating_summary(user_handle)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@social_routes.route("/admin/rating-flags", methods=["GET"])
@require_auth(admin_only=True)
def route_rating_flags():
    return jsonify(list_flagged_ratings())
