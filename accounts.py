"""
Holds a connected merchant's Razorpay API credentials in memory only, keyed by
a random session token - never written to disk, never put in the (signed but
unencrypted) session cookie itself. The cookie only carries the lookup token.

Deliberately process-local: fine for a single-instance prototype where losing
connections on a restart is a non-issue. A multi-instance deployment would need
this backed by a real store (e.g. Redis) with proper encryption at rest.
"""
import secrets

_STORE = {}


def create_session(key_id, key_secret):
    token = secrets.token_urlsafe(24)
    _STORE[token] = {"key_id": key_id, "key_secret": key_secret}
    return token


def get_credentials(token):
    if not token:
        return None
    return _STORE.get(token)


def clear_session(token):
    _STORE.pop(token, None)


def mask_key_id(key_id):
    if not key_id or len(key_id) <= 8:
        return key_id or ""
    return f"{key_id[:8]}••••{key_id[-4:]}"
