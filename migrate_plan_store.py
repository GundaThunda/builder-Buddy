"""
One-time migration: posted plans -> plan store.

Only builds that were posted (social published_builds) are migrated. Their
owner is the posting account, the only attribution the data has. Blueprint
builds that were never posted have no owner, so they are left in place.

Usage:
  python migrate_plan_store.py           dry run: reports what would change, writes nothing
  python migrate_plan_store.py --apply   backs up both data files, then migrates
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

import website_plan_store as store

HERE = os.path.dirname(os.path.abspath(__file__))
BLUEPRINT_FILE = os.path.join(HERE, "blueprint_data.json")
SOCIAL_FILE = os.path.join(HERE, "social_data.json")
BACKUP_DIR = os.path.join(HERE, "plan_backups")


def _read(path: str, default: dict) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def plan_body_from_build(build: dict) -> dict:
    steps = sorted(build.get("steps", []), key=lambda s: s.get("order", 0))
    return {
        "steps": [{k: s.get(k) for k in store.STEP_FIELDS} for s in steps],
        "materials": [{k: m.get(k) for k in store.MATERIAL_FIELDS}
                      for m in build.get("materials", [])],
        "dimensions": build.get("dimensions") or {},
    }


def plan_migration(social: dict, blueprint: dict, apply: bool) -> dict:
    """Dry run computes everything in memory and writes nothing."""
    builds = blueprint.get("builds", {})
    report = {"candidates": 0, "migrated_new": 0, "migrated_reposts": 0,
              "skipped_missing_build": [], "skipped_invalid": [], "dry_run": not apply}
    seen_hashes = set(store._load_index()["by_hash"].keys()) if apply else set()
    for build_id, pub in social.get("published_builds", {}).items():
        report["candidates"] += 1
        build = builds.get(build_id)
        if build is None:
            report["skipped_missing_build"].append(build_id)
            continue
        body = plan_body_from_build(build)
        err = store._validate_body(body)
        if err:
            report["skipped_invalid"].append({"build_id": build_id, "reason": err})
            continue
        if apply:
            result = store.submit_plan(pub["owner"], body)
            if result["status"] == "new":
                report["migrated_new"] += 1
            else:
                report["migrated_reposts"] += 1
        else:
            h = store.content_hash(body)
            if h in seen_hashes:
                report["migrated_reposts"] += 1
            else:
                seen_hashes.add(h)
                report["migrated_new"] += 1
    return report


def backup(paths: list, backup_dir: str) -> list:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.makedirs(backup_dir, exist_ok=True)
    copies = []
    for path in paths:
        if os.path.exists(path):
            dest = os.path.join(backup_dir, f"{stamp}_{os.path.basename(path)}")
            shutil.copy2(path, dest)
            copies.append(dest)
    return copies


def main(argv: list) -> int:
    apply = "--apply" in argv
    social = _read(SOCIAL_FILE, {})
    blueprint = _read(BLUEPRINT_FILE, {"builds": {}})
    if apply:
        copies = backup([BLUEPRINT_FILE, SOCIAL_FILE], BACKUP_DIR)
        print("backups:", copies or "none (no source files present)")
    report = plan_migration(social, blueprint, apply)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
