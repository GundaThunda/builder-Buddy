import uuid
import json
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

tips_routes = Blueprint("tips", __name__)

TIP_CATEGORIES = {"finishing", "joinery", "material_prep", "problem_solving", "tool_use", "safety", "general"}

DATA_FILE = os.path.join(os.path.dirname(__file__), "tips_data.json")


def _load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"tips": {}}


def _save(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_tip(title: str, problem: str, solution: str, category: str = "general",
            process_tags: list | None = None, verified: bool = True) -> dict:
    title = title.strip()
    problem = problem.strip()
    solution = solution.strip()
    if not title:
        return {"error": "title is required"}
    if not problem:
        return {"error": "problem is required"}
    if not solution:
        return {"error": "solution is required"}
    if category not in TIP_CATEGORIES:
        category = "general"

    tip_id = str(uuid.uuid4())
    now = _now()
    tip = {
        "id": tip_id,
        "title": title,
        "problem": problem,
        "solution": solution,
        "category": category,
        "process_tags": process_tags or [],
        "verified": verified,
        "created_at": now,
        "updated_at": now,
    }
    data = _load()
    data["tips"][tip_id] = tip
    _save(data)
    return {"tip": tip}


def get_tip(tip_id: str) -> dict:
    data = _load()
    tip = data["tips"].get(tip_id)
    if not tip:
        return {"error": "not_found"}
    return {"tip": tip}


def update_tip(tip_id: str, **fields) -> dict:
    data = _load()
    tip = data["tips"].get(tip_id)
    if not tip:
        return {"error": "not_found"}

    allowed = {"title", "problem", "solution", "category", "process_tags", "verified"}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in ("title", "problem", "solution"):
            value = value.strip()
            if not value:
                return {"error": f"{key} cannot be empty"}
        if key == "category" and value not in TIP_CATEGORIES:
            value = "general"
        tip[key] = value

    tip["updated_at"] = _now()
    data["tips"][tip_id] = tip
    _save(data)
    return {"tip": tip}


def delete_tip(tip_id: str) -> dict:
    data = _load()
    if tip_id not in data["tips"]:
        return {"error": "not_found"}
    removed = data["tips"].pop(tip_id)
    _save(data)
    return {"deleted": removed}


def list_tips(category: str | None = None, verified: bool | None = None) -> dict:
    data = _load()
    tips = list(data["tips"].values())
    if category:
        tips = [t for t in tips if t["category"] == category]
    if verified is not None:
        tips = [t for t in tips if t["verified"] == verified]
    return {"tips": tips, "count": len(tips)}


def search_tips(query: str) -> dict:
    q = query.lower().strip()
    if not q:
        return {"error": "query is required"}
    data = _load()
    results = [
        t for t in data["tips"].values()
        if q in t["title"].lower()
        or q in t["problem"].lower()
        or q in t["solution"].lower()
        or any(q in tag.lower() for tag in t.get("process_tags", []))
    ]
    return {"tips": results, "count": len(results)}


# --- Flask routes ---

@tips_routes.route("/tips", methods=["GET"])
def route_list_tips():
    category = request.args.get("category")
    verified_str = request.args.get("verified")
    verified = None
    if verified_str is not None:
        verified = verified_str.lower() == "true"
    return jsonify(list_tips(category=category, verified=verified))


@tips_routes.route("/tips/search", methods=["GET"])
def route_search_tips():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "q parameter required"}), 400
    return jsonify(search_tips(q))


@tips_routes.route("/tips", methods=["POST"])
def route_add_tip():
    body = request.get_json(silent=True) or {}
    result = add_tip(
        title=body.get("title", ""),
        problem=body.get("problem", ""),
        solution=body.get("solution", ""),
        category=body.get("category", "general"),
        process_tags=body.get("process_tags"),
        verified=body.get("verified", True),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 201


@tips_routes.route("/tips/<tip_id>", methods=["GET"])
def route_get_tip(tip_id):
    result = get_tip(tip_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@tips_routes.route("/tips/<tip_id>", methods=["PATCH"])
def route_update_tip(tip_id):
    body = request.get_json(silent=True) or {}
    result = update_tip(tip_id, **body)
    if result.get("error") == "not_found":
        return jsonify(result), 404
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@tips_routes.route("/tips/<tip_id>", methods=["DELETE"])
def route_delete_tip(tip_id):
    result = delete_tip(tip_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
