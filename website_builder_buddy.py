import uuid
import json
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

blueprint_routes = Blueprint("blueprint", __name__)

PROJECT_TYPES = {"furniture", "storage", "decor", "structural", "repair", "outdoor", "custom"}
SKILL_LEVELS = {"beginner", "intermediate", "advanced", "professional"}
BUILD_STATUSES = {"draft", "active", "finalized", "sold"}
LOCKED_STATUSES = {"finalized", "sold"}
BUILD_PHASES = {"planning", "sourcing", "in_progress", "assembly", "finishing", "complete"}
PROCESS_TYPES = {
    "milling", "ripping", "crosscutting", "joinery", "assembly", "finishing",
    "measuring", "layout", "sanding", "routing", "drilling", "carving",
    "turning", "gluing", "clamping", "painting", "staining", "other"
}
MATERIAL_UNITS = {"bf", "sheet", "lf", "pc", "oz", "gal", "bag", "sq-ft", "lb", "ft", "in"}

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

def add_build(name: str, description: str = "", project_type: str = "custom",
              skill_level: str = "beginner", difficulty: int = 1,
              phase: str = "planning", estimated_hours: float = 0.0,
              estimated_cost_usd: float = 0.0, notes: str = "",
              dimensions: dict | None = None, tags: list | None = None) -> dict:
    name = name.strip()
    if not name:
        return {"error": "name is required"}
    if estimated_hours < 0:
        return {"error": "estimated_hours must be non-negative"}
    if estimated_cost_usd < 0:
        return {"error": "estimated_cost_usd must be non-negative"}
    if not (1 <= difficulty <= 5):
        return {"error": "difficulty must be 1–5"}
    if project_type not in PROJECT_TYPES:
        project_type = "custom"
    if skill_level not in SKILL_LEVELS:
        skill_level = "beginner"
    if phase not in BUILD_PHASES:
        phase = "planning"

    build_id = str(uuid.uuid4())
    now = _now()
    build = {
        "id": build_id,
        "name": name,
        "description": description,
        "project_type": project_type,
        "skill_level": skill_level,
        "difficulty": difficulty,
        "phase": phase,
        "status": "draft",
        "steps": [],
        "materials": [],
        "required_tool_ids": [],
        "estimated_hours": estimated_hours,
        "estimated_cost_usd": estimated_cost_usd,
        "actual_cost_usd": 0.0,
        "notes": notes,
        "dimensions": dimensions or {},
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

    allowed = {
        "name", "description", "project_type", "skill_level", "difficulty",
        "phase", "estimated_hours", "estimated_cost_usd", "actual_cost_usd",
        "notes", "dimensions", "tags"
    }
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "name":
            value = value.strip()
            if not value:
                return {"error": "name cannot be empty"}
        if key == "estimated_hours" and value < 0:
            return {"error": "estimated_hours must be non-negative"}
        if key == "estimated_cost_usd" and value < 0:
            return {"error": "estimated_cost_usd must be non-negative"}
        if key == "difficulty" and not (1 <= value <= 5):
            return {"error": "difficulty must be 1–5"}
        if key == "project_type" and value not in PROJECT_TYPES:
            value = "custom"
        if key == "skill_level" and value not in SKILL_LEVELS:
            value = "beginner"
        if key == "phase" and value not in BUILD_PHASES:
            return {"error": f"invalid phase '{value}'"}
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

    valid_transitions = {
        "draft": {"active", "finalized"},
        "active": {"draft", "finalized"},
        "finalized": {"sold"},
        "sold": set(),
    }
    current = build["status"]
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


def list_builds(status: str | None = None, phase: str | None = None,
                skill_level: str | None = None, tag: str | None = None) -> dict:
    data = _load()
    builds = list(data["builds"].values())
    if status:
        builds = [b for b in builds if b["status"] == status]
    if phase:
        builds = [b for b in builds if b["phase"] == phase]
    if skill_level:
        builds = [b for b in builds if b["skill_level"] == skill_level]
    if tag:
        builds = [b for b in builds if tag in b.get("tags", [])]
    return {"builds": builds, "count": len(builds)}


def search_builds(query: str) -> dict:
    q = query.lower().strip()
    data = _load()
    results = [
        b for b in data["builds"].values()
        if q in b["name"].lower() or q in b["description"].lower()
        or q in b.get("notes", "").lower()
        or any(q in t.lower() for t in b.get("tags", []))
    ]
    return {"builds": results, "count": len(results)}


# --- Steps ---

def add_step(build_id: str, title: str, notes: str = "",
             process_type: str = "other", estimated_minutes: int = 0,
             alternatives: str = "", step_tool_ids: list | None = None,
             step_material_ids: list | None = None,
             tip_ids: list | None = None) -> dict:
    title = title.strip()
    if not title:
        return {"error": "title is required"}
    if process_type not in PROCESS_TYPES:
        process_type = "other"

    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked", "message": "Cannot modify a finalized or sold build."}

    step = {
        "id": str(uuid.uuid4()),
        "order": len(build["steps"]) + 1,
        "title": title,
        "notes": notes,
        "process_type": process_type,
        "estimated_minutes": max(0, estimated_minutes),
        "alternatives": alternatives,
        "step_tool_ids": step_tool_ids or [],
        "step_material_ids": step_material_ids or [],
        "tip_ids": tip_ids or [],
        "completed": False,
        "completed_at": None,
    }
    build["steps"].append(step)
    build["updated_at"] = _now()
    _save(data)
    return {"step": step, "build_id": build_id}


def update_step(build_id: str, step_id: str, **fields) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}
    step = next((s for s in build["steps"] if s["id"] == step_id), None)
    if not step:
        return {"error": "step_not_found"}

    allowed = {"title", "notes", "process_type", "estimated_minutes",
               "alternatives", "step_tool_ids", "step_material_ids", "tip_ids"}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "title":
            value = value.strip()
            if not value:
                return {"error": "title cannot be empty"}
        if key == "process_type" and value not in PROCESS_TYPES:
            value = "other"
        step[key] = value

    build["updated_at"] = _now()
    _save(data)
    return {"step": step}


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
    if set(step_ids) != {s["id"] for s in build["steps"]}:
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


# --- Materials ---

def add_material(build_id: str, name: str, qty: float = 1.0,
                 unit: str = "pc", species_or_grade: str = "",
                 dimensions: dict | None = None, cost_per_unit: float = 0.0,
                 vendor: str = "", sourced: bool = False, notes: str = "") -> dict:
    name = name.strip()
    if not name:
        return {"error": "name is required"}
    if unit not in MATERIAL_UNITS:
        return {"error": f"unit must be one of {sorted(MATERIAL_UNITS)}"}
    if qty <= 0:
        return {"error": "qty must be greater than 0"}
    if cost_per_unit < 0:
        return {"error": "cost_per_unit must be non-negative"}

    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}

    total_cost = round(qty * cost_per_unit, 2)
    material = {
        "id": str(uuid.uuid4()),
        "name": name,
        "species_or_grade": species_or_grade,
        "qty": qty,
        "unit": unit,
        "dimensions": dimensions or {},
        "cost_per_unit": cost_per_unit,
        "total_cost": total_cost,
        "vendor": vendor,
        "sourced": sourced,
        "notes": notes,
    }
    build["materials"].append(material)
    build["actual_cost_usd"] = round(
        sum(m["total_cost"] for m in build["materials"]), 2
    )
    build["updated_at"] = _now()
    _save(data)
    return {"material": material, "build_id": build_id}


def update_material(build_id: str, material_id: str, **fields) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}
    mat = next((m for m in build["materials"] if m["id"] == material_id), None)
    if not mat:
        return {"error": "material_not_found"}

    allowed = {"name", "species_or_grade", "qty", "unit", "dimensions",
               "cost_per_unit", "vendor", "sourced", "notes"}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "qty" and value <= 0:
            return {"error": "qty must be greater than 0"}
        if key == "cost_per_unit" and value < 0:
            return {"error": "cost_per_unit must be non-negative"}
        if key == "unit" and value not in MATERIAL_UNITS:
            return {"error": f"invalid unit '{value}'"}
        mat[key] = value

    mat["total_cost"] = round(mat["qty"] * mat["cost_per_unit"], 2)
    build["actual_cost_usd"] = round(
        sum(m["total_cost"] for m in build["materials"]), 2
    )
    build["updated_at"] = _now()
    _save(data)
    return {"material": mat}


def mark_material_sourced(build_id: str, material_id: str, sourced: bool = True) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    mat = next((m for m in build["materials"] if m["id"] == material_id), None)
    if not mat:
        return {"error": "material_not_found"}
    mat["sourced"] = sourced
    build["updated_at"] = _now()
    _save(data)
    return {"material": mat}


def delete_material(build_id: str, material_id: str) -> dict:
    data = _load()
    build = data["builds"].get(build_id)
    if not build:
        return {"error": "not_found"}
    if _is_locked(build):
        return {"error": "locked"}
    original = len(build["materials"])
    build["materials"] = [m for m in build["materials"] if m["id"] != material_id]
    if len(build["materials"]) == original:
        return {"error": "material_not_found"}
    build["actual_cost_usd"] = round(
        sum(m["total_cost"] for m in build["materials"]), 2
    )
    build["updated_at"] = _now()
    _save(data)
    return {"deleted_material_id": material_id}


# --- Required tools (project level) ---

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
        phase=request.args.get("phase"),
        skill_level=request.args.get("skill_level"),
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
        project_type=body.get("project_type", "custom"),
        skill_level=body.get("skill_level", "beginner"),
        difficulty=body.get("difficulty", 1),
        phase=body.get("phase", "planning"),
        estimated_hours=body.get("estimated_hours", 0.0),
        estimated_cost_usd=body.get("estimated_cost_usd", 0.0),
        notes=body.get("notes", ""),
        dimensions=body.get("dimensions"),
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
    result = add_step(
        build_id,
        title=body.get("title", ""),
        notes=body.get("notes", ""),
        process_type=body.get("process_type", "other"),
        estimated_minutes=body.get("estimated_minutes", 0),
        alternatives=body.get("alternatives", ""),
        step_tool_ids=body.get("step_tool_ids"),
        step_material_ids=body.get("step_material_ids"),
        tip_ids=body.get("tip_ids"),
    )
    if "error" in result:
        return jsonify(result), 404 if result["error"] == "not_found" else 400
    return jsonify(result), 201


@blueprint_routes.route("/builds/<build_id>/steps/<step_id>", methods=["PATCH"])
def route_update_step(build_id, step_id):
    body = request.get_json(silent=True) or {}
    result = update_step(build_id, step_id, **body)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


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


@blueprint_routes.route("/builds/<build_id>/materials", methods=["POST"])
def route_add_material(build_id):
    body = request.get_json(silent=True) or {}
    result = add_material(
        build_id,
        name=body.get("name", ""),
        qty=body.get("qty", 1.0),
        unit=body.get("unit", "pc"),
        species_or_grade=body.get("species_or_grade", ""),
        dimensions=body.get("dimensions"),
        cost_per_unit=body.get("cost_per_unit", 0.0),
        vendor=body.get("vendor", ""),
        sourced=body.get("sourced", False),
        notes=body.get("notes", ""),
    )
    if "error" in result:
        return jsonify(result), 404 if result["error"] == "not_found" else 400
    return jsonify(result), 201


@blueprint_routes.route("/builds/<build_id>/materials/<material_id>", methods=["PATCH"])
def route_update_material(build_id, material_id):
    body = request.get_json(silent=True) or {}
    result = update_material(build_id, material_id, **body)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/materials/<material_id>/sourced", methods=["PATCH"])
def route_mark_sourced(build_id, material_id):
    body = request.get_json(silent=True) or {}
    result = mark_material_sourced(build_id, material_id, sourced=body.get("sourced", True))
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@blueprint_routes.route("/builds/<build_id>/materials/<material_id>", methods=["DELETE"])
def route_delete_material(build_id, material_id):
    result = delete_material(build_id, material_id)
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
