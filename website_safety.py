"""
Safety checks for plans and plan changes.

Severities:
  caution  shown to the uploader; no acknowledgement required
  warning  uploader must acknowledge the rule ID before the plan is saved
  block    plan is refused until the step or material is changed

Rules fire only when status is "approved" and a source is cited. Drafts are
ignored, so nothing is enforced on a guess.

Rules are matched against plan text (step titles, notes, process types,
material names, grades and notes). Rule messages are short and stated once.
They are not written to lecture experienced users.
"""

import json
import os

SEVERITIES = ("caution", "warning", "block")
RULES_PATH = os.path.join(os.path.dirname(__file__), "safety_rules.json")

# Tests can set this to inject rules without touching the file.
RULES_OVERRIDE = None


def load_rules() -> list:
    if RULES_OVERRIDE is not None:
        return RULES_OVERRIDE
    if not os.path.exists(RULES_PATH):
        return []
    with open(RULES_PATH) as f:
        return json.load(f)["rules"]


def active_rules(rules: list) -> list:
    return [r for r in rules
            if r.get("status") == "approved" and str(r.get("source", "")).strip()
            and r.get("severity") in SEVERITIES]


def _step_text(step: dict) -> str:
    return " ".join(str(step.get(k, "")) for k in ("title", "notes", "process_type")).lower()


def _material_text(m: dict) -> str:
    return " ".join(str(m.get(k, "")) for k in ("name", "species_or_grade", "notes")).lower()


def _matches(rule: dict, text: str, process_type: str | None) -> bool:
    trigger = rule.get("trigger", {})
    if process_type and process_type in trigger.get("process_types", []):
        return True
    return any(k.lower() in text for k in trigger.get("keywords", []))


def check_plan(body: dict, rules: list | None = None) -> list:
    rules = active_rules(load_rules() if rules is None else rules)
    found = []
    for i, step in enumerate(body.get("steps", [])):
        text = _step_text(step)
        for rule in rules:
            if _matches(rule, text, step.get("process_type")):
                found.append({"rule_id": rule["id"], "severity": rule["severity"],
                              "message": rule["message"], "where": f"step:{i + 1}"})
    for m in body.get("materials", []):
        text = _material_text(m)
        for rule in rules:
            if _matches(rule, text, None):
                found.append({"rule_id": rule["id"], "severity": rule["severity"],
                              "message": rule["message"], "where": f"material:{m.get('name')}"})
    return found


def gate(warnings: list, acknowledged) -> dict | None:
    """Return None if the plan may be saved, otherwise an error dict."""
    if any(w["severity"] == "block" for w in warnings):
        return {"error": "safety_block", "warnings": warnings}
    ack = set(acknowledged or [])
    needed = {w["rule_id"] for w in warnings if w["severity"] == "warning"}
    missing = sorted(needed - ack)
    if missing:
        return {"error": "acknowledgement_required", "required": missing, "warnings": warnings}
    return None


def compare_safety(incomplete_body: dict, final_body: dict, rules: list | None = None) -> dict:
    """Hazards that appear in the final build but not in the incomplete upload."""
    before = {w["rule_id"] for w in check_plan(incomplete_body, rules)}
    after = check_plan(final_body, rules)
    new_in_final = [w for w in after if w["rule_id"] not in before]
    return {"new_in_final": new_in_final,
            "carried_over": sorted(before & {w["rule_id"] for w in after})}
