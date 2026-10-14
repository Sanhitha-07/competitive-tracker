"""Platform connectors: everything platform-specific lives here.

Each connector knows how to check an account, read its posts, and which public metrics
the platform really exposes (with definitions). Analysis code only uses the normalized
fields below, so adding a platform means adding one connector, not changing the analysis.

Normalized item: title, link, published_at (UTC), format, thumbnail, tags,
                 views, likes, comments, shares, duration_seconds (None when not available)

Each connector also names its performance metric: the number that "how well did this post do"
is measured with. YouTube uses views; Instagram and Facebook use interactions, because
competitors' views/reach aren't public there (Instagram only shows views for Reels).
"""
import calendar
from datetime import datetime, timezone

import feedparser

import meta
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
    "followers": "Public follower count at the time of the last refresh.",
    "interactions": "Likes + comments (+ shares where public) on a post. Used to measure posts where views aren't public.",
    "median_interactions": "The middle interaction count of posts older than 24 hours, so one viral post doesn't distort it.",
    "engagement_per_follower": "Interactions on a post ÷ the account's followers × 100, averaged over posts older than 24 hours. Standard for Instagram and Facebook; not comparable with YouTube's per-view rate.",
    "shares": "Public share count (Facebook only).",
    "reel_views": "Views on Reels. Instagram doesn't show views for photos or carousels.",
}


class YouTubeConnector:
    id = "youtube"
    label = "YouTube"
    source_label = "YouTube channel (name, @handle or link)"
    performance_metric = "views"
    audience_label = "subscribers"
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

    def resolve(self, source):
        ch = youtube.find_channel(source)
        return {"channel_id": ch["channel_id"], "subscribers": ch["subscribers"], "thumbnail": ch["thumbnail"]}

    def fetch(self, account):
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
    performance_metric = None
    audience_label = None
    metrics = ["posts", "per_week"]  # feeds expose no audience numbers
    formats = {"article": "An item in the site's RSS feed (article, blog post or episode)."}
    supports_questions = False
    quota_note = None

    def resolve(self, source):
        if not source.lower().startswith(("http://", "https://")):
            raise ValueError("The RSS link must start with http:// or https://")
        return {}

    def fetch(self, account):
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


class InstagramConnector:
    id = "instagram"
    label = "Instagram"
    source_label = "Instagram account (@username or profile link)"
    performance_metric = "interactions"
    audience_label = "followers"
    metrics = ["posts", "per_week", "likes", "comments", "interactions", "median_interactions",
               "engagement_per_follower", "relative_performance", "followers", "reel_views"]
    formats = {
        "reel": "A Reel (short vertical video).",
        "image": "A single photo post.",
        "carousel": "A carousel: several photos or videos in one post.",
        "video": "A video post that isn't a Reel.",
    }
    supports_questions = False
    quota_note = ("Uses the Meta Graph API through your own Instagram professional account (Business Discovery). "
                  "Only Business and Creator accounts can be read; about 1–2 calls per account per refresh.")

    def resolve(self, source):
        ch = meta.ig_find(source)
        return {"channel_id": ch["channel_id"], "subscribers": ch["subscribers"], "thumbnail": ch["thumbnail"],
                "source": ch["handle"]}

    def fetch(self, account):
        profile, items = meta.ig_account(account.source)
        account.channel_id, account.subscribers, account.thumbnail = profile["channel_id"], profile["subscribers"], profile["thumbnail"]
        return items

    def questions(self, post):
        return []


class FacebookConnector:
    id = "facebook"
    label = "Facebook Page"
    source_label = "Facebook Page (link or username)"
    performance_metric = "interactions"
    audience_label = "followers"
    metrics = ["posts", "per_week", "likes", "comments", "shares", "interactions", "median_interactions",
               "engagement_per_follower", "relative_performance", "followers"]
    formats = {
        "video": "A video or Reel posted on the Page.",
        "image": "A photo post.",
        "carousel": "An album of several photos.",
        "link": "A post sharing a link (article, website).",
        "text": "A text-only status update.",
    }
    supports_questions = False
    quota_note = ("Uses the Meta Graph API. Pages you don't manage need the Page Public Content Access feature "
                  "(Meta App Review). Reactions are counted as likes. About 2–3 calls per Page per refresh.")

    def resolve(self, source):
        ch = meta.fb_find(source)
        return {"channel_id": ch["channel_id"], "subscribers": ch["subscribers"], "thumbnail": ch["thumbnail"]}

    def fetch(self, account):
        profile, items = meta.fb_account(account.channel_id or account.source)
        account.channel_id, account.subscribers, account.thumbnail = profile["channel_id"], profile["subscribers"], profile["thumbnail"]
        return items

    def questions(self, post):
        return []


CONNECTORS = {c.id: c for c in (YouTubeConnector(), InstagramConnector(), FacebookConnector(), RSSConnector())}

# Platforms people ask for that aren't connected yet, and why. Shown in workspace settings.
PLANNED = {
    "tiktok": "Needs TikTok Research/Display API approval.",
    "twitch": "Possible via Twitch Helix API (streams, VODs); not built yet.",
    "x": "Paid API tier required.",
    "linkedin": "No public API for competitor pages.",
}
PLANNED_LABELS = {"tiktok": "TikTok", "twitch": "Twitch", "x": "X", "linkedin": "LinkedIn"}


def performance_metric(platform):
    c = CONNECTORS.get(platform)
    return c.performance_metric if c else None


def audience_label(platform):
    c = CONNECTORS.get(platform)
    return getattr(c, "audience_label", None) if c else None


def interactions(post):
    """Likes + comments + shares that the platform exposes; None if it exposes none of them."""
    parts = [getattr(post, f, None) for f in ("likes", "comments", "shares")]
    known = [x for x in parts if x is not None]
    return sum(known) if known else None


def metric_value(post):
    """The number a post's performance is measured with on its platform (see performance_metric)."""
    m = performance_metric(getattr(post, "platform", None) or "youtube")
    if m == "views":
        return post.views
    if m == "interactions":
        return interactions(post)
    return None


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
             "performance_metric": c.performance_metric, "audience_label": c.audience_label}
            for c in CONNECTORS.values()
        ],
        "planned": [{"id": k, "label": PLANNED_LABELS[k], "reason": v} for k, v in PLANNED.items()],
    }
