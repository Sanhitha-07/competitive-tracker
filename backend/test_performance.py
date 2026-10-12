"""Checks for the YouTube comparison and suggestions. Run with:  python -m pytest -q"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Row

from performance import compare

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)

ACCOUNTS = [
    Row(id=1, name="Us", is_us=True, platform="youtube", subscribers=1000),
    Row(id=2, name="Rival A", is_us=False, platform="youtube", subscribers=5000),
    Row(id=3, name="Rival B", is_us=False, platform="youtube", subscribers=4000),
    Row(id=4, name="Silent C", is_us=False, platform="youtube", subscribers=100),  # no recent videos
]


def video(cid, n, days_ago, views, likes, comments, length):
    return Row(competitor_id=cid, title=f"Video {cid}-{n}", link=f"https://yt/{cid}/{n}",
               published_at=NOW - timedelta(days=days_ago), views=views, likes=likes,
               comments=comments, duration_seconds=length)


POSTS = (
    # Us: 3 long videos, low views, low engagement
    [video(1, i, 3 + i * 8, 1000, 5, 1, 900) for i in range(3)]
    # Rivals: 8 videos each, half of them Shorts, more views, more engagement
    + [video(2, i, 2 + i * 3, 10000, 400, 50, 45 if i % 2 else 300) for i in range(8)]
    + [video(3, i, 2 + i * 3, 8000, 300, 40, 50 if i % 2 else 280) for i in range(8)]
    # Older than 30 days: ignored
    + [video(4, 0, 45, 999999, 1, 1, 100)]
)

RESULT = compare(ACCOUNTS, POSTS, gaps_count=2, now=NOW)
TITLES = [s["title"] for s in RESULT["suggestions"]]


def test_market_ignores_accounts_without_recent_videos():
    assert RESULT["market"]["videos"] == 8
    silent = [a for a in RESULT["accounts"] if a["name"] == "Silent C"][0]
    assert silent["stats"] is None


def test_us_listed_first():
    assert RESULT["accounts"][0]["name"] == "Us"


def test_lagging_suggestions():
    assert "Post more often" in TITLES
    assert "Your videos get fewer views" in TITLES
    assert "Engagement is low" in TITLES
    assert "Try shorter videos" in TITLES
    assert "Add more Shorts" in TITLES
    assert "2 topics you haven't covered" in TITLES


def test_few_videos_note():
    assert "Based on few videos" in TITLES


def test_top_competitor_videos_exclude_us():
    assert RESULT["top_competitor_videos"]
    assert all(v["account"] != "Us" for v in RESULT["top_competitor_videos"])


def test_doing_well_when_ahead():
    flipped = [Row(**{**vars(a), "is_us": a.id == 2}) for a in ACCOUNTS]
    result = compare(flipped, POSTS, now=NOW)
    tones = {s["title"]: s["tone"] for s in result["suggestions"]}
    assert tones.get("Your views are above the market") == "good"
    assert tones.get("Strong engagement") == "good"
