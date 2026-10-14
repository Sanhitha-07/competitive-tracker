"""Meta Graph API: Instagram (Business Discovery) and Facebook Pages.

Instagram: other accounts are read with Business Discovery, "through" your own Instagram
professional account (META_IG_USER_ID). It only works for Business and Creator accounts;
personal and age-gated accounts can't be read. Public fields: followers, media count, and per
post likes, comments and (Reels only) views. Hidden like counts are left out, not counted as 0.

Facebook: public Pages are read with the Pages API. Pages you don't manage need the
"Page Public Content Access" feature (Meta App Review + business verification). Public fields:
followers/fans, and per post reactions, comments and shares. Reach and impressions are private
(Page Insights) and are never available for competitors.

Calls are counted per hour so one Refresh can't use up the app's rate limit.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import config

MAX_POSTS = 60          # latest posts read per account per refresh
PAGE_SIZE = 30
RATE_LIMIT_CODES = {4, 17, 32, 613, *range(80001, 80015)}


class RateLimited(ValueError):
    """Meta's rate limit (or our own hourly budget) is reached."""


class NotConfigured(ValueError):
    pass


# Calls made by this app process in the current hour (an estimate, not Meta's own figure).
_usage = {"hour": None, "calls": 0}


def _hour():
    return int(time.time() // 3600)


def calls_used():
    if _usage["hour"] != _hour():
        _usage.update(hour=_hour(), calls=0)
    return _usage["calls"]


def budget_left():
    return max(config.META_HOURLY_BUDGET - calls_used(), 0)


def configured():
    return {"token": bool(config.META_ACCESS_TOKEN), "instagram": bool(config.META_ACCESS_TOKEN and config.META_IG_USER_ID),
            "facebook": bool(config.META_ACCESS_TOKEN)}


def _base():
    return f"https://graph.facebook.com/{config.META_GRAPH_VERSION}/"


def _error(exc):
    """Turn a Graph API error into a message a non-developer can act on."""
    try:
        err = json.load(exc)["error"]
    except Exception:
        return ValueError(f"Meta returned an error ({exc.code}).")
    code, sub, msg = err.get("code"), err.get("error_subcode"), err.get("message", "")
    if code in RATE_LIMIT_CODES:
        _usage["calls"] = config.META_HOURLY_BUDGET  # stop calling for the rest of the hour
        return RateLimited("Meta's rate limit is reached. Try again in an hour.")
    if code == 190:
        return ValueError("The Meta access token is invalid or expired. Create a new one and update META_ACCESS_TOKEN in backend\\.env.")
    if code == 10 or (code and 200 <= code <= 299):
        return PermissionError("Meta refused access: the app needs the right permissions "
                               "(Instagram: instagram_basic + business discovery; Facebook: Page Public Content Access). See SETUP.md.")
    if code == 110 or (code == 100 and sub in (33, 2207013)):
        return ValueError("Account not found, or it isn't a public Business/Creator account (personal accounts can't be read).")
    return ValueError(f"Meta error: {msg}")


def _get(path, url=None, **params):
    if not config.META_ACCESS_TOKEN:
        raise NotConfigured("Meta access token is missing. Add META_ACCESS_TOKEN to backend\\.env (see SETUP.md).")
    if calls_used() >= config.META_HOURLY_BUDGET:
        raise RateLimited(f"Hourly Meta budget of {config.META_HOURLY_BUDGET} calls reached. Try again in an hour.")
    _usage["calls"] += 1
    if url is None:
        params["access_token"] = config.META_ACCESS_TOKEN
        url = _base() + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=25) as res:
            return json.load(res)
    except urllib.error.HTTPError as exc:
        raise _error(exc) from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Can't reach Meta: {exc.reason}") from exc


def _when(text):
    """Graph API times look like 2026-10-12T08:30:00+0000."""
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text.replace("Z", "+00:00"))
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _title(caption):
    """A post has no title on Instagram/Facebook: use the caption's first line (hashtags kept as tags)."""
    text = (caption or "").strip()
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first = re.sub(r"\s+", " ", first)
    if not first:
        return "(no caption)"
    return first if len(first) <= 140 else first[:137].rstrip() + "…"


def hashtags(text):
    return list(dict.fromkeys(m.lower() for m in re.findall(r"#(\w[\wऀ-෿]*)", text or "")))[:20]


# ---- Instagram ----

def ig_username(text):
    """'@nike', 'nike', 'instagram.com/nike/', 'https://www.instagram.com/nike?igsh=..' -> 'nike'."""
    t = urllib.parse.unquote(text.strip())
    if "instagram.com" in t.lower():
        path = urllib.parse.urlparse(t if "://" in t else "https://" + t).path
        parts = [p for p in path.split("/") if p]
        if not parts or parts[0] in ("p", "reel", "reels", "stories", "explore"):
            raise ValueError("That link points to a post, not an account. Open the profile and copy its link, or type @username.")
        t = parts[0]
    t = t.lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", t):
        raise ValueError("Instagram usernames use only letters, numbers, dots and underscores.")
    return t.lower()


_IG_MEDIA_FIELDS = ("id,caption,comments_count,like_count,view_count,media_type,media_product_type,"
                    "permalink,timestamp,thumbnail_url,media_url")
_IG_PROFILE_FIELDS = "id,username,name,profile_picture_url,followers_count,media_count"


def _discovery(username, media=None):
    if not config.META_IG_USER_ID:
        raise NotConfigured("Add META_IG_USER_ID (your own Instagram professional account ID) to backend\\.env. "
                            "Instagram competitors are read through it (see SETUP.md).")
    fields = _IG_PROFILE_FIELDS + (f",{media}" if media else "")
    data = _get(config.META_IG_USER_ID, fields=f"business_discovery.username({username}){{{fields}}}")
    bd = data.get("business_discovery")
    if not bd:
        raise ValueError(f'Instagram account "@{username}" not found, or it isn\'t a Business/Creator account.')
    return bd


def ig_find(text):
    bd = _discovery(ig_username(text))
    return {"channel_id": bd["id"], "title": bd.get("name") or bd["username"], "handle": "@" + bd["username"],
            "thumbnail": bd.get("profile_picture_url"), "subscribers": bd.get("followers_count")}


def ig_format(m):
    product, kind = m.get("media_product_type"), m.get("media_type")
    if product == "REELS":
        return "reel"
    if kind == "CAROUSEL_ALBUM":
        return "carousel"
    if kind == "VIDEO":
        return "video"
    return "image"


def ig_item(m):
    caption = m.get("caption") or ""
    fmt = ig_format(m)
    return {
        "title": _title(caption),
        "link": m["permalink"],
        "published_at": _when(m["timestamp"]),
        "format": fmt,
        "thumbnail": m.get("thumbnail_url") or (m.get("media_url") if m.get("media_type") != "VIDEO" else None),
        "tags": hashtags(caption),
        "views": m.get("view_count") if fmt == "reel" else None,
        "likes": m.get("like_count"),       # missing when the creator hides likes
        "comments": m.get("comments_count"),
        "shares": None,                      # not public on Instagram
        "duration_seconds": None,
    }


def ig_account(text, max_posts=MAX_POSTS):
    """Profile + latest posts in as few calls as possible (media is nested in the same request)."""
    username = ig_username(text)
    bd = _discovery(username, f"media.limit({PAGE_SIZE}){{{_IG_MEDIA_FIELDS}}}")
    media = list((bd.get("media") or {}).get("data", []))
    after = ((bd.get("media") or {}).get("paging") or {}).get("cursors", {}).get("after")
    while after and len(media) < max_posts and budget_left() > 5:
        page = _discovery(username, f"media.after({after}).limit({PAGE_SIZE}){{{_IG_MEDIA_FIELDS}}}")
        chunk = (page.get("media") or {})
        media += chunk.get("data", [])
        after = (chunk.get("paging") or {}).get("cursors", {}).get("after") if chunk.get("data") else None
    profile = {"channel_id": bd["id"], "subscribers": bd.get("followers_count"), "thumbnail": bd.get("profile_picture_url")}
    return profile, [ig_item(m) for m in media[:max_posts] if m.get("permalink") and m.get("timestamp")]


# ---- Facebook Pages ----

def fb_page_ref(text):
    """'facebook.com/nike', 'fb.com/pg/nike', 'facebook.com/profile.php?id=123', '123', 'nike' -> 'nike' or '123'."""
    t = urllib.parse.unquote(text.strip())
    if re.search(r"(facebook|fb)\.com", t, re.IGNORECASE):
        parsed = urllib.parse.urlparse(t if "://" in t else "https://" + t)
        q = urllib.parse.parse_qs(parsed.query)
        if "id" in q:
            return q["id"][0]
        parts = [p for p in parsed.path.split("/") if p and p not in ("pg", "pages", "people")]
        if not parts:
            raise ValueError("That Facebook link doesn't point to a Page. Open the Page and copy its link.")
        # facebook.com/pages/Some-Name/123456 -> the numeric id at the end
        t = next((p for p in reversed(parts) if p.isdigit()), parts[0])
    t = t.lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9.\-]{1,100}", t):
        raise ValueError("Enter the Page's link or its username (the part after facebook.com/).")
    return t


def fb_find(text):
    ref = fb_page_ref(text)
    p = _get(ref, fields="id,name,username,fan_count,followers_count,picture{url},link")
    return {"channel_id": p["id"], "title": p.get("name"), "handle": p.get("username") or p["id"],
            "thumbnail": ((p.get("picture") or {}).get("data") or {}).get("url"),
            "subscribers": p.get("followers_count") or p.get("fan_count")}


_FB_POST_FIELDS = ("id,message,created_time,permalink_url,full_picture,status_type,attachments{media_type},"
                   "shares,reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)")


def fb_format(post):
    media = ((post.get("attachments") or {}).get("data") or [{}])[0].get("media_type", "")
    status = post.get("status_type", "")
    if media == "video" or "video" in status:
        return "video"
    if media == "album":
        return "carousel"
    if media == "photo" or status == "added_photos":
        return "image"
    if media == "link" or status == "shared_story":
        return "link"
    return "text"


def fb_item(post):
    message = post.get("message") or ""
    return {
        "title": _title(message),
        "link": post.get("permalink_url") or f"https://www.facebook.com/{post['id']}",
        "published_at": _when(post["created_time"]),
        "format": fb_format(post),
        "thumbnail": post.get("full_picture"),
        "tags": hashtags(message),
        "views": None,  # video views are private Page Insights
        "likes": ((post.get("reactions") or {}).get("summary") or {}).get("total_count"),  # all reactions
        "comments": ((post.get("comments") or {}).get("summary") or {}).get("total_count"),
        "shares": (post.get("shares") or {}).get("count", 0),
        "duration_seconds": None,
    }


def fb_account(text, max_posts=MAX_POSTS):
    page = fb_find(text)
    data = _get(f"{page['channel_id']}/posts", fields=_FB_POST_FIELDS, limit=PAGE_SIZE)
    posts = list(data.get("data", []))
    nxt = (data.get("paging") or {}).get("next")
    while nxt and len(posts) < max_posts and budget_left() > 5:
        data = _get(None, url=nxt)
        posts += data.get("data", [])
        nxt = (data.get("paging") or {}).get("next") if data.get("data") else None
    profile = {"channel_id": page["channel_id"], "subscribers": page["subscribers"], "thumbnail": page["thumbnail"]}
    return profile, [fb_item(p) for p in posts[:max_posts] if p.get("created_time")]
