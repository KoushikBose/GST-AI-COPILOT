"""Password hashing — bcrypt, called directly (not through passlib).

passlib is unmaintained (last release 2020) and its bundled backend
self-test is incompatible with bcrypt>=4.1 (raises ValueError on its own
internal probe string before any real password is ever hashed — see
https://github.com/pyca/bcrypt/issues/684). Calling `bcrypt` directly avoids
that entirely and has no compatibility surface to break.
"""

from __future__ import annotations

import bcrypt

# bcrypt silently ignores bytes past 72 — never let two different long
# passwords collide on a truncated hash. Reject outright instead.
_MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    encoded = plain_password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {_MAX_PASSWORD_BYTES} bytes.")
    hashed = bcrypt.hashpw(encoded, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    encoded = plain_password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))
    except ValueError:
        # Malformed/legacy hash — never let a bad stored value crash login.
        return False
