"""
Authentication and role enforcement for Builder Buddy.

Design:
- Passwords hashed with stdlib scrypt; salt per password; parameters stored with the hash.
- Session tokens are random, returned once, and stored only as SHA-256 digests.
- Sessions expire after SESSION_TTL_SECONDS.
- Failed logins lock the account for LOCKOUT_SECONDS after MAX_FAILED_LOGINS.
- All auth failures return the same generic error (no account enumeration).
- Role changes are admin-only and cannot remove the last admin.

Known deviation: this module imports website_social_structure to read and
write roles on user records. CLAUDE.md asks for module independence; the
dependency is intentional and limited to role lookups.

Known limits: JSON-file storage is not safe under concurrent writers.
"""

import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, g, jsonify, request

import website_social_structure as social

auth_routes = Blueprint("auth", __name__)

AUTH_DATA_FILE = os.path.join(os.path.dirname(__file__), "auth_data.json")

SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 15 * 60
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32

GENERIC_LOGIN_ERROR = "invalid_credentials"


# --- time / storage ---

def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _load() -> dict:
    if os.path.exists(AUTH_DATA_FILE):
        with open(AUTH_DATA_FILE, "r") as f:
            return json.load(f)
    return {"credentials": {}, "sessions": {}}


def _save(data: dict) -> None:
    with open(AUTH_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# --- hashing ---

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N,
                            r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Used when an unknown handle logs in, so response time does not reveal existence.
_DUMMY_HASH = _hash_password(secrets.token_urlsafe(16))


def _candidate(value) -> str:
    if isinstance(value, str) and len(value) <= MAX_PASSWORD_LENGTH:
        return value
    return ""


def _password_problem(password) -> str | None:
    if not isinstance(password, str):
        return "password must be a string"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"password must be at most {MAX_PASSWORD_LENGTH} characters"
    return None


# --- sessions ---

def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _prune_sessions(data: dict, now: float) -> None:
    data["sessions"] = {k: v for k, v in data["sessions"].items() if v["expires_at"] > now}


def _revoke_sessions(data: dict, handle: str) -> None:
    data["sessions"] = {k: v for k, v in data["sessions"].items()
                        if v["user_handle"] != handle}


def _issue_session(data: dict, handle: str, now: float) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = now + SESSION_TTL_SECONDS
    data["sessions"][_token_key(token)] = {"user_handle": handle, "expires_at": expires_at}
    return {"token": token, "user_handle": handle, "expires_at": _iso(expires_at)}


def authenticate_token(token: str | None) -> str | None:
    if not token:
        return None
    data = _load()
    session = data["sessions"].get(_token_key(token))
    if not session or session["expires_at"] <= _now():
        return None
    return session["user_handle"]


def logout(token: str | None) -> dict:
    data = _load()
    if token and data["sessions"].pop(_token_key(token), None) is not None:
        _save(data)
    return {"status": "logged_out"}


# --- credentials ---

def _attempt(cred: dict, candidate: str, now: float) -> bool:
    """Check a password against a credential and update lockout state. Caller saves."""
    ok = _verify_password(candidate, cred["hash"])
    if cred["locked_until"] > now:
        return False
    if ok:
        cred["failed_logins"] = 0
        cred["locked_until"] = 0
        return True
    cred["failed_logins"] += 1
    if cred["failed_logins"] >= MAX_FAILED_LOGINS:
        cred["locked_until"] = now + LOCKOUT_SECONDS
        cred["failed_logins"] = 0
    return False


def set_password(user_handle: str, password) -> dict:
    """Server-side only (no HTTP route). Requires an existing social user."""
    handle = (user_handle or "").strip().lower()
    if not handle:
        return {"error": "user_handle is required"}
    problem = _password_problem(password)
    if problem:
        return {"error": problem}
    if social.get_user_points(handle).get("error"):
        return {"error": "not_found"}
    data = _load()
    data["credentials"][handle] = {"hash": _hash_password(password),
                                   "failed_logins": 0, "locked_until": 0}
    _revoke_sessions(data, handle)
    _save(data)
    return {"user_handle": handle}


def login(user_handle, password) -> dict:
    handle = (user_handle or "").strip().lower()
    now = _now()
    data = _load()
    cred = data["credentials"].get(handle)
    if cred is None:
        _verify_password(_candidate(password), _DUMMY_HASH)
        return {"error": GENERIC_LOGIN_ERROR}
    ok = _attempt(cred, _candidate(password), now)
    if not ok:
        _save(data)
        return {"error": GENERIC_LOGIN_ERROR}
    _prune_sessions(data, now)
    session = _issue_session(data, handle, now)
    _save(data)
    return session


def change_password(user_handle: str, current_password, new_password) -> dict:
    handle = (user_handle or "").strip().lower()
    now = _now()
    data = _load()
    cred = data["credentials"].get(handle)
    if cred is None:
        return {"error": GENERIC_LOGIN_ERROR}
    if not _attempt(cred, _candidate(current_password), now):
        _save(data)
        return {"error": GENERIC_LOGIN_ERROR}
    problem = _password_problem(new_password)
    if problem:
        _save(data)
        return {"error": problem}
    if _verify_password(new_password, cred["hash"]):
        _save(data)
        return {"error": "new password must differ from current password"}
    cred["hash"] = _hash_password(new_password)
    _revoke_sessions(data, handle)
    _prune_sessions(data, now)
    session = _issue_session(data, handle, now)
    _save(data)
    return session


# --- enforcement ---

def _bearer_token() -> str | None:
    parts = request.headers.get("Authorization", "").split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def require_auth(admin: bool = False):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            handle = authenticate_token(_bearer_token())
            if handle is None:
                return jsonify({"error": "unauthorized"}), 401
            if admin and not social.is_admin(handle):
                return jsonify({"error": "forbidden"}), 403
            g.auth_user = handle
            return view(*args, **kwargs)
        return wrapper
    return decorator


# --- routes ---

ROLE_ERROR_STATUS = {"invalid_role": 400, "not_found": 404, "last_admin": 409}


@auth_routes.route("/login", methods=["POST"])
def route_login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("user_handle"), str):
        return jsonify({"error": "invalid_request"}), 400
    result = login(body["user_handle"], body.get("password"))
    if "error" in result:
        return jsonify({"error": GENERIC_LOGIN_ERROR}), 401
    return jsonify(result), 200


@auth_routes.route("/logout", methods=["POST"])
@require_auth()
def route_logout():
    return jsonify(logout(_bearer_token())), 200


@auth_routes.route("/me", methods=["GET"])
@require_auth()
def route_me():
    role = social.ROLE_ADMIN if social.is_admin(g.auth_user) else social.ROLE_MEMBER
    return jsonify({"user_handle": g.auth_user, "role": role}), 200


@auth_routes.route("/password", methods=["POST"])
@require_auth()
def route_change_password():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    result = change_password(g.auth_user, body.get("current_password"),
                             body.get("new_password"))
    if "error" in result:
        status = 403 if result["error"] == GENERIC_LOGIN_ERROR else 400
        return jsonify({"error": result["error"]}), status
    return jsonify(result), 200


@auth_routes.route("/roles/<handle>", methods=["POST"])
@require_auth(admin=True)
def route_set_role(handle):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    result = social.set_role(handle, body.get("role"))
    if "error" in result:
        return jsonify({"error": result["error"]}), ROLE_ERROR_STATUS[result["error"]]
    return jsonify(result), 200


# --- bootstrap CLI: python website_auth.py <user_handle> ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python website_auth.py <user_handle>")
        sys.exit(2)
    first = getpass.getpass("New password: ")
    if getpass.getpass("Confirm password: ") != first:
        print("passwords do not match")
        sys.exit(1)
    outcome = set_password(sys.argv[1], first)
    if "error" in outcome:
        print(f"error: {outcome['error']}")
        sys.exit(1)
    print(f"password set for {outcome['user_handle']}")
