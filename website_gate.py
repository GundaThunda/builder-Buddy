"""
Shared request gate for Builder Buddy write routes.

website_auth imports website_social_structure, which imports this module, so
this module must not import either of them at load time. Both are imported
inside the wrapper, at request time, which keeps the import graph acyclic.
"""

from functools import wraps

from flask import g, jsonify


def require_auth(admin_only: bool = False, owner_of=None):
    """
    admin_only: caller must hold the admin role.
    owner_of:   callable(route_kwargs) -> user handle. The caller passes if they
                are that handle or an admin. If omitted, any authenticated caller passes.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            import website_auth
            import website_social_structure as social

            handle = website_auth.authenticate_token(website_auth._bearer_token())
            if handle is None:
                return jsonify({"error": "unauthorized"}), 401
            is_admin = social.is_admin(handle)
            if admin_only and not is_admin:
                return jsonify({"error": "forbidden"}), 403
            if owner_of is not None and not is_admin:
                owner = (owner_of(kwargs) or "").strip().lower()
                if owner != handle:
                    return jsonify({"error": "forbidden"}), 403
            g.auth_user = handle
            return view(*args, **kwargs)
        return wrapper
    return decorator
