"""Competitor Content DNA: what an account publishes, described only from its public posts.

Per account (last DNA_DAYS days): main topics, formats, publishing rhythm, video length,
title patterns, public engagement, posts far above its own usual, and topics that appeared or
faded. Every statement carries the number of posts behind it. Nothing here claims to know an
account's audience, private analytics, or WHY a post did well.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

import topics as topic_map
from dataset import iso, utc
from performance import engagement_rate

DNA_DAYS = 90
MIN_POSTS = 10            # fewer posts than this: patterns are shown as tentative
PATTERN_MIN_SHARE = 0.25  # a title pattern must appear in 25%+ of titles to be called common
PATTERN_MIN_POSTS = 2
STANDOUT = 2.0

# English keyword rules: other languages are counted only by punctuation-based patterns.
TITLE_PATTERNS = [
    ("question", "Asks a question", re.compile(r"\?")),
    ("number", "Numbers or lists (\"5 tips\", \"Top 10\")",
     re.compile(r"^\s*\d+\b|\btop\s*\d+|\b\d+\s+(ways|tips|things|mistakes|reasons|steps|ideas|best|rules)\b", re.I)),
    ("how_to", "How-to, tutorial or guide",
     re.compile(r"\bhow to\b|\btutorial\b|\bguide\b|\bexplained\b|\bbeginners?\b|\bstep[- ]by[- ]step\b|\blearn\b", re.I)),
    ("brackets", "Brackets or separators ( [ |", re.compile(r"[(\[|]")),
    ("caps", "Words in capitals (emphasis or acronyms)", re.compile(r"\b[A-Z]{3,}\b")),
]


def _has_emoji(text):
    return any(unicodedata.category(c) == "So" for c in text or "")


def _main_topics(account, posts, rules, limit=6):
    aliases, excluded = topic_map.normalize_rules(rules)
    skip = topic_map._account_words([account])
    counts = defaultdict(set)
    for p in posts:
        for t in topic_map.post_terms(p, skip):
            if t in excluded:
                continue
            t = aliases.get(t, t).lower()
            if t not in excluded:
                counts[t].add(p.id)
    n = len(posts)
    # Terms on almost every post are the account's branding, not a topic.
    rows = [(t, ids) for t, ids in counts.items() if len(ids) >= 2 and not (n >= 5 and len(ids) / n > 0.6)]
    phrases = [(t, ids) for t, ids in rows if " " in t]
    keep = []
    for t, ids in rows:
        if " " not in t and any(t in ph.split() and len(pids) >= 0.7 * len(ids) for ph, pids in phrases):
            continue
        keep.append((t, ids))
    keep.sort(key=lambda r: (-len(r[1]), r[0]))
    return [{"topic": t, "posts": len(ids)} for t, ids in keep[:limit]]


def _title_patterns(ds, posts):
    out = []
    n = len(posts)
    checks = [(k, label, (lambda rx: lambda t: bool(rx.search(t)))(rx)) for k, label, rx in TITLE_PATTERNS]
    checks.append(("emoji", "Uses emoji", _has_emoji))
    for key, label, test in checks:
        hits = [p for p in posts if test(p.title)]
        if len(hits) < PATTERN_MIN_POSTS or len(hits) / n < PATTERN_MIN_SHARE:
            continue
        hit_ids = {p.id for p in hits}
        rel_in = [ds.relative[p.id] for p in hits if p.id in ds.relative]
        rel_out = [ds.relative[p.id] for p in posts if p.id not in hit_ids and p.id in ds.relative]
        out.append({
            "pattern": key, "label": label, "posts": len(hits), "share": round(len(hits) / n * 100),
            "examples": [p.title for p in hits[:2]],
            "median_relative": round(median(rel_in), 2) if len(rel_in) >= 3 else None,
            "others_median_relative": round(median(rel_out), 2) if len(rel_out) >= 3 else None,
        })
    return sorted(out, key=lambda r: -r["share"])


def _topic_shift(account, posts, rules, now, days):
    """Topics in the recent half of the period that didn't appear in the earlier half, and the reverse."""
    half = now - timedelta(days=days / 2)
    recent = [p for p in posts if utc(p.published_at) >= half]
    earlier = [p for p in posts if utc(p.published_at) < half]
    if len(recent) < 4 or len(earlier) < 4:
        return None
    r = {t["topic"]: t["posts"] for t in _main_topics(account, recent, rules, 20)}
    e = {t["topic"]: t["posts"] for t in _main_topics(account, earlier, rules, 20)}
    return {
        "split_at": iso(half),
        "new": [{"topic": t, "posts": n} for t, n in r.items() if t not in e][:4],
        "faded": [{"topic": t, "posts": n} for t, n in e.items() if t not in r][:4],
        "recent_posts": len(recent), "earlier_posts": len(earlier),
    }


def profile(ds, account, days=DNA_DAYS):
    since = ds.now - timedelta(days=days)
    posts = sorted((p for p in ds.posts if p.competitor_id == account.id and utc(p.published_at) >= since),
                   key=lambda p: p.published_at, reverse=True)
    rules = getattr(ds.org, "topic_rules", None)
    base = {"account": {"id": account.id, "name": account.name, "platform": account.platform, "is_us": account.is_us,
                        "group": getattr(account, "group", None), "thumbnail": getattr(account, "thumbnail", None),
                        "subscribers": getattr(account, "subscribers", None)},
            "days": days, "posts": len(posts)}
    if not posts:
        return {**base, "enough_data": False, "summary": [f"No posts collected from {account.name} in the last {days} days."]}

    oldest = utc(posts[-1].published_at)
    span = max(min((ds.now - oldest).days, days), 1)
    per_week = round(len(posts) / span * 7, 1)
    formats = Counter(ds.format(p) for p in posts if ds.format(p))
    durations = [p.duration_seconds for p in posts if p.duration_seconds]
    mature = [p for p in posts if ds.now - utc(p.published_at) >= timedelta(hours=24)]
    views = [p.views for p in mature if p.views is not None]
    hidden_likes = sum(1 for p in mature if p.views is not None and p.likes is None)
    standouts = sorted((p for p in posts if (ds.relative.get(p.id) or 0) >= STANDOUT), key=lambda p: -ds.relative[p.id])
    main = _main_topics(account, posts, rules)
    patterns = _title_patterns(ds, posts)
    shift = _topic_shift(account, posts, rules, ds.now, days)
    enough = len(posts) >= MIN_POSTS

    fmt_rows = [{"format": f, "posts": n, "share": round(n / len(posts) * 100)} for f, n in formats.most_common()]
    summary = []
    summary.append(f"Published {len(posts)} post{'s' if len(posts) != 1 else ''} in the last {span} days (about {per_week} a week).")
    if fmt_rows:
        top = fmt_rows[0]
        summary.append(f'Mostly {top["format"]} posts ({top["share"]}% of {len(posts)}).')
    if main:
        summary.append("Most frequent topics: " + ", ".join(f'"{t["topic"]}" ({t["posts"]} posts)' for t in main[:3]) + ".")
    if patterns:
        p = patterns[0]
        line = f'{p["share"]}% of titles: {p["label"].lower()}'
        if p["median_relative"] is not None and p["others_median_relative"] is not None:
            line += f' (those got {p["median_relative"]}× its usual views vs {p["others_median_relative"]}× for other titles)'
        summary.append(line + ".")
    if standouts:
        summary.append(f'{len(standouts)} post{"s" if len(standouts) != 1 else ""} got {STANDOUT:g}× or more of its usual views; '
                       f'top: "{standouts[0].title}" ({ds.relative[standouts[0].id]}×).')
    if shift and shift["new"]:
        summary.append("Newer topics recently: " + ", ".join(f'"{t["topic"]}"' for t in shift["new"][:3]) + ".")
    if not enough:
        summary.append(f"Only {len(posts)} posts: these are early signs, not consistent patterns. More data is needed.")

    return {
        **base,
        "enough_data": enough,
        "per_week": per_week,
        "span_days": span,
        "first_post": iso(oldest),
        "last_post": iso(posts[0].published_at),
        "formats": fmt_rows,
        "median_duration_seconds": round(median(durations)) if durations else None,
        "duration_sample": len(durations),
        "main_topics": main,
        "title_patterns": patterns,
        "avg_title_words": round(sum(len(p.title.split()) for p in posts) / len(posts), 1),
        "median_views": round(median(views)) if views else None,
        "views_sample": len(views),
        "engagement_rate": engagement_rate(mature),
        "likes_hidden": hidden_likes,
        "baseline": ds.baseline.get(account.id),
        "standouts": [ds.post_card(p) for p in standouts[:4]],
        "standout_count": len(standouts),
        "topic_shift": shift,
        "recent_posts": [ds.post_card(p) for p in posts[:4]],
        "summary": summary,
        "limitations": [
            "Based only on public titles, tags, formats and counts. Audience demographics and private analytics aren't available.",
            "Title patterns are found with English keyword rules; other languages count only by punctuation.",
            "A post doing well doesn't show why it did well.",
        ],
    }
