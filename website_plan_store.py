"""
Plan content store: one record per unique plan body, branches stored as
step-level deltas against the original, and separate download counters.

Layout (STORE_DIR, gitignored):
  index.json          hash -> content_id, plus one post record per submission
  <content_id>.json   base record: original author, body, x, branches, y

Branches store only the operations that differ from the base. Every operation
records its uploader, and every step or material in a branch carries an owner:
the original author if untouched, or the branch uploader if changed. A branch
is rebuilt from base + delta and must hash to exactly the uploaded plan, or it
is refused.

Counters:
  downloads_x  downloads of the original content, including reposts of it
  downloads_y  downloads of branches linked to the original

Not built yet: near-duplicate detection, notifications, disputes, match rules.
"""

import difflib
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

import website_safety as safety
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


# --- deltas and attribution ---

def _diff(base_items: list, new_items: list, uploader: str) -> list:
    """Ordered operations turning base_items into new_items. Equal runs are not stored."""
    base_keys = [_json(i) for i in base_items]
    new_keys = [_json(i) for i in new_items]
    matcher = difflib.SequenceMatcher(None, base_keys, new_keys, autojunk=False)
    ops = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ops.append({"op": tag, "base_start": i1, "base_end": i2,
                    "new_items": new_items[j1:j2], "uploader": uploader})
    return ops


def _apply_pairs(base_items: list, base_owner: str, ops: list) -> list:
    """Apply ops to (item, owner) pairs. Opcodes are ordered and non-overlapping,
    so applying them last-to-first keeps earlier indices valid."""
    pairs = [(item, base_owner) for item in base_items]
    for op in reversed(ops):
        replacement = [(item, op["uploader"]) for item in op["new_items"]]
        pairs[op["base_start"]:op["base_end"]] = replacement
    return pairs


def _reconstruct(base: dict, delta: dict, author: str) -> dict:
    """Rebuild a full canonical body from the base plus a delta, with per-item owners."""
    steps = _apply_pairs(base["steps"], author, delta.get("steps", []))
    materials = _apply_pairs(base["materials"], author, delta.get("materials", []))
    dims_owner = delta["dimensions"]["uploader"] if "dimensions" in delta else author
    dims = delta["dimensions"]["to"] if "dimensions" in delta else base["dimensions"]
    return {
        "body": {"steps": [i for i, _ in steps],
                 "materials": [i for i, _ in materials],
                 "dimensions": dims},
        "step_owners": [o for _, o in steps],
        "material_owners": [o for _, o in materials],
        "dimensions_owner": dims_owner,
    }


def _changes_summary(delta: dict) -> list:
    changes = []
    for field in ("steps", "materials"):
        for op in delta.get(field, []):
            changes.append({"field": field, "op": op["op"],
                            "base_range": [op["base_start"], op["base_end"]],
                            "uploader": op["uploader"]})
    if "dimensions" in delta:
        changes.append({"field": "dimensions", "op": "replace",
                        "uploader": delta["dimensions"]["uploader"]})
    return changes


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

def submit_plan(author: str, body, acknowledged=()) -> dict:
    err = _validate_body(body)
    if err:
        return {"error": err}
    gated = safety.gate(safety.check_plan(body), acknowledged)
    if gated:
        return gated
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


def add_branch(author: str, content_id: str, body, acknowledged=()) -> dict:
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

    new = canonical_body(body)
    base = rec["body"]
    # Only hazards this branch adds are gated; the base's hazards were already acknowledged.
    added_hazards = safety.compare_safety(base, new)["new_in_final"]
    gated = safety.gate(added_hazards, acknowledged)
    if gated:
        return gated
    delta = {"steps": _diff(base["steps"], new["steps"], author),
             "materials": _diff(base["materials"], new["materials"], author)}
    if new["dimensions"] != base["dimensions"]:
        delta["dimensions"] = {"from": base["dimensions"], "to": new["dimensions"],
                               "uploader": author}

    rebuilt = _reconstruct(base, delta, rec["original_author"])["body"]
    if content_hash(rebuilt) != h:
        return {"error": "delta_mismatch"}

    branch_id = str(uuid.uuid4())
    rec["branches"][branch_id] = {
        "branch_id": branch_id, "uploader": author, "hash": h,
        "delta": delta, "created_at": _now(), "downloads": 0,
    }
    _save_content(rec)
    return {"branch_id": branch_id, "content_id": content_id}


# Download rate limit: at most DOWNLOAD_LIMIT downloads per user per plan in any
# DOWNLOAD_WINDOW_SECONDS window. Counts only successful downloads toward x/y.
# Persisted under STORE_DIR so it survives restarts. Defaults are starting values.
DOWNLOAD_LIMIT = 20
DOWNLOAD_WINDOW_SECONDS = 3600


def _limits_path() -> str:
    return os.path.join(STORE_DIR, "download_limits.json")


def _load_limits() -> dict:
    path = _limits_path()
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _save_limits(data: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(_limits_path(), "w") as f:
        json.dump(data, f)


def download_allowed(user: str, content_id: str, now: float | None = None) -> bool:
    """Record an attempt and return True if it is within the limit. Checks before counting."""
    now = time.time() if now is None else now
    data = _load_limits()
    key = f"{user}|{content_id}"
    hits = [t for t in data.get(key, []) if now - t < DOWNLOAD_WINDOW_SECONDS]
    if len(hits) >= DOWNLOAD_LIMIT:
        data[key] = hits
        _save_limits(data)
        return False
    hits.append(now)
    data[key] = hits
    _save_limits(data)
    return True


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
    branches = []
    for b in rec["branches"].values():
        rebuilt = _reconstruct(rec["body"], b["delta"], rec["original_author"])
        branches.append({
            "branch_id": b["branch_id"],
            "uploader": b["uploader"],
            "created_at": b["created_at"],
            "downloads": b["downloads"],
            "body": rebuilt["body"],
            "attribution": {
                "step_owners": rebuilt["step_owners"],
                "material_owners": rebuilt["material_owners"],
                "dimensions_owner": rebuilt["dimensions_owner"],
            },
            "changes": _changes_summary(b["delta"]),
        })
    return {
        "content_id": content_id,
        "original_author": rec["original_author"],
        "body": rec["body"],
        "downloads_x": rec["downloads_x"],
        "downloads_y": rec["downloads_y"],
        "post_count": posts,
        "branches": branches,
    }


# --- routes ---

def _body_from_request() -> tuple:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return {}, []
    acknowledged = body.pop("acknowledged", [])
    if not isinstance(acknowledged, list):
        acknowledged = []
    return body, acknowledged


SAFETY_STATUS = {"safety_block": 422, "acknowledgement_required": 409}


@plan_routes.route("", methods=["POST"])
@require_auth()
def route_submit_plan():
    body, acknowledged = _body_from_request()
    result = submit_plan(g.auth_user, body, acknowledged)
    if "error" in result:
        return jsonify(result), SAFETY_STATUS.get(result["error"], 400)
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
    body, acknowledged = _body_from_request()
    result = add_branch(g.auth_user, content_id, body, acknowledged)
    if "error" in result:
        status = {"not_found": 404, "exact_duplicate": 409, "duplicate_branch": 409,
                  "delta_mismatch": 500, **SAFETY_STATUS}.get(result["error"], 400)
        return jsonify(result), status
    return jsonify(result), 201


@plan_routes.route("/<content_id>/download", methods=["POST"])
@require_auth()
def route_download(content_id):
    if not download_allowed(g.auth_user, content_id):
        return jsonify({"error": "rate_limited"}), 429
    result = record_download(content_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@plan_routes.route("/<content_id>/branches/<branch_id>/download", methods=["POST"])
@require_auth()
def route_download_branch(content_id, branch_id):
    if not download_allowed(g.auth_user, content_id):
        return jsonify({"error": "rate_limited"}), 429
    result = record_download(content_id, branch_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
