import pytest

import website_plan_store as store
import website_safety as safety
from app_server import app

RULE_WARN = {"id": "r_warn", "status": "approved", "severity": "warning", "source": "src",
             "trigger": {"process_types": ["finishing"], "keywords": ["lacquer"]},
             "message": "Use a respirator."}
RULE_BLOCK = {"id": "r_block", "status": "approved", "severity": "block", "source": "src",
              "trigger": {"process_types": [], "keywords": ["unguarded"]},
              "message": "Guard the blade."}
RULE_DRAFT = {"id": "r_draft", "status": "draft", "severity": "block", "source": "",
              "trigger": {"process_types": [], "keywords": ["anything"]}, "message": "x"}


GENERIC_ORIGINAL = list(safety.GENERIC_RULES)


@pytest.fixture(autouse=True)
def rules(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "STORE_DIR", str(tmp_path / "plan_store"))
    monkeypatch.setattr(safety, "RULES_OVERRIDE", [RULE_WARN, RULE_BLOCK, RULE_DRAFT])
    monkeypatch.setattr(safety, "GENERIC_RULES", [])
    yield


@pytest.fixture
def generic_on(monkeypatch):
    monkeypatch.setattr(safety, "GENERIC_RULES", GENERIC_ORIGINAL)


def _body(*steps, materials=None):
    return {"steps": list(steps), "materials": materials or [], "dimensions": {}}


def test_draft_rules_never_fire():
    warnings = safety.check_plan(_body({"title": "anything"}), [RULE_DRAFT])
    assert warnings == []


def test_approved_rule_needs_source():
    no_source = dict(RULE_WARN, source="")
    assert safety.active_rules([no_source]) == []


def test_warning_matched_by_process_and_keyword():
    w = safety.check_plan(_body({"title": "Apply lacquer", "process_type": "other"}))
    assert [x["rule_id"] for x in w] == ["r_warn"]
    w2 = safety.check_plan(_body({"title": "Clean up", "process_type": "finishing"}))
    assert "r_warn" in [x["rule_id"] for x in w2]


def test_warning_blocks_save_until_acknowledged():
    warnings = safety.check_plan(_body({"title": "Apply lacquer"}))
    assert safety.gate(warnings, [])["error"] == "acknowledgement_required"
    assert safety.gate(warnings, ["r_warn"]) is None


def test_block_cannot_be_acknowledged():
    warnings = safety.check_plan(_body({"title": "Run unguarded saw"}))
    assert safety.gate(warnings, ["r_block"])["error"] == "safety_block"


def test_submit_refused_then_accepted_with_acknowledgement():
    body = _body({"title": "Apply lacquer"})
    assert store.submit_plan("alice", body)["error"] == "acknowledgement_required"
    assert store.submit_plan("alice", body, acknowledged=["r_warn"])["status"] == "new"


def test_submit_refused_on_block():
    body = _body({"title": "Run unguarded saw"})
    assert store.submit_plan("alice", body, acknowledged=["r_block"])["error"] == "safety_block"


def test_branch_adding_hazard_needs_acknowledgement():
    base = _body({"title": "Sand edges"})
    cid = store.submit_plan("alice", base)["content_id"]
    tweak = _body({"title": "Sand edges"}, {"title": "Apply lacquer"})
    assert store.add_branch("bob", cid, tweak)["error"] == "acknowledgement_required"
    assert "branch_id" in store.add_branch("bob", cid, tweak, acknowledged=["r_warn"])


def test_compare_flags_hazard_only_in_final_build():
    incomplete = _body({"title": "Rough cut"})
    final = _body({"title": "Rough cut"}, {"title": "Apply lacquer"})
    result = safety.compare_safety(incomplete, final, [RULE_WARN])
    assert [w["rule_id"] for w in result["new_in_final"]] == ["r_warn"]
    assert result["carried_over"] == []


def test_compare_reports_carried_over_hazard():
    incomplete = _body({"title": "Apply lacquer"})
    final = _body({"title": "Apply lacquer"}, {"title": "Sand"})
    result = safety.compare_safety(incomplete, final, [RULE_WARN])
    assert result["new_in_final"] == []
    assert result["carried_over"] == ["r_warn"]


def test_route_returns_422_on_block_and_409_on_missing_ack():
    from website_auth import auth_routes  # noqa: F401  (ensures blueprints load)
    app.config["TESTING"] = True
    import website_auth as auth
    import website_social_structure as ss
    ss.get_or_create_user("alice")
    auth.set_password("alice", "correct horse battery")
    with app.test_client() as c:
        tok = c.post("/auth/login", json={"user_handle": "alice",
                                          "password": "correct horse battery"}).get_json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        blocked = c.post("/plans", headers=h, json={
            "steps": [{"title": "Run unguarded saw"}], "acknowledged": ["r_block"]})
        assert blocked.status_code == 422
        needs_ack = c.post("/plans", headers=h, json={"steps": [{"title": "Apply lacquer"}]})
        assert needs_ack.status_code == 409
        assert needs_ack.get_json()["required"] == ["r_warn"]
        ok = c.post("/plans", headers=h, json={
            "steps": [{"title": "Apply lacquer"}], "acknowledged": ["r_warn"]})
        assert ok.status_code == 201


# --- generic warnings (no sourced rule needed) ---

def test_power_tool_step_warns_without_any_sourced_rule(generic_on):
    w = safety.check_plan(_body({"title": "Rip the boards on the table saw"}), [])
    ids = [x["rule_id"] for x in w]
    assert "general_power_tool" in ids
    assert "hr_ripping" in ids
    assert safety.gate(w, [])["error"] == "acknowledgement_required"


def test_power_tool_process_type_warns(generic_on):
    w = safety.check_plan(_body({"title": "Smooth edges", "process_type": "sanding"}), [])
    assert "general_power_tool" in [x["rule_id"] for x in w]


def test_finishing_step_warns_generically(generic_on):
    w = safety.check_plan(_body({"title": "Wipe on finish", "process_type": "finishing"}), [])
    assert "mask_finish_voc" in [x["rule_id"] for x in w]


def test_plain_assembly_step_has_no_generic_warning(generic_on):
    w = safety.check_plan(_body({"title": "Clamp the frame", "process_type": "assembly"}), [])
    assert w == []


def test_power_tool_warning_blocks_save_until_acknowledged(generic_on):
    body = _body({"title": "Rip the boards on the table saw"})
    assert store.submit_plan("alice", body)["error"] == "acknowledgement_required"
    partial = store.submit_plan("alice", body, acknowledged=["general_power_tool"])
    assert partial["error"] == "acknowledgement_required"
    assert store.submit_plan("alice", body,
                             acknowledged=["general_power_tool", "hr_ripping"])["status"] == "new"


def test_high_risk_step_has_explained_warning(generic_on):
    body = _body({"title": "Rip the stock", "process_type": "ripping"})
    hits = [w for w in safety.check_plan(body, []) if w["rule_id"] == "hr_ripping"]
    assert len(hits) == 1
    assert hits[0]["where"] == "step:1"
    assert hits[0]["message"].startswith("High-risk:")
    assert "kick" in hits[0]["message"]


def test_high_risk_warning_repeats_per_high_risk_step(generic_on):
    body = _body({"title": "Rip the stock", "process_type": "ripping"},
                 {"title": "Rip the second board on the table saw", "process_type": "ripping"})
    hits = [w for w in safety.check_plan(body, []) if w["rule_id"] == "hr_ripping"]
    assert len(hits) == 2


def test_non_high_risk_power_step_gets_no_repeat(generic_on):
    body = _body({"title": "Drill pilot holes", "process_type": "drilling"})
    ids = [w["rule_id"] for w in safety.check_plan(body, [])]
    assert not [i for i in ids if i.startswith("hr_")]


def test_respirator_reminder_before_each_finish_application(generic_on):
    body = _body({"title": "Apply first coat of lacquer", "process_type": "finishing"},
                 {"title": "Sand between coats"},
                 {"title": "Apply second coat of lacquer", "process_type": "finishing"})
    hits = [w for w in safety.check_plan(body, []) if w["rule_id"] == "mask_finish_voc"]
    assert [h["where"] for h in hits] == ["step:1", "step:3"]


def test_chemical_step_with_finishing_type_gets_respirator_reminder(generic_on):
    # "mineral spirits" is not in FINISH_KEYWORDS yet (open question for the user),
    # so this test sets the process type explicitly.
    body = _body({"title": "Wipe on mineral spirits to clean the top", "process_type": "finishing"})
    ids = [w["rule_id"] for w in safety.check_plan(body, [])]
    assert "mask_finish_voc" in ids


# --- refined generic behaviour: once per plan for power tools, per-step for high-risk and masks ---

def _ids(warnings):
    return [w["rule_id"] for w in warnings]


def test_power_tools_warn_once_per_plan(generic_on):
    body = _body({"title": "Rough cut", "process_type": "crosscutting"},
                 {"title": "Drill pilot holes", "process_type": "drilling"},
                 {"title": "Sand edges", "process_type": "sanding"})
    ids = _ids(safety.check_plan(body, []))
    assert ids.count("general_power_tool") == 1


def test_high_risk_step_gets_explained_warning(generic_on):
    w = safety.check_plan(_body({"title": "Rip stock on the table saw", "process_type": "ripping"}), [])
    hr = [x for x in w if x["rule_id"] == "hr_ripping"]
    assert len(hr) == 1
    assert "kick" in hr[0]["message"]


def test_non_high_risk_power_step_has_no_hr_warning(generic_on):
    w = safety.check_plan(_body({"title": "Drill pilot holes", "process_type": "drilling"}), [])
    assert not [x for x in w if x["rule_id"].startswith("hr_")]


def test_finish_mask_reminder_on_every_application_step(generic_on):
    body = _body({"title": "Apply first coat of lacquer", "process_type": "finishing"},
                 {"title": "Sand between coats", "process_type": "sanding"},
                 {"title": "Apply second coat of lacquer", "process_type": "finishing"})
    ids = _ids(safety.check_plan(body, []))
    assert ids.count("mask_finish_voc") == 2


def test_particulate_reminder_on_each_sanding_or_milling_step(generic_on):
    body = _body({"title": "Sand the top", "process_type": "sanding"},
                 {"title": "Mill the stock", "process_type": "milling"})
    ids = _ids(safety.check_plan(body, []))
    assert ids.count("mask_particulate") == 2


def test_material_names_do_not_trigger_generic(generic_on):
    body = {"steps": [{"title": "Assemble", "process_type": "assembly"}],
            "materials": [{"name": "Router bits", "qty": 1, "unit": "pc"}]}
    assert _ids(safety.check_plan(body, [])) == []
