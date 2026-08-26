import uuid
import json
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from website_builder_buddy import get_build

silhouette_routes = Blueprint("silhouette", __name__)

SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), "silhouette_data.json")


def _load() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r") as f:
            return json.load(f)
    return {"snapshots": {}}


def _save(data: dict) -> None:
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Presentation generators ---

def generate_overview(build_id: str) -> dict:
    result = get_build(build_id)
    if "error" in result:
        return result
    b = result["build"]
    total_steps = len(b["steps"])
    completed_steps = sum(1 for s in b["steps"] if s["completed"])
    return {
        "overview": {
            "build_id": b["id"],
            "name": b["name"],
            "description": b["description"],
            "status": b["status"],
            "estimated_hours": b["estimated_hours"],
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "progress_pct": round((completed_steps / total_steps * 100) if total_steps else 0, 1),
            "tags": b["tags"],
            "created_at": b["created_at"],
            "finalized_at": b["finalized_at"],
        }
    }


def generate_step_list(build_id: str) -> dict:
    result = get_build(build_id)
    if "error" in result:
        return result
    b = result["build"]
    steps = sorted(b["steps"], key=lambda s: s["order"])
    return {
        "build_id": build_id,
        "build_name": b["name"],
        "steps": steps,
        "total": len(steps),
        "completed": sum(1 for s in steps if s["completed"]),
    }


def generate_cut_list(build_id: str) -> dict:
    result = get_build(build_id)
    if "error" in result:
        return result
    b = result["build"]
    cuts = b["cut_list"]
    by_material: dict = {}
    for cut in cuts:
        mat = cut["material"]
        by_material.setdefault(mat, []).append(cut)
    return {
        "build_id": build_id,
        "build_name": b["name"],
        "cut_list": cuts,
        "by_material": by_material,
        "total_pieces": sum(c["qty"] for c in cuts),
    }


def generate_tools_list(build_id: str) -> dict:
    result = get_build(build_id)
    if "error" in result:
        return result
    b = result["build"]
    return {
        "build_id": build_id,
        "build_name": b["name"],
        "required_tool_ids": b["required_tool_ids"],
        "tool_count": len(b["required_tool_ids"]),
    }


def generate_presentation(build_id: str) -> dict:
    overview = generate_overview(build_id)
    if "error" in overview:
        return overview
    steps = generate_step_list(build_id)
    cuts = generate_cut_list(build_id)
    tools = generate_tools_list(build_id)
    return {
        "presentation": {
            "overview": overview["overview"],
            "steps": steps["steps"],
            "cut_list": cuts["cut_list"],
            "cut_list_by_material": cuts["by_material"],
            "required_tool_ids": tools["required_tool_ids"],
        }
    }


# --- Snapshots ---

def create_snapshot(build_id: str, label: str = "") -> dict:
    result = get_build(build_id)
    if "error" in result:
        return result
    presentation = generate_presentation(build_id)
    if "error" in presentation:
        return presentation

    snap_id = str(uuid.uuid4())
    snapshot = {
        "id": snap_id,
        "build_id": build_id,
        "label": label.strip() or f"Snapshot {_now()}",
        "captured_at": _now(),
        "content": presentation["presentation"],
    }
    data = _load()
    data["snapshots"][snap_id] = snapshot
    _save(data)
    return {"snapshot": snapshot}


def get_snapshot(snap_id: str) -> dict:
    data = _load()
    snap = data["snapshots"].get(snap_id)
    if not snap:
        return {"error": "not_found"}
    return {"snapshot": snap}


def list_snapshots(build_id: str | None = None) -> dict:
    data = _load()
    snaps = list(data["snapshots"].values())
    if build_id:
        snaps = [s for s in snaps if s["build_id"] == build_id]
    return {"snapshots": snaps, "count": len(snaps)}


def delete_snapshot(snap_id: str) -> dict:
    data = _load()
    if snap_id not in data["snapshots"]:
        return {"error": "not_found"}
    removed = data["snapshots"].pop(snap_id)
    _save(data)
    return {"deleted": removed}


# --- Flask routes ---

@silhouette_routes.route("/overview/<build_id>", methods=["GET"])
def route_overview(build_id):
    result = generate_overview(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@silhouette_routes.route("/steps/<build_id>", methods=["GET"])
def route_steps(build_id):
    result = generate_step_list(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@silhouette_routes.route("/cuts/<build_id>", methods=["GET"])
def route_cuts(build_id):
    result = generate_cut_list(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@silhouette_routes.route("/tools/<build_id>", methods=["GET"])
def route_tools(build_id):
    result = generate_tools_list(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@silhouette_routes.route("/presentation/<build_id>", methods=["GET"])
def route_presentation(build_id):
    result = generate_presentation(build_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@silhouette_routes.route("/snapshots", methods=["GET"])
def route_list_snapshots():
    build_id = request.args.get("build_id")
    return jsonify(list_snapshots(build_id))


@silhouette_routes.route("/snapshots", methods=["POST"])
def route_create_snapshot():
    body = request.get_json(silent=True) or {}
    build_id = body.get("build_id", "")
    if not build_id:
        return jsonify({"error": "build_id required"}), 400
    result = create_snapshot(build_id, label=body.get("label", ""))
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 201


@silhouette_routes.route("/snapshots/<snap_id>", methods=["GET"])
def route_get_snapshot(snap_id):
    result = get_snapshot(snap_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@silhouette_routes.route("/snapshots/<snap_id>", methods=["DELETE"])
def route_delete_snapshot(snap_id):
    result = delete_snapshot(snap_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
