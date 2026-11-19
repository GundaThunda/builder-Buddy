"""
field_guard.py

Fail-closed field guard for Builder Buddy update endpoints.

Problem this replaces:
    def update_build(build_id, **kwargs):
        return _apply_update(build_id, user_id=current_user.id, **kwargs)
    # crashes with "got multiple values for keyword argument 'user_id'"
    # whenever the incoming payload happens to contain a `user_id` key.

Fix, in three parts:
    1. Explicit allowlist -- only named fields can ever be applied.
       There is no **kwargs passthrough, so there is no namespace for a
       collision to happen in.
    2. Identity is passed as a separate `current_user` object, never
       merged into the same dict as request data. This is what makes
       the collision structurally impossible, not just avoided.
    3. Anything NOT on the allowlist is rejected from the update (never
       silently applied, never crashes the request) and logged as a
       pending decision -- a Pinned Items entry in Notion -- for a
       human to later approve (add to allowlist) or deny (leave as-is).

Security note:
    Approval must never happen inside the same request that triggered
    the rejection. If a client could send a field AND a flag that
    approves that field in one payload, the whole guard is pointless.
    Approval only happens out-of-band: a human reviews the Pinned Items
    entry and edits the allowlist in this file (or wherever it lives)
    as a deliberate code/config change.
"""

import os
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger("builder_buddy.field_guard")

NOTION_API_URL = "https://api.notion.com/v1/pages"
# NOTE: "data_source_id" as a page parent (used below) requires API version
# 2025-09-03 or later -- it is NOT supported on 2022-06-28. If Notion ships
# a newer version by the time you read this, check developers.notion.com
# before bumping this string.
NOTION_VERSION = "2025-09-03"

# Server-side integration token. NEVER hardcode this -- set it as an
# environment variable in your deployment config.
NOTION_TOKEN = os.environ.get("NOTION_API_TOKEN")

# The Pinned Items data source in the Builder Buddy Notion workspace.
# Override via env var if this ever moves.
# Workspace-specific ID: deliberately NOT defaulted in code so it never lands in git.
# Set PINNED_ITEMS_DATA_SOURCE_ID in the deployment environment.
PINNED_ITEMS_DATA_SOURCE_ID = os.environ.get("PINNED_ITEMS_DATA_SOURCE_ID", "")


class FieldGuardResult:
    """Simple container so callers can see what happened, not just guess."""

    def __init__(self, applied: dict, rejected: dict):
        self.applied = applied      # fields actually safe to write
        self.rejected = rejected    # fields held back, pending review


def filter_allowed_fields(payload: dict, allowlist: set) -> FieldGuardResult:
    """
    Split an incoming payload into (applied, rejected) based on an
    explicit allowlist. Never raises on unknown keys -- fail closed,
    not fail crash.
    """
    if not isinstance(payload, dict):
        return FieldGuardResult({}, {})

    applied = {k: v for k, v in payload.items() if k in allowlist}
    rejected = {k: v for k, v in payload.items() if k not in allowlist}
    return FieldGuardResult(applied, rejected)


def log_unknown_fields(endpoint: str, record_id, actor_user_id, rejected: dict) -> None:
    """
    Write one Pinned Items entry in Notion per rejected batch, so a
    human can decide later whether a field should be added to the
    allowlist. This function only ever informs -- it never applies
    the field itself, and a failure here must never crash or block
    the caller's request.
    """
    if not rejected:
        return

    if not PINNED_ITEMS_DATA_SOURCE_ID:
        logger.warning(
            "PINNED_ITEMS_DATA_SOURCE_ID not set -- unknown field(s) %s on %s were "
            "rejected but NOT pinned to Notion.", list(rejected.keys()), endpoint,
        )
        return

    if not NOTION_TOKEN:
        logger.warning(
            "NOTION_API_TOKEN not set -- unknown field(s) %s on %s were rejected "
            "but NOT pinned to Notion for review. Set NOTION_API_TOKEN to fix this.",
            list(rejected.keys()), endpoint,
        )
        return

    field_list = ", ".join(rejected.keys())
    timestamp = datetime.now(timezone.utc).isoformat()

    properties = {
        "Pin": {
            "title": [{"text": {"content": f"Unknown field(s) on {endpoint}: {field_list}"}}]
        },
        "Type": {"select": {"name": "App Feature"}},
        "Project": {"rich_text": [{"text": {"content": "Core / app_server.py"}}]},
        "Severity": {"select": {"name": "Yellow"}},
        "Status": {"select": {"name": "Open"}},
        "Question": {
            "rich_text": [{
                "text": {
                    "content": (
                        f"Should [{field_list}] be allowed on {endpoint}? "
                        f"Rejected at {timestamp} for record {record_id}, "
                        f"submitted by user {actor_user_id}. Raw values are in "
                        f"the application logs for this request, not stored here."
                    )
                }
            }]
        },
        "Why It Matters": {
            "rich_text": [{
                "text": {
                    "content": (
                        "The fail-closed field guard rejected this automatically. "
                        "It was not applied to the record. Approve = deliberately add "
                        "to the allowlist in field_guard config. Deny = leave rejected."
                    )
                }
            }]
        },
        "Next Action": {
            "rich_text": [{
                "text": {
                    "content": (
                        "Check request logs for the raw value(s), decide legitimate "
                        "vs. stray/malicious, then update the allowlist if approved."
                    )
                }
            }]
        },
    }

    body = {
        "parent": {"type": "data_source_id", "data_source_id": PINNED_ITEMS_DATA_SOURCE_ID},
        "properties": properties,
    }

    try:
        resp = requests.post(
            NOTION_API_URL,
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        # Never let a Notion outage take down the actual application request.
        logger.error("Failed to log unknown fields to Notion Pinned Items: %s", exc)
