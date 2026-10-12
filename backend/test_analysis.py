"""Automatic checks for the analysis. Run with:  python -m pytest -q"""
from datetime import datetime, timezone

from analysis import analyse
from sample_data import COMPETITORS, make_posts

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
RESULT = analyse(make_posts(NOW), COMPETITORS, NOW)


def find(rows, text):
    return [r for r in rows if text.lower() in r["title"].lower()]


def test_rain_story_is_p1_gap_covered_by_three():
    gap = find(RESULT["gaps"], "rain")
    assert len(gap) == 1
    assert gap[0]["covered_by"] == ["Channel A", "Channel B", "Channel C"]
    assert gap[0]["priority"] == "P1"
    assert gap[0]["first_by"] == "Channel A"


def test_gold_story_is_p2_gap():
    gap = find(RESULT["gaps"], "gold")
    assert len(gap) == 1 and gap[0]["priority"] == "P2"


def test_single_competitor_story_is_not_a_gap():
    assert find(RESULT["gaps"], "temple") == []


def test_story_we_covered_is_not_a_gap():
    assert find(RESULT["gaps"], "metro") == []


def test_unrelated_story_not_joined_with_rain():
    assert find(RESULT["gaps"], "marathon") == []
    assert len(find(RESULT["gaps"], "rain")[0]["links"]) == 3


def test_old_posts_are_ignored():
    assert len(find(RESULT["gaps"], "rain")[0]["links"]) == 3


def test_we_were_39_minutes_late_on_metro():
    row = find(RESULT["speed"], "metro")[0]
    assert row["first_by"] == "Channel B"
    assert row["delay_minutes"] == 39


def test_we_were_first_on_squad():
    row = find(RESULT["speed"], "squad")[0]
    assert row["we_were_first"] and row["delay_minutes"] == 0


def test_overview_counts():
    o = RESULT["overview"]
    assert o["gaps"] == 2
    assert o["stories_we_were_first"] == 1
    assert o["stories_we_were_late"] == 1
    assert o["avg_delay_minutes"] == 39
