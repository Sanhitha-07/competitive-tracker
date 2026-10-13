"""Security helpers for platform sign-in.

Tokens: encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using TOKEN_ENCRYPTION_KEY from backend\\.env.
        Without the key, nothing is stored: connecting is refused rather than saving tokens in plain text.
State:  every sign-in gets a random, single-use `state` tied to one workspace and platform. The callback
        only accepts a state that exists, matches the platform and is less than STATE_TTL old.
PKCE:   X requires a code_verifier / code_challenge pair (S256) for each sign-in.
"""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import select

from config import setting
from models import OAuthState

STATE_TTL = timedelta(minutes=15)


class SecurityError(ValueError):
    pass


def _fernet():
    key = setting("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise SecurityError("TOKEN_ENCRYPTION_KEY is not set, so tokens can't be stored safely.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise SecurityError("TOKEN_ENCRYPTION_KEY is not a valid key. Generate one with the command in SOCIAL_SETUP.md.") from None


def key_ok():
    try:
        _fernet()
        return True
    except SecurityError:
        return False


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode() if value else None


def decrypt(value):
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        # Key changed since the token was saved: treat as no token (the user reconnects).
        raise SecurityError("A stored token can't be read with the current TOKEN_ENCRYPTION_KEY. Reconnect the account.") from None


def pkce_pair():
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def new_state(session, org_id, platform, code_verifier=None):
    _cleanup(session)
    row = OAuthState(state=secrets.token_urlsafe(32), org_id=org_id, platform=platform, code_verifier=code_verifier)
    session.add(row)
    session.commit()
    return row.state


def take_state(session, state, platform):
    """Return the pending sign-in for this state and delete it (single use), or raise."""
    row = session.exec(select(OAuthState).where(OAuthState.state == (state or ""))).first() if state else None
    if not row or row.platform != platform:
        raise SecurityError("This sign-in link is invalid or was already used. Start again from Accounts.")
    session.delete(row)
    session.commit()
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > STATE_TTL:
        raise SecurityError("This sign-in took too long and expired. Start again from Accounts.")
    return row


def _cleanup(session):
    cutoff = datetime.now(timezone.utc) - STATE_TTL * 4
    for row in session.exec(select(OAuthState)).all():
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        if created < cutoff:
            session.delete(row)
