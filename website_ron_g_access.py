"""
Ron G access: subscribers are unlimited; everyone else gets FREE_DAILY_LIMIT asks per UTC day.

Subscription is to the Ron G plugin. Until a payment provider is connected, an admin sets the
flag by hand (website_ron_g.route_set_subscription). Counts are persisted, so they survive
restarts. Only accepted asks count: a failed ask does not use up an allowance.
"""
import json
import os
from datetime import datetime, timezone

FREE_DAILY_LIMIT = 10
ACCESS_FILE = os.path.join(os.path.dirname(__file__), "ron_g_access.json")


def _load() -> dict:
    if os.path.exists(ACCESS_FILE):
        with open(ACCESS_FILE, "r") as f:
            return json.load(f)
    return {"subscribed": {}, "daily": {}}


def _save(data: dict) -> None:
    with open(ACCESS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_subscribed(handle: str) -> bool:
    return bool(_load()["subscribed"].get(handle, False))


def set_subscribed(handle: str, subscribed: bool) -> None:
    data = _load()
    data["subscribed"][handle] = bool(subscribed)
    _save(data)


def remaining_today(handle: str) -> int | None:
    """None means unlimited (subscriber)."""
    if is_subscribed(handle):
        return None
    entry = _load()["daily"].get(handle, {})
    used = entry.get("count", 0) if entry.get("date") == _today() else 0
    return max(FREE_DAILY_LIMIT - used, 0)


def can_ask(handle: str) -> bool:
    left = remaining_today(handle)
    return left is None or left > 0


def record_ask(handle: str) -> None:
    if is_subscribed(handle):
        return
    data = _load()
    today = _today()
    entry = data["daily"].get(handle, {})
    count = entry.get("count", 0) if entry.get("date") == today else 0
    data["daily"][handle] = {"date": today, "count": count + 1}
    _save(data)
