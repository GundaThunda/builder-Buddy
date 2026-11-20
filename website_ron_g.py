import uuid
import json
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
import anthropic
from website_gate import require_auth
from website_silhouette import generate_presentation
import website_ron_g_access as access
import website_billing as billing

ron_g_routes = Blueprint("ron_g", __name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "ron_g_data.json")

RON_G_SYSTEM = (
    "You are Ron G — a stoic, calm, direct woodworking expert with dry humor and a safety-first "
    "mindset. You never condescend toward beginners. Your core philosophy: everyone starts "
    "somewhere, fundamentals matter forever, and the shop is supposed to be fun. Tone scales "
    "with timing and consequence — never dramatic, always honest.\n\n"
    "When answering questions:\n"
    "- Be direct and practical\n"
    "- Lead with the fix, not a lecture\n"
    "- Mention safety when it matters — once, clearly, without alarm\n"
    "- If you don't know, say so — never guess on dimensions or safety\n"
    "- Keep it tight. A good answer is as short as it needs to be."
)


def _load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"sessions": []}


def _save(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ask_ron_g(question: str, build_id: str = "") -> dict:
    question = question.strip()
    if not question:
        return {"error": "question is required"}

    build_context = ""
    if build_id:
        presentation = generate_presentation(build_id)
        if "error" not in presentation:
            p = presentation["presentation"]
            ov = p.get("overview", {})
            build_context = (
                f"Current build: {ov.get('name', 'Unknown')}\n"
                f"Description: {ov.get('description', '')}\n"
                f"Steps: {ov.get('total_steps', 0)} total, "
                f"{ov.get('completed_steps', 0)} completed\n"
                f"Progress: {ov.get('progress_pct', 0)}%"
            )

    content = question
    if build_context:
        content = f"Build context:\n{build_context}\n\nQuestion: {question}"

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        system=RON_G_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    answer = message.content[0].text

    entry = {
        "id": str(uuid.uuid4()),
        "question": question,
        "answer": answer,
        "build_id": build_id,
        "asked_at": _now(),
    }
    data = _load()
    data["sessions"].append(entry)
    _save(data)

    return {
        "question": question,
        "answer": answer,
        "build_id": build_id,
        "session_id": entry["id"],
    }


def get_session_log(limit: int = 20) -> dict:
    data = _load()
    sessions = data["sessions"][-limit:]
    return {"sessions": sessions, "count": len(sessions)}


# --- Flask routes ---

@ron_g_routes.route("/ask", methods=["POST"])
@require_auth()
def route_ask():
    if not access.can_ask(g.auth_user):
        return jsonify({"error": "daily_limit_reached", "limit": access.FREE_DAILY_LIMIT}), 429
    body = request.get_json(silent=True) or {}
    result = ask_ron_g(
        question=body.get("question", ""),
        build_id=body.get("build_id", ""),
    )
    if "error" in result:
        return jsonify(result), 400
    access.record_ask(g.auth_user)
    result["remaining_today"] = access.remaining_today(g.auth_user)
    return jsonify(result)


@ron_g_routes.route("/billing/checkout", methods=["POST"])
@require_auth()
def route_billing_checkout():
    try:
        return jsonify({"url": billing.create_checkout_url(g.auth_user)})
    except billing.BillingNotConfigured as e:
        return jsonify({"error": "billing_not_configured", "missing": str(e)}), 503


@ron_g_routes.route("/billing/webhook", methods=["POST"])
def route_billing_webhook():
    # No login: Stripe calls this. The signature check is the authentication.
    try:
        result = billing.handle_webhook(request.get_data(), request.headers.get("Stripe-Signature", ""))
    except billing.BillingNotConfigured as e:
        return jsonify({"error": "billing_not_configured", "missing": str(e)}), 503
    except Exception:
        return jsonify({"error": "invalid_signature"}), 400
    return jsonify(result)


@ron_g_routes.route("/subscriptions/<handle>", methods=["POST"])
@require_auth(admin_only=True)
def route_set_subscription(handle):
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("subscribed"), bool):
        return jsonify({"error": "subscribed must be true or false"}), 400
    access.set_subscribed(handle, body["subscribed"])
    return jsonify({"handle": handle, "subscribed": body["subscribed"]})


@ron_g_routes.route("/log", methods=["GET"])
@require_auth()
def route_log():
    limit = int(request.args.get("limit", 20))
    return jsonify(get_session_log(limit))
