import types
import pytest
import field_guard as fg

DS_ID = "test-ds-id"
SCHEMA = {
    "Next Action": "text", "Why It Matters": "text", "Project": "text",
    "Question": "text", "Pin": "title",
    "Severity": {"Green", "Yellow", "Red"},
    "Status": {"Open", "Resolved"},
    "Type": {"Measurement Needed", "Tool Unknown", "Material Unknown",
             "Hardware Unknown", "Safety Concern", "Design Decision",
             "Future Upgrade", "Pricing/Business Note", "App Feature", "Bug",
             "Research Needed", "User Preference"},
}


class _Resp:
    def raise_for_status(self):
        pass


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def fake_post(url, headers, json, timeout):
        calls.update(url=url, headers=headers, body=json)
        return _Resp()

    monkeypatch.setattr(fg, "requests", types.SimpleNamespace(
        post=fake_post, RequestException=Exception))
    monkeypatch.setattr(fg, "NOTION_TOKEN", "test-token")
    monkeypatch.setattr(fg, "PINNED_ITEMS_DATA_SOURCE_ID", DS_ID)
    return calls


def test_filter_splits_allowed_and_rejected():
    r = fg.filter_allowed_fields({"name": "x", "is_admin": True}, {"name"})
    assert r.applied == {"name": "x"}
    assert r.rejected == {"is_admin": True}


def test_filter_non_dict_is_empty():
    r = fg.filter_allowed_fields(None, {"name"})
    assert r.applied == {} and r.rejected == {}


def test_no_rejected_fields_sends_nothing(captured):
    fg.log_unknown_fields("update_build", "rec", "user", {})
    assert captured == {}


def test_missing_token_warns_and_does_not_post(monkeypatch, captured):
    monkeypatch.setattr(fg, "NOTION_TOKEN", None)
    fg.log_unknown_fields("update_build", "rec", "user", {"x": 1})
    assert captured == {}


def test_payload_matches_real_pinned_items_schema(captured):
    fg.log_unknown_fields("update_build", "rec-1", "user-1", {"is_admin": True})
    body = captured["body"]
    assert body["parent"] == {"type": "data_source_id", "data_source_id": DS_ID}
    assert captured["headers"]["Notion-Version"] == "2025-09-03"
    for name, val in body["properties"].items():
        assert name in SCHEMA, f"unknown property {name}"
        kind = SCHEMA[name]
        if kind == "title":
            assert "title" in val
        elif kind == "text":
            assert "rich_text" in val
        else:
            assert val["select"]["name"] in kind


def test_notion_outage_does_not_raise(monkeypatch):
    class Boom(Exception):
        pass

    def bad_post(*a, **k):
        raise Boom("down")

    monkeypatch.setattr(fg, "requests", types.SimpleNamespace(
        post=bad_post, RequestException=Boom))
    monkeypatch.setattr(fg, "NOTION_TOKEN", "t")
    fg.log_unknown_fields("update_build", "rec", "user", {"x": 1})


def test_missing_data_source_id_warns_and_does_not_post(monkeypatch, captured):
    monkeypatch.setattr(fg, "PINNED_ITEMS_DATA_SOURCE_ID", "")
    fg.log_unknown_fields("update_build", "rec", "user", {"x": 1})
    assert captured == {}
