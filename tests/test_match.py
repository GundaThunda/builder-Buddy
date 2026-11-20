import website_match as wm


def _mat(name, qty=1, cost=10.0):
    return {"name": name, "qty": qty, "cost_per_unit": cost}


def _s(score, mtype="hardwood"):
    return {"score": score, "type": mtype}


FLOORS = {"hardwood": 60, "plywood": 50}


def test_identical_builds_match():
    mats = [_mat("Maple 4/4", 2, 10.0)]
    scores = {"Maple 4/4": _s(80)}
    assert wm.compare(mats, mats, scores, scores, FLOORS) == {"match": True, "reasons": []}


def test_cost_within_5_percent_matches():
    base = [_mat("Maple 4/4", 100, 10.0)]          # 1000.00
    branch = [_mat("Maple 4/4", 100, 10.49)]       # 1049.00, about 4.6% apart
    scores = {"Maple 4/4": _s(80)}
    assert wm.compare(base, branch, scores, scores, FLOORS)["match"] is True


def test_cost_outside_5_percent_blocks():
    base = [_mat("Maple 4/4", 100, 10.0)]
    branch = [_mat("Maple 4/4", 100, 11.0)]        # about 9.1% apart
    scores = {"Maple 4/4": _s(80)}
    assert "cost_outside_tolerance" in wm.compare(base, branch, scores, scores, FLOORS)["reasons"]


def test_quality_within_5_points_matches_and_beyond_blocks():
    mats = [_mat("Maple 4/4")]
    assert wm.compare(mats, mats, {"Maple 4/4": _s(80)}, {"Maple 4/4": _s(85)}, FLOORS)["match"] is True
    result = wm.compare(mats, mats, {"Maple 4/4": _s(80)}, {"Maple 4/4": _s(86)}, FLOORS)
    assert "quality_outside_tolerance:Maple 4/4" in result["reasons"]


def test_each_material_judged_alone_strong_cannot_offset_weak():
    mats = [_mat("Maple 4/4"), _mat("Pine 1x12")]
    base = {"Maple 4/4": _s(95), "Pine 1x12": _s(62, "plywood")}
    branch = {"Maple 4/4": _s(95), "Pine 1x12": _s(70, "plywood")}
    result = wm.compare(mats, mats, base, branch, FLOORS)
    assert "quality_outside_tolerance:Pine 1x12" in result["reasons"]


def test_below_floor_blocks():
    mats = [_mat("Maple 4/4")]
    low = {"Maple 4/4": _s(55)}
    result = wm.compare(mats, mats, low, low, FLOORS)
    assert "below_floor:Maple 4/4" in result["reasons"]


def test_no_floor_set_fails_closed():
    mats = [_mat("Maple 4/4")]
    scores = {"Maple 4/4": _s(90, "exotic")}
    result = wm.compare(mats, mats, scores, scores, FLOORS)
    assert result["match"] is False
    assert "floor_not_set:exotic" in result["reasons"]


def test_missing_score_is_unverified():
    mats = [_mat("Maple 4/4")]
    result = wm.compare(mats, mats, {}, {"Maple 4/4": _s(80)}, FLOORS)
    assert result["match"] is False
    assert "unverified:Maple 4/4" in result["reasons"]


def test_material_set_difference_blocks():
    base = [_mat("Maple 4/4")]
    branch = [_mat("Maple 4/4"), _mat("Screws", 1, 0.0)]
    scores = {"Maple 4/4": _s(80)}
    result = wm.compare(base, branch, scores, scores, FLOORS)
    assert "material_set_differs" in result["reasons"]


def test_material_cost_helper():
    assert wm.material_cost([_mat("A", 2, 3.5), _mat("B", 1, 1.0)]) == 8.0
