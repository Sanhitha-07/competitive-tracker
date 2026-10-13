"""Platform connectors: everything platform-specific lives here.

Each connector knows how to check an account, read its posts, and which public metrics
the platform really exposes (with definitions). Analysis code only uses the normalized
fields below, so adding a platform (e.g. Instagram once Meta app review is done) means
adding one connector, not changing the analysis.

Normalized item: title, link, published_at (UTC), format, thumbnail, tags,
                 views, likes, comments, duration_seconds (None when not available)
"""
import calendar
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser

import meta_api
import social_http as http
import x_api
import youtube

SHORT_MAX_SECONDS = 60       # see the "short" format definition below
LONG_MIN_SECONDS = 20 * 60

# Shared metric vocabulary. A connector lists the ones it supports and may refine the definition.
METRICS = {
    "posts": "Number of posts/videos published in the period.",
    "per_week": "Posts per week = posts in the period ÷ days covered × 7.",
    "views": "Public view count reported by the platform at the time of the last refresh.",
    "median_views": "The middle view count of posts older than 24 hours, so one viral post doesn't distort it.",
    "likes": "Public like count. Some creators hide it; hidden counts are left out, not counted as zero.",
    "comments": "Public comment count. Zero when comments are turned off.",
    "engagement_rate": "(likes + comments) ÷ views × 100, over posts older than 24 hours. Not comparable with platforms that use followers or reach as the denominator.",
    "relative_performance": "A post's views ÷ the median views of the same account's other posts in the period. 2.0× means twice that account's usual. Compares an account with itself, so big and small accounts can be compared fairly.",
    "subscribers": "Public subscriber count. YouTube rounds it (to 3 significant figures), so small changes may not show.",
    "duration": "Video length.",
}


class YouTubeConnector:
    id = "youtube"
    label = "YouTube"
    source_label = "YouTube channel (name, @handle or link)"
    metrics = ["posts", "per_week", "views", "median_views", "likes", "comments",
               "engagement_rate", "relative_performance", "subscribers", "duration"]
    formats = {
        "short": f"Video of {SHORT_MAX_SECONDS}s or less. Approximate: the API doesn't say whether a video is a Short, and Shorts can be up to 3 minutes.",
        "video": "Uploaded video between 1 and 20 minutes.",
        "long": "Uploaded video of 20 minutes or more.",
        "live": "A finished live stream (the API marks videos that were broadcast live).",
    }
    supports_questions = True
    quota_note = "Uses the YouTube Data API daily quota (≈5 units per channel per refresh, 1 per comment check)."

    def resolve(self, source, ctx=None):
        ch = youtube.find_channel(source)
        return {"channel_id": ch["channel_id"], "subscribers": ch["subscribers"], "thumbnail": ch["thumbnail"]}

    def fetch(self, account, ctx=None):
        ch = youtube.find_channel(account.channel_id or account.source)
        account.channel_id, account.subscribers, account.thumbnail = ch["channel_id"], ch["subscribers"], ch["thumbnail"]
        items = []
        for v in youtube.latest_videos(ch["uploads_playlist"]):
            v["format"] = self.classify(v.pop("was_live", False), v.get("duration_seconds"))
            items.append(v)
        return items

    @staticmethod
    def classify(was_live, seconds):
        if was_live:
            return "live"
        if seconds and seconds <= SHORT_MAX_SECONDS:
            return "short"
        if seconds and seconds >= LONG_MIN_SECONDS:
            return "long"
        return "video"

    def questions(self, post):
        vid = youtube.video_id(post.link)
        if not vid:
            return []
        try:
            return youtube.comment_questions(vid)
        except youtube.CommentsDisabled:
            return []


class RSSConnector:
    id = "rss"
    label = "Website / blog (RSS)"
    source_label = "RSS link"
    metrics = ["posts", "per_week"]  # feeds expose no audience numbers
    formats = {"article": "An item in the site's RSS feed (article, blog post or episode)."}
    supports_questions = False
    quota_note = None

    def resolve(self, source, ctx=None):
        if not source.lower().startswith(("http://", "https://")):
            raise ValueError("The RSS link must start with http:// or https://")
        return {}

    def fetch(self, account, ctx=None):
        feed = feedparser.parse(account.source, agent="Mozilla/5.0 CompetitiveTracker")
        if not feed.entries:
            reason = getattr(feed, "bozo_exception", None)
            raise ValueError(f"No stories found. Is this an RSS feed link? {reason or ''}".strip())
        items = []
        for e in feed.entries:
            if not e.get("title") or not e.get("link"):
                continue
            t = e.get("published_parsed") or e.get("updated_parsed")
            # Always UTC, with timezone info (the database requires it).
            when = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc) if t else datetime.now(timezone.utc)
            thumb = None
            for m in (e.get("media_thumbnail") or e.get("media_content") or []):
                if m.get("url"):
                    thumb = m["url"]
                    break
            tags = [t.get("term", "").strip() for t in e.get("tags", []) if t.get("term")][:15]
            items.append({"title": e.title.strip(), "link": e.link, "published_at": when,
                          "format": "article", "thumbnail": thumb, "tags": tags})
        return items

    def questions(self, post):
        return []


METRICS.update({
    "shares": "Public share count (Facebook shares, X reposts). Left out where the platform doesn't report it.",
    "x_views": "Views X shows on a post (impressions). Not comparable with YouTube views.",
})


def _clean_caption(text, fallback):
    """A post's first line, as its title (social posts have captions, not titles)."""
    first = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    return (first[:150] + "…") if len(first) > 150 else (first or fallback)


def _hashtags(text):
    return list(dict.fromkeys(t.lstrip("#") for t in re.findall(r"#\w+", text or "")))[:15]


def _utc_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace("+0000", "+00:00")).astimezone(timezone.utc)


class SocialConnector:
    """Shared rules for platforms that need a signed-in connection (Instagram, Facebook, X).

    resolve(): without a usable connection the account is saved as Unverified (no API call is made);
               with one, the platform confirms the profile exists and gives its id.
    fetch():   needs a connection; the fetcher skips the platform when there isn't one.
    """
    requires_connection = True
    supports_questions = False
    handle_pattern = None
    url_hosts = ()

    def parse(self, source):
        """A handle from '@name', 'name' or a profile link; raises ValueError if it can't be one."""
        s = (source or "").strip()
        if re.match(r"^https?://", s, re.I):
            u = urlparse(s)
            host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
            if host not in self.url_hosts:
                raise ValueError(f"That isn't a {self.label} link.")
            if host.startswith("facebook") and u.path.rstrip("/") == "/profile.php":
                s = dict(p.split("=", 1) for p in u.query.split("&") if "=" in p).get("id", "")
            else:
                s = (u.path.strip("/").split("/") or [""])[0]
        s = s.lstrip("@")
        if not s or not re.fullmatch(self.handle_pattern, s):
            raise ValueError(f"Enter a {self.label} {self.handle_word} or a link to the profile.")
        return s

    def questions(self, post):
        return []

    def _unverified(self, handle):
        return {"source": handle, "verified": False}


class InstagramConnector(SocialConnector):
    id = "instagram"
    label = "Instagram"
    source_label = "Instagram username or profile link"
    handle_word = "username"
    handle_pattern = r"[A-Za-z0-9._]{1,30}"
    url_hosts = ("instagram.com",)
    metrics = ["posts", "per_week", "likes", "comments"]
    formats = {"reel": "An Instagram Reel.", "image": "A single photo post.",
               "carousel": "A post with several photos or videos.", "video": "A video in the feed."}
    quota_note = "Uses the Meta Graph API (rate-limited per app and per account)."

    def profile_url(self, account):
        return f"https://www.instagram.com/{account.source}/"

    def resolve(self, source, ctx=None):
        handle = self.parse(source)
        if not ctx:
            return self._unverified(handle)
        return self._profile(meta_api.ig_profile(ctx.token, ctx.own_id, handle), handle)

    @staticmethod
    def _profile(profile, handle):
        return {"source": profile.get("username") or handle, "verified": True, "external_id": profile["id"],
                "thumbnail": profile.get("profile_picture_url"), "subscribers": profile.get("followers_count"),
                "display_name": profile.get("name") or profile.get("username") or handle}

    def suggest(self, query, ctx):
        """Instagram has no name search: look up this exact username (public professional accounts only)."""
        try:
            handle = self.parse(query)
        except ValueError:
            return "exact", []
        try:
            return "exact", [self._profile(meta_api.ig_profile(ctx.token, ctx.own_id, handle), handle)]
        except http.ApiError as exc:
            if isinstance(exc, (http.TokenInvalid, http.RateLimited)):
                raise
            return "exact", []  # not found, private, or not a professional account

    def fetch(self, account, ctx=None):
        if ctx is None:
            raise ValueError("Instagram isn't connected.")
        if account.is_us and ctx.own_id and account.external_id == ctx.own_id:
            profile, media = meta_api.ig_own(ctx.token, ctx.own_id)
        else:
            profile, media = meta_api.ig_discovery(ctx.token, ctx.own_id, account.source)
        account.external_id, account.verified = profile.get("id"), True
        account.subscribers = profile.get("followers_count", account.subscribers)
        account.thumbnail = profile.get("profile_picture_url") or account.thumbnail
        return [self._item(m) for m in media if m.get("permalink") and m.get("timestamp")]

    @staticmethod
    def _item(m):
        product, kind = m.get("media_product_type"), m.get("media_type")
        fmt = "reel" if product == "REELS" else {"CAROUSEL_ALBUM": "carousel", "VIDEO": "video"}.get(kind, "image")
        return {"title": _clean_caption(m.get("caption"), "(post without caption)"), "link": m["permalink"],
                "published_at": _utc_time(m["timestamp"]), "format": fmt,
                "thumbnail": m.get("thumbnail_url") or (m.get("media_url") if kind == "IMAGE" else None),
                "tags": _hashtags(m.get("caption")), "views": None,
                "likes": m.get("like_count"),  # missing when the account hides like counts: stays None
                "comments": m.get("comments_count")}


class FacebookConnector(SocialConnector):
    id = "facebook"
    label = "Facebook"
    source_label = "Facebook Page name or link"
    handle_word = "Page name"
    handle_pattern = r"[A-Za-z0-9.\-]{1,100}"
    url_hosts = ("facebook.com", "fb.com")
    metrics = ["posts", "per_week", "likes", "comments", "shares"]
    formats = {"post": "A text or link post.", "image": "A photo post.", "video": "A video post.",
               "carousel": "A post with several photos."}
    quota_note = "Uses the Meta Graph API. Competitor Pages need Meta's Page Public Content Access feature."

    def profile_url(self, account):
        return f"https://www.facebook.com/{account.source}"

    def resolve(self, source, ctx=None):
        handle = self.parse(source)
        if not ctx:
            return self._unverified(handle)
        try:
            page = meta_api.page_profile(ctx.page_token if handle == ctx.own_id else ctx.token, handle)
        except http.NotPermitted:
            # Other Pages need Page Public Content Access; keep the account, unverified.
            return {**self._unverified(handle), "note": "Reading other Pages needs Meta's Page Public Content Access feature."}
        return self._profile(page)

    @staticmethod
    def _profile(page):
        return {"source": page.get("username") or page["id"], "verified": True, "external_id": page["id"],
                "thumbnail": ((page.get("picture") or {}).get("data") or {}).get("url"),
                "subscribers": page.get("followers_count") or page.get("fan_count"), "display_name": page.get("name")}

    def suggest(self, query, ctx):
        """Exact Page lookup. Pages you don't manage need Page Public Content Access (NotPermitted otherwise)."""
        try:
            handle = self.parse(query)
        except ValueError:
            return "exact", []
        try:
            return "exact", [self._profile(meta_api.page_profile(ctx.page_token if handle == ctx.own_id else ctx.token, handle))]
        except http.ApiError as exc:
            if isinstance(exc, (http.TokenInvalid, http.RateLimited, http.NotPermitted)):
                raise
            return "exact", []

    def fetch(self, account, ctx=None):
        if ctx is None:
            raise ValueError("Facebook isn't connected.")
        ours = bool(ctx.own_id) and account.external_id == ctx.own_id
        token = ctx.page_token if ours else ctx.token
        if not account.external_id or account.verified is False:
            info = self.resolve(account.source, ctx)
            if not info.get("verified"):
                raise http.NotPermitted(info.get("note") or "This Page can't be read yet.")
            account.external_id, account.verified = info["external_id"], True
            account.thumbnail, account.subscribers = info.get("thumbnail"), info.get("subscribers")
        return [self._item(p) for p in meta_api.page_posts(token, account.external_id)
                if p.get("permalink_url") and p.get("created_time")]

    @staticmethod
    def _item(p):
        kind = (((p.get("attachments") or {}).get("data") or [{}])[0].get("media_type") or "").lower()
        fmt = {"photo": "image", "video": "video", "album": "carousel"}.get(kind, "post")
        return {"title": _clean_caption(p.get("message"), "(post without text)"), "link": p["permalink_url"],
                "published_at": _utc_time(p["created_time"]), "format": fmt, "thumbnail": p.get("full_picture"),
                "tags": _hashtags(p.get("message")), "views": None,
                "likes": ((p.get("reactions") or {}).get("summary") or {}).get("total_count"),
                "comments": ((p.get("comments") or {}).get("summary") or {}).get("total_count"),
                "shares": (p.get("shares") or {}).get("count", 0 if "shares" in p else None)}


class XConnector(SocialConnector):
    id = "x"
    label = "X"
    source_label = "X username or profile link"
    handle_word = "username"
    handle_pattern = r"[A-Za-z0-9_]{1,15}"
    url_hosts = ("x.com", "twitter.com")
    metrics = ["posts", "per_week", "x_views", "likes", "comments", "shares"]
    formats = {"post": "A text or link post.", "image": "A post with photos.", "video": "A post with a video."}
    quota_note = "X API is pay-per-use: each post read and profile lookup is billed from your X API credits."

    def profile_url(self, account):
        return f"https://x.com/{account.source}"

    def resolve(self, source, ctx=None):
        handle = self.parse(source)
        if not ctx:
            return self._unverified(handle)
        return self._profile(x_api.user_by_username(ctx.token, handle))

    @staticmethod
    def _profile(user):
        return {"source": user["username"], "verified": True, "external_id": user["id"],
                "thumbnail": user.get("profile_image_url"), "display_name": user.get("name") or user["username"],
                "subscribers": (user.get("public_metrics") or {}).get("followers_count")}

    def suggest(self, query, ctx):
        """Real search where the X plan allows it (Pro and higher); otherwise an exact username lookup."""
        try:
            return "search", [self._profile(u) for u in x_api.search_users(ctx.token, query.strip().lstrip("@"))]
        except http.NotPermitted:
            pass
        try:
            handle = self.parse(query)
        except ValueError:
            return "exact", []
        try:
            return "exact", [self._profile(x_api.user_by_username(ctx.token, handle))]
        except http.ApiError as exc:
            if isinstance(exc, (http.TokenInvalid, http.RateLimited, http.NotPermitted)):
                raise
            return "exact", []

    def fetch(self, account, ctx=None):
        if ctx is None:
            raise ValueError("X isn't connected.")
        if not account.external_id:
            info = self.resolve(account.source, ctx)
            account.external_id, account.verified = info["external_id"], True
            account.thumbnail, account.subscribers = info.get("thumbnail"), info.get("subscribers")
        posts, media = x_api.user_posts(ctx.token, account.external_id)
        return [self._item(t, media, account.source) for t in posts]

    @staticmethod
    def _item(t, media, username):
        m = t.get("public_metrics") or {}
        types = [media[k]["type"] for k in (t.get("attachments") or {}).get("media_keys", []) if k in media]
        fmt = "video" if any(x in ("video", "animated_gif") for x in types) else "image" if types else "post"
        thumb = next((media[k].get("preview_image_url") or media[k].get("url")
                      for k in (t.get("attachments") or {}).get("media_keys", []) if k in media), None)
        return {"title": _clean_caption(t.get("text"), "(post)"), "link": f"https://x.com/{username}/status/{t['id']}",
                "published_at": _utc_time(t["created_at"]), "format": fmt, "thumbnail": thumb,
                "tags": [h["tag"] for h in (t.get("entities") or {}).get("hashtags", [])][:15],
                "views": m.get("impression_count"), "likes": m.get("like_count"),
                "comments": m.get("reply_count"), "shares": m.get("retweet_count")}


CONNECTORS = {c.id: c for c in (YouTubeConnector(), RSSConnector(), InstagramConnector(), FacebookConnector(), XConnector())}

# Platforms people ask for that aren't connected yet, and why. Shown in workspace settings.
PLANNED = {
    "tiktok": "Needs TikTok Research/Display API approval.",
    "twitch": "Possible via Twitch Helix API (streams, VODs); not built yet.",
    "linkedin": "No public API for competitor pages.",
}
PLANNED_LABELS = {"tiktok": "TikTok", "twitch": "Twitch", "linkedin": "LinkedIn"}


def get(platform):
    try:
        return CONNECTORS[platform]
    except KeyError:
        raise ValueError(f'Platform "{platform}" is not supported yet.') from None


def describe():
    """Platform capabilities for the UI: which metrics and formats exist, with definitions."""
    return {
        "supported": [
            {"id": c.id, "label": c.label, "source_label": c.source_label,
             "metrics": {m: METRICS[m] for m in c.metrics}, "formats": c.formats,
             "questions": c.supports_questions, "quota_note": c.quota_note,
             "requires_connection": getattr(c, "requires_connection", False)}
            for c in CONNECTORS.values()
        ],
        "planned": [{"id": k, "label": PLANNED_LABELS[k], "reason": v} for k, v in PLANNED.items()],
    }
