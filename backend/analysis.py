"""Compare and analyse: group the same story across channels, then find
coverage gaps, who published first, and overview numbers.

Works on any objects that have these attributes, so it can be tested
without a database:
  competitor: id, name, is_us
  post:       competitor_id, title, link, published_at
"""
import re
from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz

import textutil

# Two titles with a score at or above this count as the same story.
# Raise it if unrelated stories get joined; lower it if the same story is split.
THRESHOLD = 70
# Titles must also share at least this many meaningful words.
MIN_SHARED_WORDS = 2
# Only stories from the last N hours are compared.
WINDOW_HOURS = 24
# A story is a gap only if at least this many competitors covered it.
MIN_COMPETITORS_FOR_GAP = 2
# Before calling something a gap, check our stories with this looser score,
# so a story we covered under a different headline is not shown as missed.
GAP_CHECK_THRESHOLD = 60
# Roundup / digest posts mention many stories at once and cause wrong matches.
ROUNDUP_PATTERNS = re.compile(
    r"headlines for|top headlines|news headlines|news wrap|morning brief|evening brief|top \d+ news",
    re.IGNORECASE,
)

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "from",
    "by", "with", "as", "is", "are", "was", "were", "be", "been", "after",
    "over", "into", "its", "it", "this", "that", "new", "says", "said", "amid",
    "live", "updates", "update", "news", "today", "watch", "video",
}


def _utc(dt):
    """SQLite drops the timezone, so treat naive times as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def clean_title(title):
    words = textutil.words(title)  # any script, not only a-z
    return [w for w in words if w not in STOPWORDS]


def similarity(words_a, words_b):
    """0-100 score; 0 if the titles share fewer than MIN_SHARED_WORDS words."""
    if len(set(words_a) & set(words_b)) < MIN_SHARED_WORDS:
        return 0
    return fuzz.token_set_ratio(" ".join(words_a), " ".join(words_b))


def same_story(words_a, words_b, threshold=THRESHOLD):
    return similarity(words_a, words_b) >= threshold


def recent_posts(posts, now=None, hours=WINDOW_HOURS):
    """Posts from the last N hours, without roundups and without repeats of the same title from the same channel."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    seen, result = set(), []
    for p in sorted(posts, key=lambda p: _utc(p.published_at)):
        key = (p.competitor_id, " ".join(clean_title(p.title)))
        if _utc(p.published_at) < since or ROUNDUP_PATTERNS.search(p.title) or key in seen:
            continue
        seen.add(key)
        result.append(p)
    return result


def group_stories(posts):
    """Return a list of groups; each group is a list of posts about the same story.

    A new post is compared with EVERY post already in a group (not only the first),
    so different headlines for the same story end up together.
    """
    groups = []  # each item: list of (words, post)
    for p in sorted(posts, key=lambda p: _utc(p.published_at)):
        words = clean_title(p.title)
        best, best_score = None, -1
        for g in groups:
            score = max(similarity(words, w) for w, _ in g)
            if score >= THRESHOLD and score > best_score:
                best, best_score = g, score
        if best is not None:
            best.append((words, p))
        else:
            groups.append([(words, p)])
    return [[p for _, p in g] for g in groups]


def we_covered_it(group, our_posts):
    """Looser check: did we publish anything close to this story, even under a different headline?"""
    for ours in our_posts:
        ours_words = clean_title(ours.title)
        if any(same_story(ours_words, clean_title(p.title), GAP_CHECK_THRESHOLD) for p in group):
            return True
    return False


def find_gaps(groups, competitors):
    """Stories that 2+ competitors covered and we did not. Most-covered first."""
    by_id = {c.id: c for c in competitors}
    us_ids = {c.id for c in competitors if c.is_us}
    our_posts = [p for g in groups for p in g if p.competitor_id in us_ids]
    gaps = []
    for i, g in enumerate(groups, start=1):
        sources = {p.competitor_id for p in g}
        # Count by name, so one competitor's website + YouTube channel count as one competitor.
        names = {by_id[s].name for s in sources}
        if sources & us_ids or len(names) < MIN_COMPETITORS_FOR_GAP:
            continue
        if we_covered_it(g, our_posts):
            continue
        first = min(g, key=lambda p: _utc(p.published_at))
        gaps.append({
            "story_id": i,
            "title": first.title,
            "covered_by": sorted(names),
            "platforms": sorted({getattr(by_id[s], "platform", "rss") for s in sources}),
            "first_by": by_id[first.competitor_id].name,
            "first_published_at": _utc(first.published_at).isoformat(),
            "links": [p.link for p in g],
            "priority": "P1" if len(names) >= 3 else "P2",
        })
    gaps.sort(key=lambda x: (-len(x["covered_by"]), x["first_published_at"]))
    return gaps


def speed_report(groups, competitors):
    """Stories we covered that at least one competitor also covered: who was first, our delay."""
    by_id = {c.id: c for c in competitors}
    us_ids = {c.id for c in competitors if c.is_us}
    rows = []
    for i, g in enumerate(groups, start=1):
        ours = [p for p in g if p.competitor_id in us_ids]
        theirs = [p for p in g if p.competitor_id not in us_ids]
        if not ours or not theirs:
            continue
        first = min(g, key=lambda p: _utc(p.published_at))
        our_first = min(ours, key=lambda p: _utc(p.published_at))
        delay = int((_utc(our_first.published_at) - _utc(first.published_at)).total_seconds() // 60)
        rows.append({
            "story_id": i,
            "title": our_first.title,
            "first_by": by_id[first.competitor_id].name,
            "first_at": _utc(first.published_at).isoformat(),
            "our_at": _utc(our_first.published_at).isoformat(),
            "delay_minutes": delay,
            "we_were_first": delay == 0,
        })
    rows.sort(key=lambda r: -r["delay_minutes"])
    return rows


def overview(posts, gaps, speed_rows, competitors):
    us_ids = {c.id for c in competitors if c.is_us}
    late = [r["delay_minutes"] for r in speed_rows if r["delay_minutes"] > 0]
    return {
        "our_posts": sum(1 for p in posts if p.competitor_id in us_ids),
        "competitor_posts": sum(1 for p in posts if p.competitor_id not in us_ids),
        "gaps": len(gaps),
        "stories_we_were_first": sum(1 for r in speed_rows if r["we_were_first"]),
        "stories_we_were_late": len(late),
        "avg_delay_minutes": round(sum(late) / len(late)) if late else 0,
    }


def analyse(posts, competitors, now=None, window_hours=WINDOW_HOURS):
    """Run everything once and return all results."""
    posts = recent_posts(posts, now, window_hours)
    groups = group_stories(posts)
    gaps = find_gaps(groups, competitors)
    speed = speed_report(groups, competitors)
    return {
        "overview": overview(posts, gaps, speed, competitors),
        "gaps": gaps,
        "speed": speed,
    }
