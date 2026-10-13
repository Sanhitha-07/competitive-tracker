"""Word splitting and phrase matching that work in every script.

Python's regex \\w does not count combining marks as part of a word. Indian
scripts (Telugu, Hindi, Tamil, Kannada, Bengali...) write most vowels as
combining marks, so \\w-based rules cut their words apart:
    "కంచిపట్టు" (Kanchipattu)  ->  "క", "చ", ...
This module treats letters, digits and combining marks as word characters,
plus the zero-width joiners that some Indian-script words contain.

All topic, matching and relevance code uses these two functions, so every
part of the app splits text the same way.
"""
import unicodedata

# Zero-width non-joiner / joiner: invisible characters inside some Indic words.
_JOINERS = {"\u200c", "\u200d"}


def _is_word_char(ch):
    if ch in _JOINERS:
        return True
    cat = unicodedata.category(ch)
    # L = letters, N = numbers, M = combining marks (Indic vowel signs, accents).
    # Underscore and other punctuation are excluded, as before.
    return cat[0] in "LNM"


def words(text):
    """Lower-cased words of any script, in order. Joiners at a word's edge are dropped."""
    text = unicodedata.normalize("NFC", (text or "")).lower()
    out, current = [], []
    for ch in text:
        if _is_word_char(ch):
            current.append(ch)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    cleaned = []
    for w in out:
        w = w.strip("".join(_JOINERS))
        # A word must contain at least one letter or digit, not only marks.
        if w and any(unicodedata.category(c)[0] in "LN" for c in w):
            cleaned.append(w)
    return cleaned


def contains_phrase(text, phrase):
    """True if `phrase` appears in `text` as whole words, in order.

    "sale" matches "Aashadam sale!" but not "wholesale"; "కంచి" does not
    match inside "కంచిపట్టు".
    """
    target = words(phrase)
    if not target:
        return False
    hay = words(text)
    n = len(target)
    return any(hay[i:i + n] == target for i in range(len(hay) - n + 1))