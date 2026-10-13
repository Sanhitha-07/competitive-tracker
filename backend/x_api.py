"""X API v2 with OAuth 2.0 Authorization Code + PKCE.

The user signs in with X; the access token (2 hours) is refreshed with the refresh token
(scope offline.access). Profiles and posts of any public account can be read with that token.

Cost: the X API is pay-per-use (since February 2026): each post read and each user lookup is billed
from prepaid credits in the X Developer Console. X_MAX_POSTS_PER_ACCOUNT (default 20) caps how many
posts one refresh reads per account. Metrics available depend on the account's API access.

Docs: https://docs.x.com/resources/fundamentals/authentication/oauth-2-0/authorization-code
      https://docs.x.com/x-api/getting-started/pricing
"""
import base64
import urllib.parse

import social_http as http
from config import setting

API = "https://api.x.com/2/"
AUTHORIZE = "https://x.com/i/oauth2/authorize"
TOKEN = "https://api.x.com/2/oauth2/token"
SCOPES = ["tweet.read", "users.read", "offline.access"]
USER_FIELDS = "id,name,username,profile_image_url,public_metrics,verified"
TWEET_FIELDS = "id,text,created_at,public_metrics,attachments,entities"


def max_posts():
    try:
        return max(5, min(int(setting("X_MAX_POSTS_PER_ACCOUNT") or 20), 100))
    except ValueError:
        return 20


def classify(status, body):
    detail = (body or {}).get("detail") or (body or {}).get("title") or (body or {}).get("error_description") \
        or ((body or {}).get("errors") or [{}])[0].get("message") or f"X returned an error ({status})."
    if status == 401 or (body or {}).get("error") == "invalid_grant":
        return http.TokenInvalid(f"X access expired or was revoked. Reconnect. ({detail})")
    if status == 429:
        return http.RateLimited(f"X rate limit reached. Try again later. ({detail})")
    if status == 402:
        return http.NotPermitted(f"Your X API credits are used up. Add credits in the X Developer Console. ({detail})")
    if status == 403:
        return http.NotPermitted(f"Your X app's access doesn't include this data. ({detail})")
    if status == 404:
        return http.ApiError(f"X account not found. ({detail})")
    return http.ApiError(detail)


def _client_auth():
    """Confidential clients (Web App) authenticate with Basic auth; public clients send client_id."""
    cid, secret = setting("X_CLIENT_ID"), setting("X_CLIENT_SECRET")
    if secret:
        return {"Authorization": "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode()}, {}
    return {}, {"client_id": cid}


def authorize_url(state, code_challenge, redirect_uri):
    q = {"response_type": "code", "client_id": setting("X_CLIENT_ID"), "redirect_uri": redirect_uri,
         "scope": " ".join(SCOPES), "state": state, "code_challenge": code_challenge, "code_challenge_method": "S256"}
    return AUTHORIZE + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def exchange_code(code, code_verifier, redirect_uri):
    headers, extra = _client_auth()
    return http.request("POST", TOKEN, headers=headers, classify=classify, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "code_verifier": code_verifier, **extra})


def refresh(refresh_token):
    headers, extra = _client_auth()
    return http.request("POST", TOKEN, headers=headers, classify=classify,
                        data={"grant_type": "refresh_token", "refresh_token": refresh_token, **extra})


def _get(path, token, **params):
    return http.request("GET", API + path, params=params, headers={"Authorization": f"Bearer {token}"}, classify=classify)


def me(token):
    return _get("users/me", token, **{"user.fields": USER_FIELDS})["data"]


def user_by_username(token, username):
    data = _get(f"users/by/username/{urllib.parse.quote(username)}", token, **{"user.fields": USER_FIELDS})
    if "data" not in data:
        raise http.ApiError(f"X account @{username} not found.")
    return data["data"]


def user_posts(token, user_id, limit=None):
    """The account's latest original posts (no replies or reposts), with public metrics and media types."""
    limit = limit or max_posts()
    out, media, next_token = [], {}, None
    while len(out) < limit:
        params = {"max_results": max(5, min(100, limit - len(out))), "exclude": "retweets,replies",
                  "tweet.fields": TWEET_FIELDS, "expansions": "attachments.media_keys",
                  "media.fields": "media_key,type,preview_image_url,url"}
        if next_token:
            params["pagination_token"] = next_token
        data = _get(f"users/{user_id}/tweets", token, **params)
        for m in (data.get("includes") or {}).get("media", []):
            media[m["media_key"]] = m
        out += data.get("data", [])
        next_token = (data.get("meta") or {}).get("next_token")
        if not next_token:
            break
    return out[:limit], media


def search_users(token, query, limit=6):
    """Relevance search over public accounts (name, handle, bio). X offers this only on Pro access
    and higher; on other plans X answers 403 and callers fall back to an exact username lookup."""
    data = _get("users/search", token, query=query, max_results=max(1, min(limit, 100)), **{"user.fields": USER_FIELDS})
    return data.get("data", [])[:limit]
