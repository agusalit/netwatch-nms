import logging

import bcrypt
from fastapi import HTTPException, Request

from app import config

logger = logging.getLogger("nms.auth")


def _truncate_72_bytes(password: str) -> bytes:
    """bcrypt only uses the first 72 bytes of a password and raises on
    anything longer (as of bcrypt 4.x — older versions silently truncated).
    Truncating ourselves keeps behavior predictable either way."""
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_truncate_72_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_truncate_72_bytes(password), hashed.encode("utf-8"))
    except ValueError:
        # Malformed/empty hash (e.g. ADMIN_PASSWORD_HASH set to garbage) —
        # fail closed rather than raising.
        return False


def verify_credentials(username: str, password: str) -> bool:
    if username != config.ADMIN_USERNAME:
        return False
    if not config.ADMIN_PASSWORD_HASH:
        logger.warning(
            "ADMIN_PASSWORD_HASH is not set — login is disabled until it's "
            "configured. Generate one with scripts/generate_password_hash.py."
        )
        return False
    return verify_password(password, config.ADMIN_PASSWORD_HASH)


def require_login(request: Request):
    """Dependency for protected routes — redirects to /login if there's no
    active session.

    Known limitation: for an HTMX-polled endpoint (the device grid, polled
    every 5s), an expired session means that poll receives the login page's
    HTML instead of a clean client-side redirect, since HTMX/fetch follows
    the 303 automatically and swaps in whatever HTML comes back. Building a
    proper 401 + client-side-redirect handshake is a reasonable future
    improvement, but out of scope for this basic, single-admin setup.
    """
    if not request.session.get("user"):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return request.session["user"]