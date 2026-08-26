import pytest
import os
from unittest.mock import patch, MagicMock
import website_ron_g as rg
import website_builder_buddy as bb
from app_server import app

RG_DATA = os.path.join(os.path.dirname(rg.__file__), "ron_g_data.json")
BB_DATA = os.path.join(os.path.dirname(bb.__file__), "blueprint_data.json")


def _mock_message(text="Use epoxy tape on the back side."):
    msg = MagicMock()
    content = MagicMock()
    content.text = text
    msg.content = [content]
    return msg


@pytest.fixture(autouse=True)
def clean_data():
    for f in (RG_DATA, BB_DATA):
        if os.path.exists(f):
            os.remove(f)
    yield
    for f in (RG_DATA, BB_DATA):
        if os.path.exists(f):
            os.remove(f)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def mock_claude():
    with patch("website_ron_g.anthropic.Anthropic") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        instance.messages.create.return_value = _mock_message()
        yield instance


# --- ask_ron_g ---

def test_ask_basic(mock_claude):
    result = rg.ask_ron_g("How do I fill epoxy bug holes?")
    assert "answer" in result
    assert result["answer"] == "Use epoxy tape on the back side."
    assert result["question"] == "How do I fill epoxy bug holes?"


def test_ask_empty_question(mock_claude):
    result = rg.ask_ron_g("")
    assert "error" in result


def test_ask_whitespace_question(mock_claude):
    result = rg.ask_ron_g("   ")
    assert "error" in result


def test_ask_returns_session_id(mock_claude):
    result = rg.ask_ron_g("What grit sandpaper for walnut?")
    assert "session_id" in result


def test_ask_logs_to_file(mock_claude):
    rg.ask_ron_g("How tight should my mortise fit?")
    log = rg.get_session_log()
    assert log["count"] == 1
    assert log["sessions"][0]["question"] == "How tight should my mortise fit?"


def test_ask_multiple_logs(mock_claude):
    rg.ask_ron_g("Question one")
    rg.ask_ron_g("Question two")
    log = rg.get_session_log()
    assert log["count"] == 2


def test_ask_with_build_id(mock_claude):
    b = bb.add_build(name="Test Stool")["build"]
    result = rg.ask_ron_g("What should I cut first?", build_id=b["id"])
    assert result["build_id"] == b["id"]
    assert "answer" in result


def test_ask_with_build_id_injects_context(mock_claude):
    b = bb.add_build(name="Walnut Side Table", description="Low side table")["build"]
    rg.ask_ron_g("How many board feet do I need?", build_id=b["id"])
    call_args = mock_claude.messages.create.call_args
    content = call_args.kwargs["messages"][0]["content"]
    assert "Walnut Side Table" in content


def test_ask_with_invalid_build_id_still_answers(mock_claude):
    result = rg.ask_ron_g("What finish for pine?", build_id="nonexistent-build")
    assert "answer" in result


def test_ask_calls_claude_with_system_prompt(mock_claude):
    rg.ask_ron_g("Best bit for drilling oak?")
    call_args = mock_claude.messages.create.call_args
    assert call_args.kwargs["system"] == rg.RON_G_SYSTEM
    assert call_args.kwargs["model"] == "claude-opus-5"


# --- get_session_log ---

def test_session_log_empty():
    log = rg.get_session_log()
    assert log["count"] == 0


def test_session_log_limit(mock_claude):
    for i in range(5):
        rg.ask_ron_g(f"Question {i}")
    log = rg.get_session_log(limit=3)
    assert log["count"] == 3


def test_session_log_returns_latest(mock_claude):
    for i in range(5):
        rg.ask_ron_g(f"Question {i}")
    log = rg.get_session_log(limit=2)
    assert log["sessions"][0]["question"] == "Question 3"
    assert log["sessions"][1]["question"] == "Question 4"


# --- HTTP routes ---

def test_http_ask(client, mock_claude):
    r = client.post("/ron-g/ask", json={"question": "What's the best finish for pine?"})
    assert r.status_code == 200
    data = r.get_json()
    assert "answer" in data
    assert "session_id" in data


def test_http_ask_empty_question(client, mock_claude):
    r = client.post("/ron-g/ask", json={"question": ""})
    assert r.status_code == 400


def test_http_ask_no_body(client, mock_claude):
    r = client.post("/ron-g/ask", json={})
    assert r.status_code == 400


def test_http_log(client, mock_claude):
    client.post("/ron-g/ask", json={"question": "How do I sharpen a chisel?"})
    r = client.get("/ron-g/log")
    assert r.status_code == 200
    assert r.get_json()["count"] == 1


def test_http_log_limit(client, mock_claude):
    for i in range(5):
        client.post("/ron-g/ask", json={"question": f"Q{i}"})
    r = client.get("/ron-g/log?limit=2")
    assert r.get_json()["count"] == 2
