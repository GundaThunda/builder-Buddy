"""
Plan content store: one record per unique plan body, branches grouped in their
own file under the base record, and separate download counters.

Layout (STORE_DIR, gitignored):
  index.json          hash -> content_id, plus one post record per submission
  <content_id>.json   base record: original author, body, x, branches, y

Counters:
  downloads_x  downloads of the original content, including reposts of it
  downloads_y  downloads of branches (matches) linked to the original

Attribution:
  original_author is fixed on the base record. Reposts never change it.
  Each branch records its own uploader.

Not built yet: near-duplicate detection, notifications, disputes, match rules.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from website_gate import require_auth

plan_routes = Blueprint("plans", __name__)

STORE_DIR = os.path.join(os.path.dirname(__file__), "plan_store")
MAX_STEPS = 500
MAX_MATERIALS = 500

STEP_FIELDS = ("title", "notes", "process_type", "estimated_minutes", "alternatives")
MATERIAL_FIELDS = ("name", "qty", "unit", "species_or_grade", "dimensions",
                   "cost_per_unit", "vendor", "notes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _valid_id(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


# --- canonical body and hash ---

def canonical_body(body: dict) -> dict:
    """Only the fields that define the plan. IDs, timestamps and unknown keys are dropped."""
    steps = [{k: s.get(k) for k in STEP_FIELDS} for s in body.get("steps", [])]
    materials = sorted(({k: m.get(k) for k in MATERIAL_FIELDS} for m in body.get("materials", [])),
                       key=_json)
    return {"steps": steps, "materials": materials, "dimensions": body.get("dimensions") or {}}


def content_hash(body: dict) -> str:
    return hashlib.sha256(_json(canonical_body(body)).encode("utf-8")).hexdigest()


def _validate_body(body) -> str | None:
    if not isinstance(body, dict):
        return "body must be an object"
    steps = body.get("steps", [])
    materials = body.get("materials", [])
    dims = body.get("dimensions", {})
    if not isinstance(steps, list) or not isinstance(materials, list):
        return "steps and materials must be lists"
    if len(steps) > MAX_STEPS or len(materials) > MAX_MATERIALS:
        return "too many steps or materials"
    if not isinstance(dims, dict):
        return "dimensions must be an object"
    if not all(isinstance(s, dict) and str(s.get("title", "")).strip() for s in steps):
        return "every step needs a title"
    if not all(isinstance(m, dict) and str(m.get("name", "")).strip() for m in materials):
        return "every material needs a name"
    if not steps and not materials:
        return "plan body is empty"
    return None


# --- storage ---

def _index_path() -> str:
    return os.path.join(STORE_DIR, "index.json")


def _load_index() -> dict:
    if os.path.exists(_index_path()):
        with open(_index_path()) as f:
            return json.load(f)
    return {"by_hash": {}, "posts": {}}


def _save_index(idx: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(_index_path(), "w") as f:
        json.dump(idx, f, indent=2)


def _load_content(content_id: str) -> dict | None:
    if not _valid_id(content_id):
        return None
    path = os.path.join(STORE_DIR, f"{content_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_content(rec: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(os.path.join(STORE_DIR, f"{rec['content_id']}.json"), "w") as f:
        json.dump(rec, f, indent=2)


# --- operations ---

def submit_plan(author: str, body) -> dict:
    err = _validate_body(body)
    if err:
        return {"error": err}
    h = content_hash(body)
    idx = _load_index()
    now = _now()
    post_id = str(uuid.uuid4())

    existing = idx["by_hash"].get(h)
    if existing:
        idx["posts"][post_id] = {"content_id": existing, "poster": author,
                                 "kind": "repost", "created_at": now}
        _save_index(idx)
        return {"status": "exact_duplicate", "content_id": existing, "post_id": post_id}

    content_id = str(uuid.uuid4())
    _save_content({
        "content_id": content_id, "hash": h, "original_author": author,
        "body": canonical_body(body), "created_at": now,
        "downloads_x": 0, "downloads_y": 0, "branches": {},
    })
    idx["by_hash"][h] = content_id
    idx["posts"][post_id] = {"content_id": content_id, "poster": author,
                             "kind": "original", "created_at": now}
    _save_index(idx)
    return {"status": "new", "content_id": content_id, "post_id": post_id}


def add_branch(author: str, content_id: str, body) -> dict:
    rec = _load_content(content_id)
    if rec is None:
        return {"error": "not_found"}
    err = _validate_body(body)
    if err:
        return {"error": err}
    h = content_hash(body)
    if h == rec["hash"]:
        return {"error": "exact_duplicate"}
    if any(b["hash"] == h for b in rec["branches"].values()):
        return {"error": "duplicate_branch"}
    branch_id = str(uuid.uuid4())
    rec["branches"][branch_id] = {
        "branch_id": branch_id, "uploader": author, "hash": h,
        "body": canonical_body(body), "created_at": _now(), "downloads": 0,
    }
    _save_content(rec)
    return {"branch_id": branch_id, "content_id": content_id}


def record_download(content_id: str, branch_id: str | None = None) -> dict:
    rec = _load_content(content_id)
    if rec is None:
        return {"error": "not_found"}
    if branch_id is None:
        rec["downloads_x"] += 1
    else:
        branch = rec["branches"].get(branch_id)
        if not branch:
            return {"error": "not_found"}
        branch["downloads"] += 1
        rec["downloads_y"] += 1
    _save_content(rec)
    return {"content_id": content_id, "downloads_x": rec["downloads_x"],
            "downloads_y": rec["downloads_y"]}


def get_plan(content_id: str) -> dict:
    rec = _load_content(content_id)
    if rec is None:
        return {"error": "not_found"}
    posts = sum(1 for p in _load_index()["posts"].values() if p["content_id"] == content_id)
    return {
        "content_id": content_id,
        "original_author": rec["original_author"],
        "body": rec["body"],
        "downloads_x": rec["downloads_x"],
        "downloads_y": rec["downloads_y"],
        "post_count": posts,
        "branches": [
            {"branch_id": b["branch_id"], "uploader": b["uploader"],
             "created_at": b["created_at"], "downloads": b["downloads"], "body": b["body"]}
            for b in rec["branches"].values()
        ],
    }


# --- routes ---

def _body_from_request() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@plan_routes.route("", methods=["POST"])
@require_auth()
def route_submit_plan():
    from flask import g
    result = submit_plan(g.auth_user, _body_from_request())
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 201


@plan_routes.route("/<content_id>", methods=["GET"])
def route_get_plan(content_id):
    result = get_plan(content_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@plan_routes.route("/<content_id>/branches", methods=["POST"])
@require_auth()
def route_add_branch(content_id):
    from flask import g
    result = add_branch(g.auth_user, content_id, _body_from_request())
    if "error" in result:
        status = {"not_found": 404, "exact_duplicate": 409, "duplicate_branch": 409}.get(
            result["error"], 400)
        return jsonify(result), status
    return jsonify(result), 201


@plan_routes.route("/<content_id>/download", methods=["POST"])
@require_auth()
def route_download(content_id):
    result = record_download(content_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@plan_routes.route("/<content_id>/branches/<branch_id>/download", methods=["POST"])
@require_auth()
def route_download_branch(content_id, branch_id):
    result = record_download(content_id, branch_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
