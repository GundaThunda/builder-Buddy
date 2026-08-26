import uuid
import json
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

blueprint_routes = Blueprint("blueprint", __name__)

BUILD_STATUSES = {"draft", "active", "finalized", "sold"}
LOCKED_STATUSES = {"finalized", "sold"}
VALID_UNITS = {"in", "mm", "ft", "cm"}

DATA_FILE = os.path.join(os.path.dirname(__file__), "blueprint_data.json")


def _load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"builds": {}}


def _save(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_locked(build: dict) -> bool:
    return build.get("status") in LOCKED_STATUSES


# --- Build CRUD ---

def add_build(name: str, description: str = "", estimated_hours: float = 0.0,
              tags: list | None = None) -> dict:
    name = name.strip()
    if not name:
        return {"error": "name is required"}
    if estimated_hours < 0:
        return {"error": "estimated_hours must be non-negative"}

    build_id = str(uuid.uuid4())
    now = _now()
    build = {
        "id": build_id,
        "name": name,
        "description": description,
        "status": "draft",
        "steps": [],
        "cut_list": [],
        "required_tool_ids": [],
        "estimated_hours": estimated_hours,
        "tags": tags or [],
        "created_at": now,
        "updated_at": now,
        "finalized_at": None,
    }
    data = _load()
    data["builds"][build_id] = build
    _save(data)
    return {"build": build}


def get_build(build_id: str) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    return {"build": build}


def update_build(build_id: str, **fields) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked", "message": "Finalized and sold builds cannot be edited."}

    allowed = {"name", "description", "estimated_hours", "tags"}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "name":
            value = value.strip()
            if not value:
                return {"error": "name cannot be empty"}
        if key == "estimated_hours" and value < 0:
            return {"error": "estimated_hours must be non-negative"}
        build[key] = value

    build["updated_at"] = _now()
    data["builds"][build_id] = build
    _save(data)
    return {"build": build}


def set_build_status(build_id: str, status: str) -> dict:
    if status not in BUILD_STATUSES:
        return {"error": f"invalid status '{status}'"}
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}

    current = build["status"]
    valid_transitions = {
        "draft": {"active", "finalized"},
        "active": {"draft", "finalized"},
        "finalized": {"sold"},
        "sold": set(),
    }
    if status not in valid_transitions.get(current, set()):
        return {"error": f"cannot transition from '{current}' to '{status}'"}

    build["status"] = status
    build["updated_at"] = _now()
    if status == "finalized":
        build["finalized_at"] = _now()
    data["builds"][build_id] = build
    _save(data)
    return {"build": build}


def delete_build(build_id: str) -> dict:
    data = _load()
    if build_id not in data["builds"]:
        return {"error": "not_found"}
    removed = data["builds"].pop(build_id)
    _save(data)
    return {"deleted": removed}


def list_builds(status: str | None = None, tag: str | None = None) -> dict:
    data = _load()
    builds = list(data["builds"].values())
    if status:
        builds = [b for b in builds if b["status"] == status]
    if tag:
        builds = [b for b in builds if tag in b.get("tags", [])]
    return {"builds": builds, "count": len(builds)}


def search_builds(query: str) -> dict:
    q = query.lower().strip()
    data = _load()
    results = [
        b for b in data["builds"].values()
        if q in b["name"].lower() or q in b["description"].lower()
        or any(q in t.lower() for t in b.get("tags", []))
    ]
    return {"builds": results, "count": len(results)}


# --- Steps ---

def add_step(build_id: str, title: str, notes: str = "") -> dict:
    title = title.strip()
    if not title:
        return {"error": "title is required"}
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked", "message": "Cannot modify a finalized or sold build."}

    order = len(build["steps"]) + 1
    step = {
        "id": str(uuid.uuid4()),
        "order": order,
        "title": title,
        "notes": notes,
        "completed": False,
        "completed_at": None,
    }
    build["steps"].append(step)
    build["updated_at"] = _now()
    _save(data)
    return {"step": step, "build_id": build_id}


def complete_step(build_id: str, step_id: str, completed: bool = True) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    step = next((s for s in build["steps"] if s["id"] == step_id), None)
    if not step:
        return {"error": "step_not_found"}
    step["completed"] = completed
    step["completed_at"] = _now() if completed else None
    build["updated_at"] = _now()
    _save(data)
    return {"step": step}


def reorder_steps(build_id: str, step_ids: list) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}
    existing_ids = {s["id"] for s in build["steps"]}
    if set(step_ids) != existing_ids:
        return {"error": "step_ids must match existing steps exactly"}

    step_map = {s["id"]: s for s in build["steps"]}
    build["steps"] = [dict(step_map[sid], order=i + 1) for i, sid in enumerate(step_ids)]
    build["updated_at"] = _now()
    _save(data)
    return {"steps": build["steps"]}


def delete_step(build_id: str, step_id: str) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}
    original = len(build["steps"])
    build["steps"] = [s for s in build["steps"] if s["id"] != step_id]
    if len(build["steps"]) == original:
        return {"error": "step_not_found"}
    for i, s in enumerate(build["steps"]):
        s["order"] = i + 1
    build["updated_at"] = _now()
    _save(data)
    return {"deleted_step_id": step_id}


# --- Cut list ---

def add_cut(build_id: str, material: str, qty: int = 1,
            length: float = 0.0, width: float = 0.0, thickness: float = 0.0,
            unit: str = "in", notes: str = "") -> dict:
    material = material.strip()
    if not material:
        return {"error": "material is required"}
    if unit not in VALID_UNITS:
        return {"error": f"unit must be one of {sorted(VALID_UNITS)}"}
    if qty < 1:
        return {"error": "qty must be at least 1"}

    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}

    cut = {
        "id": str(uuid.uuid4()),
        "material": material,
        "qty": qty,
        "length": length,
        "width": width,
        "thickness": thickness,
        "unit": unit,
        "notes": notes,
    }
    build["cut_list"].append(cut)
    build["updated_at"] = _now()
    _save(data)
    return {"cut": cut, "build_id": build_id}


def delete_cut(build_id: str, cut_id: str) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}
    original = len(build["cut_list"])
    build["cut_list"] = [c for c in build["cut_list"] if c["id"] != cut_id]
    if len(build["cut_list"]) == original:
        return {"error": "cut_not_found"}
    build["updated_at"] = _now()
    _save(data)
    return {"deleted_cut_id": cut_id}


# --- Required tools ---

def link_tool(build_id: str, tool_id: str) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}
    if tool_id in build["required_tool_ids"]:
        return {"error": "tool_already_linked"}
    build["required_tool_ids"].append(tool_id)
    build["updated_at"] = _now()
    _save(data)
    return {"required_tool_ids": build["required_tool_ids"]}


def unlink_tool(build_id: str, tool_id: str) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if tool_id not in build["required_tool_ids"]:
        return {"error": "tool_not_linked"}
    build["required_tool_ids"].remove(tool_id)
    build["updated_at"] = _now()
    _save(data)
    return {"required_tool_ids": build["required_tool_ids"]}


# --- Flask routes ---

@blueprint_routes.route("/builds", methods=["GET"])
def route_list_builds():
    return jsonify(list_builds(
        status=request.args.get("status"),
        tag=request.args.get("tag"),
    ))


@blueprint_routes.route("/builds/search", methods=["GET"])
def route_search_builds():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "q parameter required"}), 400
    return jsonify(search_builds(q))


@blueprint_routes.route("/builds", methods=["POST"])
def route_add_build():
    body = request.get_json(silent=True) or {}
    result = add_build(
        name=body.get("name", ""),
        description=body.get("description", ""),
        estimated_hours=body.get("estimated_hours", 0.0),
        tags=body.get("tags"),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 201


@blueprint_routes.route("/builds/<build_id>", methods=["GET"])
def route_get_build(build_id):
    result = get_build(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>", methods=["PATCH"])
def route_update_build(build_id):
    body = request.get_json(silent=True) or {}
    result = update_build(build_id, **body)
    if result.get("error") == "not_found":
        return jsonify(result), 404
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/status", methods=["PATCH"])
def route_set_status(build_id):
    body = request.get_json(silent=True) or {}
    result = set_build_status(build_id, body.get("status", ""))
    if result.get("error") == "not_found":
        return jsonify(result), 404
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>", methods=["DELETE"])
def route_delete_build(build_id):
    result = delete_build(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/steps", methods=["POST"])
def route_add_step(build_id):
    body = request.get_json(silent=True) or {}
    result = add_step(build_id, title=body.get("title", ""), notes=body.get("notes", ""))
    if "error" in result:
        code = 404 if result["error"] == "not_found" else 400
        return jsonify(result), code
    return jsonify(result), 201


@blueprint_routes.route("/builds/<build_id>/steps/<step_id>/complete", methods=["PATCH"])
def route_complete_step(build_id, step_id):
    body = request.get_json(silent=True) or {}
    result = complete_step(build_id, step_id, completed=body.get("completed", True))
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/steps/reorder", methods=["PATCH"])
def route_reorder_steps(build_id):
    body = request.get_json(silent=True) or {}
    result = reorder_steps(build_id, body.get("step_ids", []))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/steps/<step_id>", methods=["DELETE"])
def route_delete_step(build_id, step_id):
    result = delete_step(build_id, step_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/cuts", methods=["POST"])
def route_add_cut(build_id):
    body = request.get_json(silent=True) or {}
    result = add_cut(
        build_id,
        material=body.get("material", ""),
        qty=body.get("qty", 1),
        length=body.get("length", 0.0),
        width=body.get("width", 0.0),
        thickness=body.get("thickness", 0.0),
        unit=body.get("unit", "in"),
        notes=body.get("notes", ""),
    )
    if "error" in result:
        code = 404 if result["error"] == "not_found" else 400
        return jsonify(result), code
    return jsonify(result), 201


@blueprint_routes.route("/builds/<build_id>/cuts/<cut_id>", methods=["DELETE"])
def route_delete_cut(build_id, cut_id):
    result = delete_cut(build_id, cut_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/tools", methods=["POST"])
def route_link_tool(build_id):
    body = request.get_json(silent=True) or {}
    result = link_tool(build_id, body.get("tool_id", ""))
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/tools/<tool_id>", methods=["DELETE"])
def route_unlink_tool(build_id, tool_id):
    result = unlink_tool(build_id, tool_id)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
