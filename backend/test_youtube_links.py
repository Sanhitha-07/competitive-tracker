"""Checks that every common kind of YouTube link is understood. Run with:  python -m pytest -q
(No internet needed: this only checks how links are read, not the API calls.)"""
import pytest

from youtube import _lookups

CASES = {
    "@mkbhd": ("channels", {"forHandle": "@mkbhd"}),
    "mkbhd": ("channels", {"forHandle": "@mkbhd"}),
    "https://www.youtube.com/@mkbhd": ("channels", {"forHandle": "@mkbhd"}),
    "https://www.youtube.com/@mkbhd/videos": ("channels", {"forHandle": "@mkbhd"}),
    "youtube.com/@mkbhd": ("channels", {"forHandle": "@mkbhd"}),
    "https://m.youtube.com/@mkbhd": ("channels", {"forHandle": "@mkbhd"}),
    "https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ": ("channels", {"id": "UCBJycsmduvYEL83R_U4JriQ"}),
    "UCBJycsmduvYEL83R_U4JriQ": ("channels", {"id": "UCBJycsmduvYEL83R_U4JriQ"}),
    "https://www.youtube.com/user/marquesbrownlee": ("channels", {"forUsername": "marquesbrownlee"}),
    "https://www.youtube.com/c/mkbhd": ("channels", {"forHandle": "@mkbhd"}),
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ": ("video", "dQw4w9WgXcQ"),
    "https://youtu.be/dQw4w9WgXcQ?si=abc": ("video", "dQw4w9WgXcQ"),
    "https://www.youtube.com/shorts/abcDEF12345": ("video", "abcDEF12345"),
    "https://www.youtube.com/results?search_query=shivatube": ("channels", {"forHandle": "@shivatube"}),
    "https://www.youtube.com/results?search_query=shiva+tube+telugu": ("search", "shiva tube telugu"),
    "Shiva Tube": ("search", "Shiva Tube"),
}


@pytest.mark.parametrize("text,first", CASES.items())
def test_link_is_understood(text, first):
    assert _lookups(text)[0] == first


def test_non_channel_link_gives_clear_error():
    with pytest.raises(ValueError, match="doesn't point to a channel"):
        _lookups("https://www.youtube.com/feed/trending")


@pytest.mark.parametrize("text,expected", [
    ("How long should I rest between sets?", True),
    ("what mic do you use for streaming", True),
    ("Great video, thanks!", False),
    ("Is this good? https://spam.example/x", False),  # links are skipped
    ("why?", False),  # too short to be useful
])
def test_question_detection(text, expected):
    from youtube import looks_like_question
    assert looks_like_question(text) is expected
