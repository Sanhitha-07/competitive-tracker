"""Instagram, Facebook and X: configuration status, sign-in (OAuth) and stored connections.

A platform is "configured" when its settings are in backend\\.env (see SOCIAL_SETUP.md). Until then it
is shown as "Not configured" and no request is ever sent to it. A workspace is "connected" only after
the platform's real sign-in succeeded and a token was stored (encrypted).

Connections belong to one workspace: every lookup is by (org_id, platform), and a sign-in's `state`
is tied to the workspace that started it.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import select

import meta_api
import secure
import social_http as http
import x_api
from config import FRONTEND_URL_DEFAULT, PUBLIC_API_URL_DEFAULT, SOCIAL_SETTINGS, setting
from models import SocialConnection

PLATFORMS = {
    "instagram": {
        "label": "Instagram",
        "provider": "meta",
        "required": ["META_APP_ID", "META_APP_SECRET", "TOKEN_ENCRYPTION_KEY"],
        "summary": "Needs a Meta developer app and your Instagram professional (Business or Creator) "
                   "account linked to a Facebook Page you manage.",
        "competitors": "Competitors must be public Instagram Business or Creator accounts (read with Business "
                       "Discovery). Personal and private accounts can't be read. Likes may be hidden; views and "
                       "reach of other accounts aren't available.",
        "setup": [
            "Create an app at developers.facebook.com (type: Business) and add Facebook Login for Business.",
            "Add the Instagram product: 'Instagram API with Facebook Login'.",
            "Add this redirect URI to the Facebook Login settings: {redirect}",
            "Request permissions: instagram_basic, instagram_manage_insights, pages_show_list, "
            "pages_read_engagement, business_management. Use outside your own team needs App Review and "
            "Business Verification.",
            "Put META_APP_ID, META_APP_SECRET and TOKEN_ENCRYPTION_KEY in backend\\.env, then restart the API.",
        ],
    },
    "facebook": {
        "label": "Facebook",
        "provider": "meta",
        "required": ["META_APP_ID", "META_APP_SECRET", "TOKEN_ENCRYPTION_KEY"],
        "summary": "Needs a Meta developer app. You connect a Facebook Page you manage, not a personal profile.",
        "competitors": "Reading other Pages' posts needs Meta's 'Page Public Content Access' feature (App Review "
                       "and Business Verification). Until it's approved, competitor Pages stay Unverified.",
        "setup": [
            "Create an app at developers.facebook.com (type: Business) and add Facebook Login for Business.",
            "Add this redirect URI to the Facebook Login settings: {redirect}",
            "Request permissions: pages_show_list, pages_read_engagement. For competitor Pages, apply for the "
            "'Page Public Content Access' feature.",
            "Put META_APP_ID, META_APP_SECRET and TOKEN_ENCRYPTION_KEY in backend\\.env, then restart the API.",
        ],
    },
    "x": {
        "label": "X",
        "provider": "x",
        "required": ["X_CLIENT_ID", "TOKEN_ENCRYPTION_KEY"],
        "optional": ["X_CLIENT_SECRET"],
        "summary": "Needs an X developer app with OAuth 2.0 and prepaid API credits (the X API is pay-per-use).",
        "competitors": "Any public X account can be added. Each post read and profile lookup uses paid X API "
                       "credits, so a refresh reads at most X_MAX_POSTS_PER_ACCOUNT posts per account.",
        "setup": [
            "Create a project and app at developer.x.com and buy API credits (pay-per-use).",
            "In User authentication settings choose OAuth 2.0, type 'Web App', and add this callback URL: {redirect}",
            "Scopes used: tweet.read, users.read, offline.access.",
            "Put X_CLIENT_ID, X_CLIENT_SECRET and TOKEN_ENCRYPTION_KEY in backend\\.env, then restart the API.",
        ],
    },
}
EXPIRY_MARGIN = timedelta(minutes=5)


class NotReady(ValueError):
    """The platform can't be used yet (not configured, or not connected for this workspace)."""


def get_platform(platform):
    if platform not in PLATFORMS:
        raise KeyError(platform)
    return PLATFORMS[platform]


def missing(platform):
    return [k for k in PLATFORMS[platform]["required"] if not setting(k)] + \
           (["TOKEN_ENCRYPTION_KEY (invalid)"] if setting("TOKEN_ENCRYPTION_KEY") and not secure.key_ok() else [])


def configured(platform):
    return not missing(platform)


def redirect_uri(platform):
    base = (setting("PUBLIC_API_URL") or PUBLIC_API_URL_DEFAULT).rstrip("/")
    return f"{base}/oauth/{platform}/callback"


def frontend_url():
    return (setting("FRONTEND_URL") or FRONTEND_URL_DEFAULT).rstrip("/")


def connection(session, org_id, platform):
    return session.exec(select(SocialConnection).where(SocialConnection.org_id == org_id,
                                                       SocialConnection.platform == platform)).first()


def describe(session, org_id):
    """Everything the Accounts page shows per platform. Never includes tokens."""
    out = []
    for pid, p in PLATFORMS.items():
        conn = connection(session, org_id, pid)
        miss = missing(pid)
        if miss:
            state = "not_configured"
        elif not conn or conn.status == "disconnected":
            state = "not_connected"
        else:
            state = conn.status
        out.append({
            "id": pid, "label": p["label"], "state": state, "configured": not miss,
            "missing": miss, "settings": {k: SOCIAL_SETTINGS.get(k, "") for k in p["required"] + p.get("optional", [])},
            "summary": p["summary"], "competitors": p["competitors"],
            "setup": [s.format(redirect=redirect_uri(pid)) for s in p["setup"]],
            "redirect_uri": redirect_uri(pid),
            "connection": None if not conn or conn.status == "disconnected" else {
                "account_name": conn.account_name, "username": conn.username, "status": conn.status,
                "connected_at": _iso(conn.connected_at), "expires_at": _iso(conn.expires_at),
                "last_error": conn.last_error, "scopes": conn.scopes or [],
                "choices": [{k: v for k, v in c.items() if k != "access_token"} for c in (conn.choices or [])],
            },
        })
    return out


def _iso(dt):
    if not dt:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _now():
    return datetime.now(timezone.utc)


# ---- sign-in ----

def start(session, org_id, platform):
    """The platform's sign-in URL for this workspace. Refuses when not configured."""
    if not configured(platform):
        raise NotReady(f"{PLATFORMS[platform]['label']} isn't configured. Add {', '.join(missing(platform))} to backend\\.env.")
    if PLATFORMS[platform]["provider"] == "x":
        verifier, challenge = secure.pkce_pair()
        state = secure.new_state(session, org_id, platform, verifier)
        return x_api.authorize_url(state, challenge, redirect_uri(platform))
    state = secure.new_state(session, org_id, platform)
    return meta_api.authorize_url(platform, state, redirect_uri(platform))


def finish(session, platform, code, state):
    """Handle the platform's redirect: check state, exchange the code, store the connection."""
    pending = secure.take_state(session, state, platform)
    if not configured(platform):
        raise NotReady(f"{PLATFORMS[platform]['label']} isn't configured.")
    conn = connection(session, pending.org_id, platform) or SocialConnection(org_id=pending.org_id, platform=platform)
    if PLATFORMS[platform]["provider"] == "x":
        tok = x_api.exchange_code(code, pending.code_verifier, redirect_uri(platform))
        user = x_api.me(tok["access_token"])
        conn.access_token_enc = secure.encrypt(tok["access_token"])
        conn.refresh_token_enc = secure.encrypt(tok.get("refresh_token"))
        conn.expires_at = _now() + timedelta(seconds=int(tok.get("expires_in") or 7200))
        conn.scopes = (tok.get("scope") or "").split()
        conn.external_id, conn.account_name, conn.username = user["id"], user.get("name"), user.get("username")
        conn.status, conn.choices, conn.page_token_enc = "connected", None, None
    else:
        tok = meta_api.exchange_code(code, redirect_uri(platform))
        token = tok["access_token"]
        conn.access_token_enc = secure.encrypt(token)
        conn.expires_at = _now() + timedelta(seconds=int(tok["expires_in"])) if tok.get("expires_in") else None
        conn.scopes = meta_api.granted_scopes(token)
        pages = meta_api.pages(token)
        if platform == "instagram":
            pages = [p for p in pages if p.get("instagram_business_account")]
        conn.choices = [{"id": p["id"], "name": p.get("name"),
                         "instagram": p.get("instagram_business_account")} for p in pages]
        conn.external_id = conn.account_name = conn.username = conn.page_token_enc = None
        if not pages:
            conn.status = "error"
            conn.last_error = ("No Instagram professional account is linked to a Page you manage." if platform == "instagram"
                               else "You don't manage any Facebook Page with this login (personal profiles aren't supported).")
        elif len(pages) == 1:
            _choose(conn, pages[0])
        else:
            conn.status = "needs_page"
    if conn.status != "error":
        conn.last_error = None
    conn.connected_at = conn.updated_at = _now()
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return conn


def _choose(conn, page):
    if conn.platform == "instagram":
        ig = page["instagram_business_account"]
        conn.external_id, conn.username = ig["id"], ig.get("username")
        conn.account_name = ig.get("name") or ig.get("username")
    else:
        conn.external_id, conn.account_name, conn.username = page["id"], page.get("name"), None
        conn.page_token_enc = secure.encrypt(page["access_token"])
    conn.status, conn.last_error = "connected", None


def choose_page(session, conn, page_id):
    """Meta: use this Page (Facebook) or the Instagram account linked to it."""
    if conn.platform not in ("facebook", "instagram"):
        raise ValueError("Only Facebook and Instagram connections have Pages to choose.")
    if not any(c["id"] == page_id for c in conn.choices or []):
        raise ValueError("Choose one of the Pages listed for this connection.")
    pages = meta_api.pages(secure.decrypt(conn.access_token_enc))  # fresh Page token, never stored in choices
    page = next((p for p in pages if p["id"] == page_id), None)
    if not page:
        raise ValueError("This Page is no longer available to your login. Reconnect.")
    _choose(conn, page)
    conn.updated_at = _now()
    session.add(conn)
    session.commit()
    return conn


def disconnect(session, conn):
    """Forget the tokens. (Access can also be removed in the platform's own settings.)"""
    conn.access_token_enc = conn.refresh_token_enc = conn.page_token_enc = None
    conn.status, conn.choices, conn.expires_at = "disconnected", None, None
    conn.updated_at = _now()
    session.add(conn)
    session.commit()


def mark_invalid(session, conn, message):
    conn.status, conn.last_error, conn.updated_at = "expired", message[:300], _now()
    session.add(conn)
    session.commit()


# ---- tokens for data collection ----

@dataclass
class Context:
    platform: str
    token: str                    # user token (Meta) or access token (X)
    own_id: str | None = None     # our Instagram account id / Facebook Page id / X user id
    page_token: str | None = None  # Facebook: our Page's token


def context(session, org_id, platform):
    """Credentials to collect data for this workspace, or None if the platform isn't usable yet.
    Refreshes X tokens shortly before they expire."""
    if platform not in PLATFORMS or not configured(platform):
        return None
    conn = connection(session, org_id, platform)
    if not conn or conn.status != "connected" or not conn.access_token_enc:
        return None
    try:
        if PLATFORMS[platform]["provider"] == "x" and conn.expires_at:
            exp = conn.expires_at if conn.expires_at.tzinfo else conn.expires_at.replace(tzinfo=timezone.utc)
            if exp - EXPIRY_MARGIN <= _now():
                _refresh_x(session, conn)
        return Context(platform, secure.decrypt(conn.access_token_enc), conn.external_id, secure.decrypt(conn.page_token_enc))
    except (http.TokenInvalid, secure.SecurityError) as exc:
        mark_invalid(session, conn, str(exc))
        return None


def _refresh_x(session, conn):
    rt = secure.decrypt(conn.refresh_token_enc)
    if not rt:
        raise http.TokenInvalid("X access expired. Reconnect.")
    tok = x_api.refresh(rt)
    conn.access_token_enc = secure.encrypt(tok["access_token"])
    if tok.get("refresh_token"):  # X rotates refresh tokens
        conn.refresh_token_enc = secure.encrypt(tok["refresh_token"])
    conn.expires_at = _now() + timedelta(seconds=int(tok.get("expires_in") or 7200))
    conn.updated_at = _now()
    session.add(conn)
    session.commit()


def not_ready_reason(session, org_id, platform):
    label = PLATFORMS[platform]["label"]
    if not configured(platform):
        return f"Not configured — Add API credentials to enable this integration ({', '.join(missing(platform))})."
    conn = connection(session, org_id, platform)
    if conn and conn.status == "expired":
        return f"{label} access expired. Reconnect it in Accounts."
    if conn and conn.status == "needs_page":
        return f"Choose which Page to use for {label} in Accounts."
    return f"{label} isn't connected for this workspace yet. Connect it in Accounts."


def is_connected(session, org_id, platform):
    """Configured and connected, judged from stored state only: no API call, no token refresh."""
    conn = connection(session, org_id, platform)
    return configured(platform) and bool(conn and conn.status == "connected" and conn.access_token_enc)


# ---- profile suggestions while typing (Accounts form) ----

SUGGEST_TTL = timedelta(minutes=10)
_suggest_cache = {}  # (org_id, platform, query) -> (time, result); avoids repeating paid lookups


def suggest(session, org_id, platform, query):
    """Profiles matching what the user typed. No request is made unless the platform is connected.
    Instagram and Facebook only support exact lookups; X searches when its plan allows."""
    import connectors  # here, not at the top: connectors imports the API clients this module also uses

    q = (query or "").strip()
    label = PLATFORMS[platform]["label"]
    if not configured(platform):
        return {"available": False, "results": [], "note": "Integration is not configured yet. Contact your administrator to enable it."}
    if not is_connected(session, org_id, platform):
        return {"available": False, "results": [], "note": f"Suggestions appear once {label} is connected (Platform connections, above)."}
    key = (org_id, platform, q.lower().lstrip("@"))
    hit = _suggest_cache.get(key)
    if hit and _now() - hit[0] < SUGGEST_TTL:
        return hit[1]
    ctx = context(session, org_id, platform)
    if ctx is None:
        return {"available": False, "results": [], "note": not_ready_reason(session, org_id, platform)}
    try:
        mode, results = connectors.CONNECTORS[platform].suggest(q, ctx)
    except http.TokenInvalid as exc:
        mark_invalid(session, connection(session, org_id, platform), str(exc))
        return {"available": False, "results": [], "note": f"{label} access expired. Reconnect it above."}
    except http.RateLimited:
        return {"available": True, "results": [], "note": f"{label} rate limit reached. Type the full username and add it; it's checked on the next Refresh."}
    except http.NotPermitted as exc:
        return {"available": True, "results": [], "note": str(exc)}
    note = None if results else (
        "No public Business or Creator account with this exact username." if platform == "instagram" else
        "No Page with this exact name or link." if platform == "facebook" else "No X account found.")
    result = {"available": True, "mode": mode, "results": results, "note": note}
    _suggest_cache[key] = (_now(), result)
    return result
