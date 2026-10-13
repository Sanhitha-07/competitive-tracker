"""Compare our performance with competitors' per platform, and turn the differences into findings.

Only metrics a platform really exposes are compared (see connectors.py for definitions):
YouTube has views, likes, comments and length; a website feed only has posting activity.
A number that can't be calculated from the data is None (shown as "not available"), never 0.

Works on any objects with these attributes:
  account: id, name, is_us, platform, subscribers
  post:    competitor_id, title, link, published_at, views, likes, comments, duration_seconds, format
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from zoneinfo import ZoneInfo

from connectors import SHORT_MAX_SECONDS, YouTubeConnector

PERF_DAYS = 30            # compare videos from the last 30 days (unless another period is chosen)
MIN_AGE_HOURS = 24        # very new videos haven't collected views yet; leave them out of view averages
MIN_VIDEOS = 5            # below this, findings get a "rough guide" note
DEFAULT_TZ = ZoneInfo("Asia/Kolkata")


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _time_slot(hour):
    if 5 <= hour < 12:
        return "Morning (5 AM–12 PM)"
    if 12 <= hour < 17:
        return "Afternoon (12–5 PM)"
    if 17 <= hour < 22:
        return "Evening (5–10 PM)"
    return "Night (10 PM–5 AM)"


def _format_of(v):
    return getattr(v, "format", None) or YouTubeConnector.classify(False, v.duration_seconds)


def _span_days(videos, now, history_start=None, days=PERF_DAYS):
    """Days the posting rate is measured over. If we have posts older than the period,
    the whole period counts; otherwise only the time since the oldest post we know of."""
    oldest = history_start or min(_utc(v.published_at) for v in videos)
    return max(min((now - _utc(oldest)).total_seconds() / 86400, days), 1)


def engagement_rate(videos):
    """(likes + comments) ÷ views, in %, over videos whose like count is public.
    None when no video has both views and a visible like count (missing is not zero)."""
    rated = [v for v in videos if v.views and v.likes is not None]
    total = sum(v.views for v in rated)
    if not total:
        return None
    return round(sum(v.likes + (v.comments or 0) for v in rated) / total * 100, 2)


def account_stats(videos, now, tz=DEFAULT_TZ, history_start=None, days=PERF_DAYS):
    """Numbers for one account's videos from the last `days` days."""
    if not videos:
        return None
    span_days = _span_days(videos, now, history_start, days)
    mature = [v for v in videos if now - _utc(v.published_at) >= timedelta(hours=MIN_AGE_HOURS)] or videos
    viewed = [v for v in mature if v.views is not None]
    views = [v.views for v in viewed]
    durations = [v.duration_seconds for v in videos if v.duration_seconds]
    shorts = [d for d in durations if d <= SHORT_MAX_SECONDS]

    by_slot = defaultdict(list)
    for v in viewed:
        by_slot[_time_slot(_utc(v.published_at).astimezone(tz).hour)].append(v.views)
    best_slot = max(by_slot, key=lambda s: median(by_slot[s])) if by_slot else None

    by_format = defaultdict(list)
    for v in viewed:
        by_format[_format_of(v)].append(v)
    formats = {f: {"videos": len(vs), "median_views": round(median(v.views for v in vs)),
                   "engagement_rate": engagement_rate(vs)}
               for f, vs in by_format.items()}

    return {
        "videos": len(videos),
        "mature_videos": len(mature),
        "per_week": round(len(videos) / span_days * 7, 1),
        "avg_views": round(mean(views)) if views else None,
        "median_views": round(median(views)) if views else None,
        "engagement_rate": engagement_rate(viewed),
        "avg_length_seconds": round(mean(durations)) if durations else None,
        "shorts_pct": round(len(shorts) / len(durations) * 100) if durations else None,
        "best_time": best_slot,
        "best_time_sample": len(by_slot.get(best_slot, [])) if best_slot else 0,
        "formats": formats,
    }


def _market(rows):
    """Average of the competitors' numbers (each competitor counts once, whatever its size).
    An unknown value is left out of the average, not counted as 0."""
    keys = ["videos", "per_week", "avg_views", "median_views", "engagement_rate", "avg_length_seconds", "shorts_pct"]
    if not rows:
        return None
    m = {}
    for k in keys:
        vals = [r[k] for r in rows if r[k] is not None]
        m[k] = round(mean(vals), 2 if k in ("engagement_rate", "per_week") else None) if vals else None
    m["accounts"] = len(rows)
    m["total_videos"] = sum(r["videos"] for r in rows)
    slots = Counter(r["best_time"] for r in rows if r["best_time"])
    m["best_time"] = slots.most_common(1)[0][0] if slots else None
    return m


def _pct_diff(ours, theirs):
    """% difference, or None when either side is unknown (so no finding is made from it)."""
    if ours is None or not theirs:
        return None
    return round((ours - theirs) / theirs * 100)


def suggestions(us, market, gaps_count=0):
    """Plain-language findings. tone: 'lagging' (do better), 'good' (keep going), 'info'.
    Each one also says which metric it is based on, so it can be shown with its evidence."""
    if not us or not market:
        return []
    out = []

    def add(tone, title, detail, metric=None, ours=None, theirs=None, kind="benchmark"):
        out.append({"tone": tone, "title": title, "detail": detail, "metric": metric,
                    "ours": ours, "theirs": theirs, "kind": kind})

    d = _pct_diff(us["per_week"], market["per_week"])
    if d is not None and d <= -30:
        add("lagging", "Post more often",
            f"You publish {us['per_week']} videos a week; competitors average {market['per_week']}. "
            "Posting more doesn't guarantee more views: test it and compare with your own baseline.",
            "per_week", us["per_week"], market["per_week"], "publishing_pattern")
    elif d is not None and d >= 30:
        add("good", "You post more often than competitors",
            f"{us['per_week']} videos a week vs the market's {market['per_week']}. Make sure quality keeps up with the volume.",
            "per_week", us["per_week"], market["per_week"], "publishing_pattern")

    # Median = the typical video, so one viral video doesn't distort the comparison.
    d = _pct_diff(us["median_views"], market["median_views"])
    if d is not None and d <= -20:
        add("lagging", "Your videos get fewer views",
            f"Your typical video gets {us['median_views']:,} views vs {market['median_views']:,} for competitors ({d}%). "
            "Channel size explains much of this, so also compare each post with its own channel's usual.",
            "median_views", us["median_views"], market["median_views"])
    elif d is not None and d >= 20:
        add("good", "Your views are above the market",
            f"Your typical video gets {us['median_views']:,} views vs {market['median_views']:,} for competitors (+{d}%).",
            "median_views", us["median_views"], market["median_views"])

    d = _pct_diff(us["engagement_rate"], market["engagement_rate"])
    if d is not None and d <= -20:
        add("lagging", "Engagement is low",
            f"Likes + comments are {us['engagement_rate']}% of your views vs {market['engagement_rate']}% for competitors (public counts only).",
            "engagement_rate", us["engagement_rate"], market["engagement_rate"])
    elif d is not None and d >= 20:
        add("good", "Strong engagement",
            f"{us['engagement_rate']}% engagement vs the market's {market['engagement_rate']}%. Your audience is more active than competitors'.",
            "engagement_rate", us["engagement_rate"], market["engagement_rate"])

    d = _pct_diff(us["avg_length_seconds"], market["avg_length_seconds"])
    slower = us["median_views"] is not None and market["median_views"] is not None and us["median_views"] < market["median_views"]
    if d is not None and d >= 30 and slower:
        add("lagging", "Try shorter videos",
            f"Your videos average {_fmt_len(us['avg_length_seconds'])}; competitors' average {_fmt_len(market['avg_length_seconds'])} and get more views.",
            "avg_length_seconds", us["avg_length_seconds"], market["avg_length_seconds"], "format_test")
    elif d is not None and d <= -30 and slower:
        add("info", "Competitors make longer videos",
            f"Their videos average {_fmt_len(market['avg_length_seconds'])} vs your {_fmt_len(us['avg_length_seconds'])}. Test a few longer, in-depth videos.",
            "avg_length_seconds", us["avg_length_seconds"], market["avg_length_seconds"], "format_test")

    if us["shorts_pct"] is not None and market["shorts_pct"] is not None:
        gap = market["shorts_pct"] - us["shorts_pct"]
        if gap >= 15:
            add("lagging", "Add more Shorts",
                f"{market['shorts_pct']}% of competitors' videos are Shorts vs {us['shorts_pct']}% of yours.",
                "shorts_pct", us["shorts_pct"], market["shorts_pct"], "format_test")
        elif gap <= -15:
            add("info", "You rely more on Shorts",
                f"{us['shorts_pct']}% of your videos are Shorts vs {market['shorts_pct']}% for competitors. Make sure long videos still get attention.",
                "shorts_pct", us["shorts_pct"], market["shorts_pct"], "format_test")

    if market["best_time"] and us["best_time"] and market["best_time"] != us["best_time"]:
        add("info", "Test a different posting time",
            f"Competitors' best-performing videos go out in the {market['best_time']} slot. Yours do best in the {us['best_time']} slot. Try a few uploads in their slot.",
            "best_time", us["best_time"], market["best_time"], "publishing_pattern")

    if gaps_count:
        add("lagging", f"{gaps_count} topic{'s' if gaps_count != 1 else ''} you haven't covered",
            "Several competitors covered these and you didn't. See the Coverage Gaps tab.",
            kind="topic_gap")

    if not any(s["tone"] == "lagging" for s in out):
        add("good", "No major gaps found", "You're level with or ahead of competitors on the main numbers.", kind="status")
    if us["videos"] < MIN_VIDEOS or market["videos"] < MIN_VIDEOS:
        add("info", "Based on few videos",
            f"You or your competitors posted fewer than {MIN_VIDEOS} videos in this period, so treat these numbers as a rough guide.",
            kind="status")
    return out


def _fmt_len(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _history_start(posts):
    start = {}
    for p in posts:
        t = _utc(p.published_at)
        if p.competitor_id not in start or t < start[p.competitor_id]:
            start[p.competitor_id] = t
    return start


def posting_stats(accounts, posts, now, days=PERF_DAYS):
    """Posting activity for platforms without audience numbers (e.g. website feeds)."""
    since = now - timedelta(days=days)
    start = _history_start(posts)
    rows = []
    for a in accounts:
        mine = [p for p in posts if p.competitor_id == a.id and _utc(p.published_at) >= since]
        per_week = round(len(mine) / _span_days(mine, now, start.get(a.id), days) * 7, 1) if mine else 0
        rows.append({"id": a.id, "name": a.name, "is_us": a.is_us, "posts": len(mine), "per_week": per_week})
    return sorted(rows, key=lambda r: (not r["is_us"], r["name"]))


def compare(accounts, posts, gaps_count=0, now=None, tz=DEFAULT_TZ, days=PERF_DAYS):
    """Full comparison for one organization: YouTube in detail, other platforms by posting activity."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    yt_accounts = [a for a in accounts if a.platform == "youtube"]
    start = _history_start(posts)
    by_account = defaultdict(list)
    for p in posts:
        if p.views is not None and _utc(p.published_at) >= since:
            by_account[p.competitor_id].append(p)

    rows = []
    for a in yt_accounts:
        stats = account_stats(by_account.get(a.id, []), now, tz, start.get(a.id), days)
        rows.append({"id": a.id, "name": a.name, "is_us": a.is_us, "subscribers": a.subscribers, "stats": stats})

    our_rows = [r["stats"] for r in rows if r["is_us"] and r["stats"]]
    us = our_rows[0] if our_rows else None
    market = _market([r["stats"] for r in rows if not r["is_us"] and r["stats"]])

    names = {a.id: a.name for a in yt_accounts}
    competitor_ids = {a.id for a in yt_accounts if not a.is_us}
    top = sorted(
        (p for cid in competitor_ids for p in by_account.get(cid, [])
         if now - _utc(p.published_at) >= timedelta(hours=MIN_AGE_HOURS)),
        key=lambda p: p.views, reverse=True,
    )[:5]

    other = defaultdict(list)
    for a in accounts:
        if a.platform != "youtube":
            other[a.platform].append(a)

    return {
        "days": days,
        "accounts": sorted(rows, key=lambda r: (not r["is_us"], r["name"])),
        "us": us,
        "market": market,
        "top_competitor_videos": [
            {"account": names[p.competitor_id], "title": p.title, "link": p.link, "views": p.views,
             "published_at": _utc(p.published_at).isoformat(), "length_seconds": p.duration_seconds,
             "thumbnail": getattr(p, "thumbnail", None)}
            for p in top
        ],
        "other_platforms": {
            platform: posting_stats(accs, [p for p in posts if p.competitor_id in {a.id for a in accs}], now, days)
            for platform, accs in other.items()
        },
        "suggestions": suggestions(us, market, gaps_count),
    }
