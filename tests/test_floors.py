import website_floors as wf
import website_match as wm


def test_every_floor_has_an_anchor_and_is_on_the_scale():
    for t, (floor, anchor) in wf.FLOORS.items():
        assert 1 <= floor <= 100, t
        assert anchor.strip(), t


def test_floors_by_type_matches_table():
    mapping = wf.floors_by_type()
    assert mapping["hardwood_visible"] == 70
    assert set(mapping) == set(wf.FLOORS)


def test_epoxy_has_no_floor_and_fails_closed():
    mats = [{"name": "Epoxy", "qty": 1, "cost_per_unit": 10.0}]
    scores = {"Epoxy": {"score": 90, "type": "epoxy"}}
    result = wm.compare(mats, mats, scores, scores, wf.floors_by_type())
    assert result["match"] is False
    assert "floor_not_set:epoxy" in result["reasons"]


def test_score_below_floor_blocks_with_real_table():
    mats = [{"name": "Oak", "qty": 1, "cost_per_unit": 10.0}]
    low = {"Oak": {"score": 65, "type": "hardwood_visible"}}
    result = wm.compare(mats, mats, low, low, wf.floors_by_type())
    assert "below_floor:Oak" in result["reasons"]
