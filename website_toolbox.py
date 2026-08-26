import uuid
import json
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

toolbox_routes = Blueprint("toolbox", __name__)

ITEM_TYPES = {"tool", "upgrade", "hardware", "material"}
ITEM_STATUSES = {"owned", "wishlist"}
CATEGORIES = {
    "General", "Power Tools", "Hand Tools", "Measuring", "Finishing",
    "Fasteners", "Lumber", "Sheet Goods", "Hardware", "Safety",
    "Specialty", "Uncategorized"
}

DATA_FILE = os.path.join(os.path.dirname(__file__), "toolbox_data.json")


def _load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"items": {}}


def _save(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _smart_route(name: str, item_type: str | None, category: str | None) -> str:
    """Infer item_type from name/category when not provided."""
    if item_type and item_type in ITEM_TYPES:
        return item_type
    name_lower = name.lower()
    if any(w in name_lower for w in ("screw", "bolt", "nail", "washer", "nut", "anchor")):
        return "hardware"
    if any(w in name_lower for w in ("blade", "bit", "sandpaper", "abrasive", "disc", "wheel")):
        return "upgrade"
    if any(w in name_lower for w in ("wood", "plywood", "lumber", "mdf", "oak", "pine", "maple", "walnut", "cedar")):
        return "material"
    return "tool"


def _find_duplicates(data: dict, name: str, item_type: str) -> list:
    name_lower = name.lower().strip()
    return [
        item for item in data["items"].values()
        if item["name"].lower().strip() == name_lower and item["type"] == item_type
    ]


# --- Core functions (used directly and via routes) ---

def add_item(name: str, item_type: str | None = None, category: str | None = None,
             status: str = "owned", wishlist_rating: int | None = None,
             tags: list | None = None, linked_items: list | None = None) -> dict:
    """Add an item. Returns {"item": {...}} or {"error": ..., "duplicates": [...]}."""
    name = name.strip()
    if not name:
        return {"error": "name is required"}

    resolved_type = _smart_route(name, item_type, category)
    resolved_category = category if category in CATEGORIES else "Uncategorized"
    status = status if status in ITEM_STATUSES else "owned"

    if status == "wishlist" and wishlist_rating is not None:
        if not (1 <= wishlist_rating <= 5):
            return {"error": "wishlist_rating must be 1–5"}
    if status == "owned":
        wishlist_rating = None

    data = _load()
    dupes = _find_duplicates(data, name, resolved_type)
    if dupes:
        return {"error": "duplicate_detected", "duplicates": dupes,
                "message": f"'{name}' already exists as a {resolved_type}. Clarify before adding."}

    item_id = str(uuid.uuid4())
    now = _now()
    item = {
        "id": item_id,
        "name": name,
        "type": resolved_type,
        "category": resolved_category,
        "status": status,
        "wishlist_rating": wishlist_rating,
        "tags": tags or [],
        "linked_items": linked_items or [],
        "created_at": now,
        "updated_at": now,
    }
    data["items"][item_id] = item
    _save(data)
    return {"item": item}


def get_item(item_id: str) -> dict:
    data = _load()
    item = data["items"].get(item_id)
    if not item:
        return {"error": "not_found"}
    return {"item": item}


def update_item(item_id: str, **fields) -> dict:
    data = _load()
    item = data["items"].get(item_id)
    if not item:
        return {"error": "not_found"}

    allowed = {"name", "category", "status", "wishlist_rating", "tags", "linked_items"}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "category":
            value = value if value in CATEGORIES else "Uncategorized"
        if key == "status" and value not in ITEM_STATUSES:
            return {"error": f"invalid status '{value}'"}
        if key == "wishlist_rating" and value is not None and not (1 <= value <= 5):
            return {"error": "wishlist_rating must be 1–5"}
        item[key] = value

    if item.get("status") == "owned":
        item["wishlist_rating"] = None

    item["updated_at"] = _now()
    data["items"][item_id] = item
    _save(data)
    return {"item": item}


def delete_item(item_id: str) -> dict:
    data = _load()
    if item_id not in data["items"]:
        return {"error": "not_found"}
    removed = data["items"].pop(item_id)
    _save(data)
    return {"deleted": removed}


def list_items(item_type: str | None = None, status: str | None = None,
               category: str | None = None) -> dict:
    data = _load()
    items = list(data["items"].values())
    if item_type:
        items = [i for i in items if i["type"] == item_type]
    if status:
        items = [i for i in items if i["status"] == status]
    if category:
        items = [i for i in items if i["category"] == category]
    return {"items": items, "count": len(items)}


def search_items(query: str) -> dict:
    query_lower = query.lower().strip()
    data = _load()
    results = [
        item for item in data["items"].values()
        if query_lower in item["name"].lower()
        or query_lower in item["category"].lower()
        or any(query_lower in tag.lower() for tag in item.get("tags", []))
    ]
    return {"items": results, "count": len(results)}


# --- Flask routes ---

@toolbox_routes.route("/items", methods=["GET"])
def route_list_items():
    item_type = request.args.get("type")
    status = request.args.get("status")
    category = request.args.get("category")
    return jsonify(list_items(item_type, status, category))


@toolbox_routes.route("/items/search", methods=["GET"])
def route_search_items():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "q parameter required"}), 400
    return jsonify(search_items(query))


@toolbox_routes.route("/items", methods=["POST"])
def route_add_item():
    body = request.get_json(silent=True) or {}
    result = add_item(
        name=body.get("name", ""),
        item_type=body.get("type"),
        category=body.get("category"),
        status=body.get("status", "owned"),
        wishlist_rating=body.get("wishlist_rating"),
        tags=body.get("tags"),
        linked_items=body.get("linked_items"),
    )
    if "error" in result:
        code = 409 if result["error"] == "duplicate_detected" else 400
        return jsonify(result), code
    return jsonify(result), 201


@toolbox_routes.route("/items/<item_id>", methods=["GET"])
def route_get_item(item_id):
    result = get_item(item_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@toolbox_routes.route("/items/<item_id>", methods=["PATCH"])
def route_update_item(item_id):
    body = request.get_json(silent=True) or {}
    result = update_item(item_id, **body)
    if result.get("error") == "not_found":
        return jsonify(result), 404
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@toolbox_routes.route("/items/<item_id>", methods=["DELETE"])
def route_delete_item(item_id):
    result = delete_item(item_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
