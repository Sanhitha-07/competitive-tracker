"""Meta Graph API: Facebook Login, Facebook Pages and Instagram professional accounts.

One Meta developer app serves both platforms ("Instagram API with Facebook Login"):
  - Facebook: the user signs in, picks a Page they manage; the Page's posts and public counts are read
    with the Page token. Other (competitor) Pages need Meta's "Page Public Content Access" feature.
  - Instagram: the user's Instagram professional (Business/Creator) account must be linked to a Page
    they manage. Competitor profiles are read with Business Discovery, which only works for other
    professional accounts and returns public data (no reach, impressions or views).
Personal Facebook profiles and personal / private Instagram accounts are not supported by these APIs.

Docs: https://developers.facebook.com/docs/graph-api , /docs/instagram-platform/instagram-api-with-facebook-login
"""
import urllib.parse

import social_http as http
from config import META_GRAPH_VERSION_DEFAULT, setting

MAX_POSTS = 100  # posts read per account per refresh (paged 25 at a time)

SCOPES = {
    "facebook": ["pages_show_list", "pages_read_engagement"],
    # business_management is needed when the Page / Instagram account belongs to a business portfolio.
    "instagram": ["instagram_basic", "instagram_manage_insights", "pages_show_list",
                  "pages_read_engagement", "business_management"],
}
RATE_LIMIT_CODES = {4, 17, 32, 613}


def version():
    return setting("META_GRAPH_VERSION") or META_GRAPH_VERSION_DEFAULT


def _graph(path=""):
    return f"https://graph.facebook.com/{version()}/{path}"


def classify(status, body):
    """Map a Graph API error to a meaning (see social_http)."""
    err = (body or {}).get("error") or {}
    code, msg = err.get("code"), err.get("message") or f"Meta returned an error ({status})."
    if code == 190 or status == 401:
        return http.TokenInvalid(f"Meta access expired or was revoked. Reconnect. ({msg})")
    if code in RATE_LIMIT_CODES or (isinstance(code, int) and 80001 <= code <= 80014) or status == 429:
        return http.RateLimited(f"Meta rate limit reached. Try again later. ({msg})")
    if code == 10 or (isinstance(code, int) and 200 <= code <= 299) or status == 403:
        return http.NotPermitted(f"The Meta app doesn't have permission for this data. ({msg})")
    if code == 100 or status == 404:
        return http.ApiError(f"Not found on Meta, or not a public professional account / Page. ({msg})")
    return http.ApiError(msg)


def get(path, token, **params):
    return http.request("GET", _graph(path), params={**params, "access_token": token}, classify=classify)


def paged(path, token, limit=MAX_POSTS, **params):
    """Follow `paging.next` until `limit` items are collected."""
    out, url, query = [], _graph(path), {**params, "access_token": token, "limit": min(25, limit)}
    while url and len(out) < limit:
        data = http.request("GET", url, params=query, classify=classify)
        out += data.get("data", [])
        url, query = (data.get("paging") or {}).get("next"), None
    return out[:limit]


# ---- sign-in ----

def authorize_url(platform, state, redirect_uri):
    q = {"client_id": setting("META_APP_ID"), "redirect_uri": redirect_uri, "state": state,
         "response_type": "code", "scope": ",".join(SCOPES[platform])}
    return f"https://www.facebook.com/{version()}/dialog/oauth?" + urllib.parse.urlencode(q)


def exchange_code(code, redirect_uri):
    """Code -> short-lived user token -> long-lived user token (about 60 days)."""
    short = http.request("GET", _graph("oauth/access_token"), classify=classify, params={
        "client_id": setting("META_APP_ID"), "client_secret": setting("META_APP_SECRET"),
        "redirect_uri": redirect_uri, "code": code})
    long = http.request("GET", _graph("oauth/access_token"), classify=classify, params={
        "grant_type": "fb_exchange_token", "client_id": setting("META_APP_ID"),
        "client_secret": setting("META_APP_SECRET"), "fb_exchange_token": short["access_token"]})
    return {"access_token": long["access_token"], "expires_in": long.get("expires_in")}


def granted_scopes(token):
    data = get("me/permissions", token)
    return [p["permission"] for p in data.get("data", []) if p.get("status") == "granted"]


def pages(token):
    """Pages the user manages, each with its own token and linked Instagram professional account."""
    return paged("me/accounts", token, limit=200,
                 fields="id,name,access_token,instagram_business_account{id,username,name,profile_picture_url}")


# ---- Facebook Pages ----

PAGE_FIELDS = "id,name,username,link,fan_count,followers_count,picture{url}"
POST_FIELDS = ("id,message,created_time,permalink_url,full_picture,shares,attachments{media_type},"
               "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)")


def page_profile(token, page_ref):
    """A Page by id or username. For Pages the user doesn't manage this needs Page Public Content Access."""
    return get(page_ref, token, fields=PAGE_FIELDS)


def page_posts(token, page_id, limit=MAX_POSTS):
    return paged(f"{page_id}/posts", token, limit=limit, fields=POST_FIELDS)


# ---- Instagram professional accounts ----

IG_MEDIA_FIELDS = "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count,thumbnail_url,media_url"
IG_PROFILE_FIELDS = "id,username,name,profile_picture_url,followers_count,media_count"


def ig_discovery(token, ig_user_id, username, limit=MAX_POSTS):
    """Public profile and recent media of another professional account (Business Discovery)."""
    fields = f"business_discovery.username({username}){{{IG_PROFILE_FIELDS},media.limit(25){{{IG_MEDIA_FIELDS}}}}}"
    data = get(ig_user_id, token, fields=fields)["business_discovery"]
    media = list((data.get("media") or {}).get("data", []))
    after = ((data.get("media") or {}).get("paging") or {}).get("cursors", {}).get("after")
    while after and len(media) < limit:
        more_fields = f"business_discovery.username({username}){{media.after({after}).limit(25){{{IG_MEDIA_FIELDS}}}}}"
        page = (get(ig_user_id, token, fields=more_fields)["business_discovery"].get("media") or {})
        media += page.get("data", [])
        after = (page.get("paging") or {}).get("cursors", {}).get("after") if page.get("data") else None
    return data, media[:limit]


def ig_own(token, ig_user_id, limit=MAX_POSTS):
    """The connected account's own profile and media."""
    return get(ig_user_id, token, fields=IG_PROFILE_FIELDS), paged(f"{ig_user_id}/media", token, limit=limit, fields=IG_MEDIA_FIELDS)


def ig_profile(token, ig_user_id, username):
    """Just the public profile of another professional account (no media): one exact username."""
    fields = f"business_discovery.username({username}){{{IG_PROFILE_FIELDS}}}"
    return get(ig_user_id, token, fields=fields)["business_discovery"]
