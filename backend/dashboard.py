"""Performance dashboard: one consistent set of numbers for the chosen period and filters.

Every figure here comes from the same filtered list of posts, so the summary, chart, insights and
tables always agree. Rules:
  - YouTube and website (RSS) content are kept apart: feeds have no views, so they are never
    mixed into view-based numbers.
  - A number that can't be calculated is None with a reason, never 0.
  - Chart points are only real observations. A week with no posts has no "views" point
    (a gap), and weeks before we started collecting an account have no point at all.
  - "Current" values (a post's latest view count) and "snapshots" (numbers saved at each Refresh)
    are labelled differently.
"""
from collections import defaultdict
from datetime import timedelta
from statistics import median

import textutil
import topics as topic_map
from dataset import iso, utc
from performance import MIN_AGE_HOURS, compare, engagement_rate

MIN_INSIGHT_POSTS = 3       # posts needed on each side before a comparison becomes an insight
INSIGHT_LIFT = 1.2          # "does better" = at least 1.2× the usual views
ACTIVITY_CHANGE = 0.4       # publishing activity must change by 40%+ to be mentioned
STANDOUT_RATIO = 2.0

PER_WEEK_LABELS = {"youtube": "Videos per week", "rss": "Articles per week", "instagram": "Instagram posts per week",
                   "facebook": "Facebook posts per week", "x": "X posts per week"}
SOCIAL = {"instagram": "Instagram", "facebook": "Facebook", "x": "X"}
# Metrics each platform really reports for posts (anything else is shown as not available).
SOCIAL_METRICS = {"instagram": ["likes", "comments"], "facebook": ["likes", "comments", "shares"],
                  "x": ["views", "likes", "comments", "shares"]}

SOURCES = {
    "youtube": "YouTube Data API (public counts at the last Refresh)",
    "rss": "Website RSS feed (titles, links and dates only)",
    "calc": "Calculated by the tracker from collected posts",
    "snapshot": "Saved at each Refresh (history)",
}


def _median(values):
    values = [v for v in values if v is not None]
    return round(median(values), 2) if values else None


def _week(dt):
    d = utc(dt)
    return (d - timedelta(days=d.weekday())).date().isoformat()


def filter_posts(ds, posts, fmt=None, topic=None, platform=None):
    """The posts the dashboard shows: inside the period, optionally one platform, format and/or topic."""
    out = [p for p in posts if utc(p.published_at) >= ds.since]
    if platform:
        out = [p for p in out if p.platform == platform]
    if fmt:
        out = [p for p in out if ds.format(p) == fmt]
    if topic:
        out = [p for p in out if textutil.contains_phrase(" ".join([p.title, *(p.tags or [])]), topic)]
    return out


def _mature(ds, posts):
    return [p for p in posts if ds.now - utc(p.published_at) >= timedelta(hours=MIN_AGE_HOURS)]


# ---- summary ----

def _metric(key, label, ours, theirs, fmt, definition, source, sample_ours, sample_theirs, note=None):
    return {"key": key, "label": label, "ours": ours, "theirs": theirs, "format": fmt,
            "definition": definition, "source": source, "sample_ours": sample_ours,
            "sample_theirs": sample_theirs, "note": note}


def summary(ds, posts, opportunities, platform=None):
    """Summary cards. With a platform filter, only that platform's cards are shown."""
    ours = [p for p in posts if ds.is_us(p)]
    theirs = [p for p in posts if not ds.is_us(p)]
    days = max((ds.now - ds.since).days, 1)
    out = [
        _metric("our_posts", "Your posts", len(ours), None, "count", "Posts collected from your accounts in this period.",
                SOURCES["calc"], len(ours), None),
        _metric("competitor_posts", "Competitor posts", len(theirs), None, "count",
                "Posts collected from the competitors in this view.", SOURCES["calc"], len(theirs), None),
    ]
    for pid, label in PER_WEEK_LABELS.items():
        if platform and pid != platform:
            continue
        o = [p for p in ours if p.platform == pid]
        t = [p for p in theirs if p.platform == pid]
        # Show the card when there are posts, or accounts on this platform (then 0 posts is a real count).
        if not o and not t and not any(a.platform == pid for a in ds.accounts):
            continue
        comp_ids = {p.competitor_id for p in t} or {a.id for a in ds.accounts if not a.is_us and a.platform == pid}
        theirs_rate = round(len(t) / max(len(comp_ids), 1) / days * 7, 1) if comp_ids else None
        out.append(_metric(f"per_week_{pid}", label, round(len(o) / days * 7, 1), theirs_rate, "number",
                           "Posts in the period ÷ days × 7. Competitors: average per competitor account.",
                           SOURCES["calc"], len(o), len(t)))

    yt_ours = [p for p in _mature(ds, ours) if p.platform == "youtube" and p.views is not None]
    yt_theirs = [p for p in _mature(ds, theirs) if p.platform == "youtube" and p.views is not None]
    per_comp = defaultdict(list)
    for p in yt_theirs:
        per_comp[p.competitor_id].append(p.views)
    comp_medians = [median(v) for v in per_comp.values()]
    has_yt = platform in (None, "", "youtube") and any(a.platform == "youtube" for a in ds.accounts)
    if has_yt:
        out.append(_metric(
            "typical_views", "Typical views (YouTube)",
            round(median(p.views for p in yt_ours)) if yt_ours else None,
            round(median(comp_medians)) if comp_medians else None, "compact",
            "Median views of videos at least 24 hours old. Competitors: the median of each competitor's own median, so each channel counts once.",
            SOURCES["youtube"], len(yt_ours), len(yt_theirs),
            None if yt_ours else "None of your videos in this view are 24h+ old with a view count."))
        rate_o, rate_t = engagement_rate(yt_ours), engagement_rate(yt_theirs)
        out.append(_metric(
            "engagement", "Engagement (YouTube)", rate_o, rate_t, "percent",
            "(likes + comments) ÷ views, for videos whose like count is public.",
            SOURCES["youtube"], len([p for p in yt_ours if p.likes is not None]),
            len([p for p in yt_theirs if p.likes is not None]),
            None if rate_o is not None else "Not available: no video in this view has a public like count."))
    out.append(_metric("opportunities", "Open suggestions", opportunities, None, "count",
                       "Suggestions with enough evidence to act on (see Suggestions).", SOURCES["calc"], None, None))
    return out


# ---- trend chart ----

TREND_METRICS = [
    {"id": "views", "label": "Typical views of videos published each week", "platform": "youtube", "kind": "current",
     "note": "Median of each video's latest view count, grouped by publishing week. Older weeks have had more time to collect views."},
    {"id": "relative", "label": "Performance vs each channel's usual", "platform": "youtube", "kind": "current",
     "note": "Median of (views ÷ that channel's usual views) per week. 1.0× = the channel's usual, so channels of any size compare fairly."},
    {"id": "posts_youtube", "label": "Videos published per week", "platform": "youtube", "kind": "count",
     "note": "Videos collected per publishing week. Weeks before we started collecting an account have no point."},
    {"id": "posts_rss", "label": "Articles published per week", "platform": "rss", "kind": "count",
     "note": "Feed items per publishing week. Feeds only return their latest items, so older weeks may be incomplete."},
    {"id": "subscribers", "label": "Subscribers (YouTube)", "platform": "youtube", "kind": "snapshot",
     "note": "Public subscriber count saved at each Refresh. YouTube rounds it, and history starts at your first Refresh."},
]


def trend(ds, posts, all_posts, audience_snaps):
    """Weekly series per account for each metric the data supports. No invented points."""
    first_seen = {}
    for p in all_posts:  # earliest post we know per account, across all time
        t = utc(p.published_at)
        if p.competitor_id not in first_seen or t < first_seen[p.competitor_id]:
            first_seen[p.competitor_id] = t
    weeks = []
    w = utc(ds.since) - timedelta(days=utc(ds.since).weekday())
    while w <= ds.now:
        weeks.append(w.date().isoformat())
        w += timedelta(days=7)

    by_acc_week = defaultdict(lambda: defaultdict(list))
    for p in posts:
        by_acc_week[p.competitor_id][_week(p.published_at)].append(p)

    series = {m["id"]: [] for m in TREND_METRICS}
    for a in ds.accounts:
        start = first_seen.get(a.id)
        base = {"account_id": a.id, "name": a.name, "is_us": a.is_us}
        if a.platform == "youtube":
            vp, rp, cp = [], [], []
            for wk in weeks:
                ps = by_acc_week[a.id].get(wk, [])
                known = start is not None and _week(start) <= wk
                views = [p.views for p in ps if p.views is not None]
                rels = [ds.relative[p.id] for p in ps if p.id in ds.relative]
                vp.append({"x": wk, "y": round(median(views)) if views else None, "n": len(views)})
                rp.append({"x": wk, "y": _median(rels), "n": len(rels)})
                cp.append({"x": wk, "y": len(ps) if known else None, "n": len(ps)})
            series["views"].append({**base, "points": vp})
            if a.id in ds.baseline:
                series["relative"].append({**base, "points": rp})
            series["posts_youtube"].append({**base, "points": cp})
            snaps = [s for s in audience_snaps.get(a.id, []) if s[0] >= ds.since and s[1] is not None]
            if snaps:
                series["subscribers"].append({**base, "points": [{"x": iso(t), "y": v, "n": 1} for t, v in snaps]})
        elif a.platform == "rss":
            cp = []
            for wk in weeks:
                ps = by_acc_week[a.id].get(wk, [])
                known = start is not None and _week(start) <= wk
                cp.append({"x": wk, "y": len(ps) if known else None, "n": len(ps)})
            series["posts_rss"].append({**base, "points": cp})
    metrics = [m for m in TREND_METRICS
               if any(any(pt["y"] is not None for pt in s["points"]) for s in series[m["id"]])]
    return {"weeks": weeks, "metrics": metrics, "series": {m["id"]: series[m["id"]] for m in metrics}}


# ---- comparisons by format and topic ----

def format_table(ds, posts):
    rows = defaultdict(lambda: {"ours": [], "theirs": []})
    for p in posts:
        f = ds.format(p)
        if f:
            rows[f]["ours" if ds.is_us(p) else "theirs"].append(p)
    out = []
    for f, sides in rows.items():
        row = {"format": f}
        for side, ps in sides.items():
            rels = [ds.relative[p.id] for p in ps if p.id in ds.relative]
            row[side] = {"posts": len(ps), "median_relative": _median(rels), "sample": len(rels),
                         "enough": len(rels) >= MIN_INSIGHT_POSTS}
        out.append(row)
    return sorted(out, key=lambda r: -(r["ours"]["posts"] + r["theirs"]["posts"]))


def topic_table(ds, posts):
    rows, _ = topic_map.coverage_map(posts, ds.accounts, ds.cfg["topics"], ds.relative, (),
                                     getattr(ds.org, "topic_rules", None))
    out = []
    for t in rows:
        if t["our_posts"] < 2:  # "your topics": at least 2 of your posts
            continue
        out.append({"topic": t["topic"], "our_posts": t["our_posts"], "our_median_relative": t["our_median_relative"],
                    "our_sample": t["our_relative_sample"], "competitor_posts": t["competitor_posts"],
                    "competitor_median_relative": t["median_relative"], "competitor_sample": t["relative_sample"],
                    "enough": t["our_relative_sample"] >= MIN_INSIGHT_POSTS, "post_ids": t["post_ids"]})
    out.sort(key=lambda r: (-r["our_posts"], -r["competitor_posts"]))
    return out[:15]


# ---- insights ----

def insights(ds, posts, formats, topic_rows, recs):
    out = []
    ours = [p for p in posts if ds.is_us(p)]

    best = [t for t in topic_rows if t["our_sample"] >= MIN_INSIGHT_POSTS and (t["our_median_relative"] or 0) >= INSIGHT_LIFT]
    if best:
        t = max(best, key=lambda r: r["our_median_relative"])
        ev = [ds.post_card(ds.post_by_id[i]) for i in t["post_ids"] if ds.is_us(ds.post_by_id[i])][:4]
        out.append({"id": "best_topic", "tone": "good", "title": f'Your posts about "{t["topic"]}" do better than usual',
                    "detail": f'Your {t["our_sample"]} posts on it got a median of {t["our_median_relative"]}× your usual.',
                    "why": "A topic that beats your own baseline is a candidate for more posts or a series.",
                    "sample": f'{t["our_sample"]} of your posts with view data.', "evidence": ev,
                    "limitation": "Topics are matched by keywords; a few strong posts can lift a small sample.",
                    "action": {"label": "Test it as an experiment", "tab": "opportunities"}})

    ok = [r for r in formats if r.get("ours", {}).get("enough")]
    if len(ok) >= 2:
        ranked = sorted(ok, key=lambda r: -r["ours"]["median_relative"])
        top, second = ranked[0], ranked[1]
        if top["ours"]["median_relative"] >= INSIGHT_LIFT and top["ours"]["median_relative"] - second["ours"]["median_relative"] >= 0.3:
            out.append({"id": "best_format", "tone": "good", "title": f'Your "{top["format"]}" posts beat your usual',
                        "detail": f'Median {top["ours"]["median_relative"]}× your usual ({top["ours"]["sample"]} posts), '
                                  f'vs {second["ours"]["median_relative"]}× for "{second["format"]}" ({second["ours"]["sample"]} posts).',
                        "why": "Compared with your own baseline, so channel size doesn't matter.",
                        "sample": f'{top["ours"]["sample"] + second["ours"]["sample"]} of your posts.', "evidence": [],
                        "limitation": "Formats often differ in topic too, so the format alone may not explain it.",
                        "action": {"label": "Test it as an experiment", "tab": "opportunities"}})

    standouts = sorted((p for p in posts if not ds.is_us(p) and (ds.relative.get(p.id) or 0) >= STANDOUT_RATIO),
                       key=lambda p: -ds.relative[p.id])
    if standouts:
        n = len(standouts)
        out.append({"id": "competitor_standouts", "tone": "info",
                    "title": f'{n} competitor post{"s" if n != 1 else ""} did {STANDOUT_RATIO:g}×+ their usual',
                    "detail": f'Top: "{standouts[0].title}" by {ds.by_id[standouts[0].competitor_id].name} '
                              f'at {ds.relative[standouts[0].id]}× its channel\'s usual.',
                    "why": "Posts far above their own channel's usual show what that audience responded to.",
                    "sample": f"{n} post(s) out of {len([p for p in posts if not ds.is_us(p)])} competitor posts in this view.",
                    "evidence": [ds.post_card(p) for p in standouts[:4]],
                    "limitation": "One post's success can come from promotion or trends this data can't see.",
                    "action": {"label": "Open in Content Explorer", "tab": "explorer"}})

    gap = next((r for r in recs if r["kind"] == "topic_gap"), None)
    if gap:
        out.append({"id": "topic_to_explore", "tone": "info", "title": f'Topic worth exploring: "{gap["topic"]}"',
                    "detail": gap["observed"], "why": gap["why_relevant"], "sample": gap["sample"]["text"],
                    "evidence": gap["evidence"]["posts"][:3], "limitation": gap["limitations"][0],
                    "action": {"label": "See Suggestions", "tab": "suggestions"}})

    half = ds.since + (ds.now - ds.since) / 2
    for platform, noun in (("youtube", "videos"), ("rss", "articles")):
        ps = [p for p in ours if p.platform == platform]
        early = sum(1 for p in ps if utc(p.published_at) < half)
        late = len(ps) - early
        if len(ps) >= 6 and early and abs(late - early) / early >= ACTIVITY_CHANGE:
            days = round((ds.now - half).days)
            more = late > early
            out.append({"id": f"activity_{platform}", "tone": "info",
                        "title": f"You published {'more' if more else 'fewer'} {noun} recently",
                        "detail": f"{late} {noun} in the last {days} days vs {early} in the {days} days before.",
                        "why": "A change in activity can explain changes in reach; check results before and after.",
                        "sample": f"{len(ps)} of your {noun}.", "evidence": [],
                        "limitation": "Feeds and channel lists only return recent items, so the earlier half may be incomplete.",
                        "action": None})
    return out


# ---- the two separate content sections ----

def youtube_section(ds, posts):
    vids = sorted((p for p in posts if ds.is_us(p) and p.platform == "youtube"), key=lambda p: p.published_at, reverse=True)
    channels = [{"id": a.id, "name": a.name, "baseline": ds.baseline.get(a.id)}
                for a in ds.accounts if a.is_us and a.platform == "youtube"]
    return {"connected": bool(channels), "channels": channels, "total": len(vids),
            "items": [ds.post_card(p) for p in vids[:25]]}


def website_section(ds, posts):
    arts = sorted((p for p in posts if ds.is_us(p) and p.platform == "rss"), key=lambda p: p.published_at, reverse=True)
    sites = [{"id": a.id, "name": a.name} for a in ds.accounts if a.is_us and a.platform == "rss"]
    return {"connected": bool(sites), "sites": sites, "total": len(arts),
            "items": [ds.post_card(p) for p in arts[:25]],
            "metrics_available": False,
            "metrics_note": "RSS feeds share titles, links and dates, not page views. Traffic and "
                            "performance vs your usual appear here only once an analytics source is connected."}


def social_section(ds, posts, platform, configured):
    """Our posts on Instagram, Facebook or X, with only the metrics that platform reports."""
    items = sorted((p for p in posts if ds.is_us(p) and p.platform == platform), key=lambda p: p.published_at, reverse=True)
    ours = [{"id": a.id, "name": a.name, "baseline": ds.baseline.get(a.id)} for a in ds.accounts
            if a.is_us and a.platform == platform]
    return {"platform": platform, "label": SOCIAL[platform], "configured": configured, "connected": bool(ours),
            "accounts": ours, "competitors": sum(1 for a in ds.accounts if not a.is_us and a.platform == platform),
            "metrics": SOCIAL_METRICS[platform], "total": len(items),
            "items": [ds.post_card(p) for p in items[:25]]}


def build(ds, all_posts, *, fmt=None, topic=None, platform=None, recs=(), audience_snaps=None, social_configured=None):
    posts = filter_posts(ds, ds.posts, fmt, topic, platform)
    formats = format_table(ds, posts)
    topic_rows = topic_table(ds, posts)
    actionable = [r for r in recs if r["actionable"]]
    standouts = sorted((p for p in posts if not ds.is_us(p) and (ds.relative.get(p.id) or 0) >= 1.5),
                       key=lambda p: -ds.relative[p.id])[:6]
    days = round((ds.now - ds.since).total_seconds() / 86400)
    return {
        "period": ds.period(),
        "freshness": ds.freshness(),
        "filters": {"format": fmt, "topic": topic, "platform": platform},
        "summary": summary(ds, posts, len(actionable), platform),
        "trend": trend(ds, posts, all_posts, audience_snaps or {}),
        "insights": insights(ds, posts, formats, topic_rows, actionable),
        "top_posts": [ds.post_card(p) for p in sorted(
            (p for p in posts if ds.is_us(p) and p.id in ds.relative), key=lambda p: -ds.relative[p.id])[:5]],
        "has_baseline": any(a in ds.baseline for a in ds.us_ids),
        "formats": formats,
        "topics": [{k: v for k, v in t.items() if k != "post_ids"} for t in topic_rows],
        "competitor_standouts": [ds.post_card(p) for p in standouts],
        "youtube": youtube_section(ds, posts),
        "website": website_section(ds, posts),
        "social": [social_section(ds, posts, pid, (social_configured or {}).get(pid, False)) for pid in SOCIAL],
        "comparison": compare(ds.accounts, posts, now=ds.now, tz=ds.tz, days=max(days, 1)),
        "sources": SOURCES,
    }
