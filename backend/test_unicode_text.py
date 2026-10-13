"""Text in Indian scripts (Telugu, Hindi, Tamil) must split into whole words.

Titles here are real examples from saree brands' YouTube channels.
Run with:  python -m pytest -q
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import analysis
import textutil
import topics

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
TELUGU_TITLE = "మెగా ఆషాడం సేల్ లో ధర్మవరం కంచిపట్టు శారీస్ #aashadamoffers"


# ---- splitting words ----

def test_telugu_words_stay_whole():
    assert textutil.words(TELUGU_TITLE) == [
        "మెగా", "ఆషాడం", "సేల్", "లో", "ధర్మవరం", "కంచిపట్టు", "శారీస్", "aashadamoffers"]


def test_hindi_and_tamil_words_stay_whole():
    assert textutil.words("सिल्क साड़ी") == ["सिल्क", "साड़ी"]   # silk saree
    assert textutil.words("பட்டு புடவை") == ["பட்டு", "புடவை"]  # silk saree


def test_latin_text_splits_as_before():
    assert textutil.words("Men's Ethnic-Wear SALE 2026!") == ["men", "s", "ethnic", "wear", "sale", "2026"]
    assert textutil.words("snake_case") == ["snake", "case"]   # underscore still separates words
    assert textutil.words("Café crème") == ["café", "crème"]  # accents no longer cut words


def test_emoji_and_symbols_are_not_words():
    assert textutil.words("Grand Sale 💕😭 ₹1500/-") == ["grand", "sale", "1500"]


def test_zero_width_joiner_inside_word_is_kept():
    word = "క\u200dష"
    assert textutil.words(f"{word} test") == [word, "test"]


def test_empty_and_none():
    assert textutil.words("") == [] and textutil.words(None) == []
    assert textutil.contains_phrase("anything", "") is False


# ---- matching whole words ----

def test_phrase_does_not_match_inside_a_longer_word():
    assert textutil.contains_phrase("Wholesale prices?", "sale") is False
    assert textutil.contains_phrase("కంచిపట్టు శారీస్", "కంచి") is False


def test_phrase_matches_whole_words_in_any_script():
    assert textutil.contains_phrase("Aashadam SALE now!", "sale")
    assert textutil.contains_phrase(TELUGU_TITLE, "కంచిపట్టు శారీస్")
    assert not textutil.contains_phrase(TELUGU_TITLE, "శారీస్ కంచిపట్టు")  # order matters


# ---- the topic map finds Telugu topics ----

def _post(i, account, title, hours_ago=1):
    return NS(id=i, competitor_id=account, title=title, tags=[], link=f"https://x/{i}",
              published_at=NOW - timedelta(hours=hours_ago))


ACCOUNTS = [NS(id=1, name="Missamma Sarees", is_us=True),
            NS(id=2, name="Brand A", is_us=False),
            NS(id=3, name="Brand B", is_us=False)]


def test_telugu_topic_found_across_competitors():
    posts = [
        _post(1, 2, "కంచిపట్టు శారీస్ కొత్త కలెక్షన్"),
        _post(2, 3, "కంచిపట్టు శారీస్ ఆఫర్"),
        _post(3, 2, "కంచిపట్టు శారీస్ బ్రైడల్"),
        _post(4, 1, "Mangalagiri cotton sarees"),
    ]
    rows, _ = topics.coverage_map(posts, ACCOUNTS)
    found = {r["topic"]: r for r in rows}
    assert "కంచిపట్టు శారీస్" in found
    row = found["కంచిపట్టు శారీస్"]
    assert row["competitors"] == ["Brand A", "Brand B"]
    assert row["our_posts"] == 0 and row["status"] == "not_covered_by_you"


def test_tracked_telugu_keyword_counts_only_whole_words():
    posts = [_post(1, 2, "కంచిపట్టు శారీస్"), _post(2, 3, "కంచి temple visit")]
    rows, _ = topics.coverage_map(posts, ACCOUNTS, tracked=["కంచి"])
    row = next(r for r in rows if r["tracked"])
    assert row["competitor_posts"] == 1  # only the post with the standalone word


# ---- story matching keeps Telugu titles ----

def test_story_matching_uses_telugu_words():
    assert "కంచిపట్టు" in analysis.clean_title(TELUGU_TITLE)


def test_same_telugu_story_from_two_channels_is_grouped():
    posts = [_post(1, 2, "ధర్మవరం కంచిపట్టు శారీస్ ఆషాడం సేల్", 3),
             _post(2, 3, "ఆషాడం సేల్ ధర్మవరం కంచిపట్టు శారీస్", 2)]
    groups = analysis.group_stories(posts)
    assert len(groups) == 1 and len(groups[0]) == 2