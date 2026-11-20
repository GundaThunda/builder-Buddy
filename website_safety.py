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


# Generic warnings. They cite no standard and set no thresholds, so they fire without a
# sourced rule. Their wording still needs review.
#   scope "plan": at most one warning per plan, on the first matching step.
#   scope "step": one warning on every matching step.
POWER_PROCESS_TYPES = ["milling", "ripping", "crosscutting", "routing", "turning",
                       "drilling", "sanding", "carving"]
POWER_KEYWORDS = ["table saw", "tablesaw", "router", "planer", "jointer", "bandsaw",
                  "band saw", "miter saw", "chop saw", "drill", "sander", "lathe",
                  "rip ", "crosscut", "circular saw", "jigsaw"]
FINISH_KEYWORDS = ["lacquer", "varnish", "polyurethane", "stain", "paint", "solvent",
                   "epoxy", "spray", "voc"]
GENERIC_SOURCE = "General shop safety practice. No specific standard cited. Wording pending review."

GENERIC_RULES = [
    {
        "id": "general_power_tool", "status": "approved", "scope": "plan",
        "source": GENERIC_SOURCE, "category": "power_tool", "severity": "warning",
        "trigger": {"process_types": POWER_PROCESS_TYPES, "keywords": POWER_KEYWORDS},
        "message": "This plan uses power tools. Confirm guards and safety devices are in place "
                   "and working, and follow each tool manufacturer's instructions.",
    },
    {
        "id": "hr_ripping", "status": "approved", "scope": "step",
        "source": GENERIC_SOURCE, "category": "power_tool", "severity": "warning",
        "trigger": {"process_types": ["ripping"], "keywords": ["rip ", "table saw", "tablesaw"]},
        "message": "High-risk: ripping on a table saw can kick the workpiece back toward you. "
                   "Use the riving knife and fence, and keep hands out of the blade path.",
    },
    {
        "id": "hr_routing", "status": "approved", "scope": "step",
        "source": GENERIC_SOURCE, "category": "power_tool", "severity": "warning",
        "trigger": {"process_types": ["routing"], "keywords": ["router"]},
        "message": "High-risk: a router spins fast and can grab or kick a loose workpiece. "
                   "Clamp or secure the work and take shallow passes.",
    },
    {
        "id": "hr_turning", "status": "approved", "scope": "step",
        "source": GENERIC_SOURCE, "category": "power_tool", "severity": "warning",
        "trigger": {"process_types": ["turning"], "keywords": ["lathe"]},
        "message": "High-risk: an unbalanced or loose workpiece on a lathe can be thrown. "
                   "Check mounting and balance before starting, and keep the tool rest and guard in place.",
    },
    {
        "id": "hr_jointer_planer", "status": "approved", "scope": "step",
        "source": GENERIC_SOURCE, "category": "power_tool", "severity": "warning",
        "trigger": {"process_types": [], "keywords": ["jointer", "planer"]},
        "message": "High-risk: jointers and planers can kick a board back or pull fingers toward "
                   "the cutterhead. Use push blocks and keep hands clear of the cutters.",
    },
    {
        "id": "mask_finish_voc", "status": "approved", "scope": "step",
        "source": GENERIC_SOURCE, "category": "finishing", "severity": "warning",
        "trigger": {"process_types": ["finishing", "painting", "staining"],
                    "keywords": FINISH_KEYWORDS},
        "message": "Wear a respirator rated for organic vapors (VOCs) before each application. "
                   "Ventilate the area and keep solvents away from ignition sources.",
    },
    {
        "id": "mask_particulate", "status": "approved", "scope": "step",
        "source": GENERIC_SOURCE, "category": "dust", "severity": "warning",
        "trigger": {"process_types": ["sanding", "milling"],
                    "keywords": ["sanding", "sander", "mdf", "milling"]},
        "message": "Wear a particulate respirator or dust mask. Sanding and milling release fine "
                   "dust that can reach deep in the lungs.",
    },
]


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
    user_rules = active_rules(load_rules() if rules is None else rules)
    generic = active_rules(GENERIC_RULES)
    found = []
    seen_plan_scope = set()
    for i, step in enumerate(body.get("steps", [])):
        text = _step_text(step)
        for rule in user_rules + generic:
            if not _matches(rule, text, step.get("process_type")):
                continue
            if rule.get("scope") == "plan":
                if rule["id"] in seen_plan_scope:
                    continue
                seen_plan_scope.add(rule["id"])
            found.append({"rule_id": rule["id"], "severity": rule["severity"],
                          "message": rule["message"], "where": f"step:{i + 1}"})
    # Generic rules are step-level only. Material names must not trigger them.
    for m in body.get("materials", []):
        text = _material_text(m)
        for rule in user_rules:
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
