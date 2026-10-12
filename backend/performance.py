"""Compare our YouTube performance with competitors' and turn the differences into suggestions.

Works on any objects with these attributes:
  account: id, name, is_us, platform, subscribers
  post:    competitor_id, title, link, published_at, views, likes, comments, duration_seconds
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, median

PERF_DAYS = 30            # compare videos from the last 30 days
MIN_AGE_HOURS = 24        # very new videos haven't collected views yet; leave them out of view averages
SHORT_MAX_SECONDS = 60    # treated as a Short (approximate: the API doesn't say if a video is a Short)
MIN_VIDEOS = 5            # below this, suggestions get a "rough guide" note
IST = timezone(timedelta(hours=5, minutes=30))


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


def account_stats(videos, now):
    """Numbers for one account's videos from the last PERF_DAYS days."""
    if not videos:
        return None
    oldest = min(_utc(v.published_at) for v in videos)
    span_days = max((now - oldest).total_seconds() / 86400, 1)
    mature = [v for v in videos if now - _utc(v.published_at) >= timedelta(hours=MIN_AGE_HOURS)] or videos
    views = [v.views or 0 for v in mature]
    total_views = sum(views)
    interactions = sum((v.likes or 0) + (v.comments or 0) for v in mature)
    durations = [v.duration_seconds for v in videos if v.duration_seconds]
    shorts = [v for v in videos if v.duration_seconds and v.duration_seconds <= SHORT_MAX_SECONDS]

    by_slot = defaultdict(list)
    for v in mature:
        by_slot[_time_slot(_utc(v.published_at).astimezone(IST).hour)].append(v.views or 0)
    best_slot = max(by_slot, key=lambda s: mean(by_slot[s])) if by_slot else None

    return {
        "videos": len(videos),
        "per_week": round(len(videos) / span_days * 7, 1),
        "avg_views": round(mean(views)) if views else 0,
        "median_views": round(median(views)) if views else 0,
        "engagement_rate": round(interactions / total_views * 100, 2) if total_views else 0.0,
        "avg_length_seconds": round(mean(durations)) if durations else 0,
        "shorts_pct": round(len(shorts) / len(videos) * 100),
        "best_time": best_slot,
    }


def _market(rows):
    """Average of the competitors' numbers."""
    keys = ["videos", "per_week", "avg_views", "median_views", "engagement_rate", "avg_length_seconds", "shorts_pct"]
    if not rows:
        return None
    m = {k: round(mean(r[k] for r in rows), 2 if k in ("engagement_rate", "per_week") else 0) for k in keys}
    for k in ("videos", "avg_views", "median_views", "avg_length_seconds", "shorts_pct"):
        m[k] = int(m[k])
    slots = Counter(r["best_time"] for r in rows if r["best_time"])
    m["best_time"] = slots.most_common(1)[0][0] if slots else None
    return m


def _pct_diff(ours, theirs):
    return round((ours - theirs) / theirs * 100) if theirs else 0


def suggestions(us, market, gaps_count=0):
    """Plain-language findings. tone: 'lagging' (do better), 'good' (keep going), 'info'."""
    if not us or not market:
        return []
    out = []

    def add(tone, title, detail):
        out.append({"tone": tone, "title": title, "detail": detail})

    d = _pct_diff(us["per_week"], market["per_week"])
    if d <= -30:
        add("lagging", "Post more often",
            f"You publish {us['per_week']} videos a week; competitors average {market['per_week']}. Aim for at least {round(market['per_week'] * 0.8, 1)} a week.")
    elif d >= 30:
        add("good", "You post more often than competitors",
            f"{us['per_week']} videos a week vs the market's {market['per_week']}. Make sure quality keeps up with the volume.")

    # Median = the typical video, so one viral video doesn't distort the comparison.
    d = _pct_diff(us["median_views"], market["median_views"])
    if d <= -20:
        add("lagging", "Your videos get fewer views",
            f"Your typical video gets {us['median_views']:,} views vs {market['median_views']:,} for competitors ({d}%). Study their top videos for titles and thumbnails.")
    elif d >= 20:
        add("good", "Your views are above the market",
            f"Your typical video gets {us['median_views']:,} views vs {market['median_views']:,} for competitors (+{d}%).")

    d = _pct_diff(us["engagement_rate"], market["engagement_rate"])
    if d <= -20:
        add("lagging", "Engagement is low",
            f"{us['engagement_rate']}% of viewers like or comment vs {market['engagement_rate']}% for competitors. Ask a question in the video and pin a comment to start discussion.")
    elif d >= 20:
        add("good", "Strong engagement",
            f"{us['engagement_rate']}% engagement vs the market's {market['engagement_rate']}%. Your audience is more active than competitors'.")

    if us["avg_length_seconds"] and market["avg_length_seconds"]:
        d = _pct_diff(us["avg_length_seconds"], market["avg_length_seconds"])
        if d >= 30 and us["median_views"] < market["median_views"]:
            add("lagging", "Try shorter videos",
                f"Your videos average {_fmt_len(us['avg_length_seconds'])}; competitors' average {_fmt_len(market['avg_length_seconds'])} and get more views.")
        elif d <= -30 and us["median_views"] < market["median_views"]:
            add("info", "Competitors make longer videos",
                f"Their videos average {_fmt_len(market['avg_length_seconds'])} vs your {_fmt_len(us['avg_length_seconds'])}. Test a few longer, in-depth videos.")

    gap = market["shorts_pct"] - us["shorts_pct"]
    if gap >= 15:
        add("lagging", "Add more Shorts",
            f"{market['shorts_pct']}% of competitors' videos are Shorts vs {us['shorts_pct']}% of yours.")
    elif gap <= -15:
        add("info", "You rely more on Shorts",
            f"{us['shorts_pct']}% of your videos are Shorts vs {market['shorts_pct']}% for competitors. Make sure long videos still get attention.")

    if market["best_time"] and us["best_time"] and market["best_time"] != us["best_time"]:
        add("info", "Test a different posting time",
            f"Competitors' best-performing videos go out in the {market['best_time']} slot. Yours do best in the {us['best_time']} slot. Try a few uploads in their slot.")

    if gaps_count:
        add("lagging", f"{gaps_count} topic{'s' if gaps_count != 1 else ''} you haven't covered",
            "Several competitors covered these and you didn't. See the Coverage Gaps tab and use Create Package.")

    if not any(s["tone"] == "lagging" for s in out):
        add("good", "No major gaps found", "You're level with or ahead of competitors on the main numbers.")
    if us["videos"] < MIN_VIDEOS or market["videos"] < MIN_VIDEOS:
        add("info", "Based on few videos",
            f"You or your competitors posted fewer than {MIN_VIDEOS} videos in the last {PERF_DAYS} days, so treat these numbers as a rough guide.")
    return out


def _fmt_len(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def compare(accounts, posts, gaps_count=0, now=None):
    """Full comparison for one organization's YouTube accounts."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=PERF_DAYS)
    yt_accounts = [a for a in accounts if a.platform == "youtube"]
    by_account = defaultdict(list)
    for p in posts:
        if p.views is not None and _utc(p.published_at) >= since:
            by_account[p.competitor_id].append(p)

    rows = []
    for a in yt_accounts:
        stats = account_stats(by_account.get(a.id, []), now)
        rows.append({"id": a.id, "name": a.name, "is_us": a.is_us, "subscribers": a.subscribers, "stats": stats})

    our_rows = [r["stats"] for r in rows if r["is_us"] and r["stats"]]
    us = our_rows[0] if our_rows else None
    market = _market([r["stats"] for r in rows if not r["is_us"] and r["stats"]])

    names = {a.id: a.name for a in yt_accounts}
    competitor_ids = {a.id for a in yt_accounts if not a.is_us}
    top = sorted(
        (p for cid in competitor_ids for p in by_account.get(cid, [])
         if now - _utc(p.published_at) >= timedelta(hours=MIN_AGE_HOURS)),
        key=lambda p: p.views or 0, reverse=True,
    )[:5]

    return {
        "days": PERF_DAYS,
        "accounts": sorted(rows, key=lambda r: (not r["is_us"], r["name"])),
        "us": us,
        "market": market,
        "top_competitor_videos": [
            {"account": names[p.competitor_id], "title": p.title, "link": p.link, "views": p.views,
             "published_at": _utc(p.published_at).isoformat(), "length_seconds": p.duration_seconds}
            for p in top
        ],
        "suggestions": suggestions(us, market, gaps_count),
    }
