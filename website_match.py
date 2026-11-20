"""
"Not marketably different" comparator for two plan versions.

Two builds match only when ALL hold:
  1. Material cost differs by no more than COST_TOLERANCE (relative).
  2. Every material present in both builds has a quality score within
     QUALITY_TOLERANCE (relative) of the other build's score.
  3. Every compared material's score clears the floor for its material type.

Rules that are not configured fail closed:
  - A material type with no floor set -> "floor_not_set" (no match).
  - A material with no quality score -> "unverified" (no match).
  - Materials that appear in only one build -> "material_set_differs" (no match).

Floors are supplied by the caller. None are set in code, because none have
been approved yet.
"""

COST_TOLERANCE = 0.05
# Quality is compared as a relative difference (5%), same method as cost. Per-type overrides
# go here once they are set; none are set yet, so every type uses the default.
QUALITY_TOLERANCE = 0.05
QUALITY_TOLERANCE_BY_TYPE: dict = {}


def material_cost(materials: list) -> float:
    return round(sum(float(m.get("qty", 0)) * float(m.get("cost_per_unit", 0)) for m in materials), 2)


def _relative_diff(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b))


def compare(base_materials: list, branch_materials: list,
            base_scores: dict, branch_scores: dict, floors: dict) -> dict:
    """
    materials:  canonical material dicts (name, qty, cost_per_unit, ...).
    scores:     {material_name: {"score": int 1-100, "type": str}}.
    floors:     {material_type: minimum passing score}.
    Returns {"match": bool, "reasons": [...]}.
    """
    reasons = []

    base_names = {m["name"] for m in base_materials}
    branch_names = {m["name"] for m in branch_materials}
    if base_names != branch_names:
        reasons.append("material_set_differs")

    cost_diff = _relative_diff(material_cost(base_materials), material_cost(branch_materials))
    if cost_diff > COST_TOLERANCE:
        reasons.append("cost_outside_tolerance")

    for name in sorted(base_names & branch_names):
        base = base_scores.get(name)
        branch = branch_scores.get(name)
        if base is None or branch is None:
            reasons.append(f"unverified:{name}")
            continue
        tol = QUALITY_TOLERANCE_BY_TYPE.get(base["type"], QUALITY_TOLERANCE)
        if _relative_diff(base["score"], branch["score"]) > tol:
            reasons.append(f"quality_outside_tolerance:{name}")
        for side in (base, branch):
            floor = floors.get(side["type"])
            if floor is None:
                reasons.append(f"floor_not_set:{side['type']}")
            elif side["score"] < floor:
                reasons.append(f"below_floor:{name}")

    return {"match": not reasons, "reasons": reasons}
