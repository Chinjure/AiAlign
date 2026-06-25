"""Text normalization and similarity functions for lyrics matching.

Auto-selects word-level matching for Latin-script text (English) and
character-level matching for CJK text (Chinese).
"""

import re
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    """Normalize text for comparison: strip punctuation, lowercase, collapse whitespace."""
    punct = '，。！？、；：""''（）《》…—・·,.!?;:\"\'()[]{}〈〉/\\-—'
    text = re.sub('[' + re.escape(punct) + r'\s]+', '', text)
    text = text.lower()
    return text


def _is_latin(text: str) -> bool:
    """Check if text is primarily Latin-script (English etc)."""
    if not text:
        return False
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    return latin > cjk and latin > len(text) * 0.3


def similarity(a: str, b: str) -> float:
    """Compute similarity between two text strings (0.0 to 1.0).

    Auto-selects word-level for Latin text, character-level for CJK.
    """
    if not a or not b:
        return 0.0

    if _is_latin(a) and _is_latin(b):
        return _similarity_en(a, b)
    return _similarity_cjk(a, b)


def _similarity_cjk(a: str, b: str) -> float:
    """Character-level similarity for CJK text."""
    seq_score = SequenceMatcher(None, a, b).ratio()
    if len(a) < 4 or len(b) < 4:
        set_a = set(a)
        set_b = set(b)
        if set_a or set_b:
            jac = len(set_a & set_b) / len(set_a | set_b)
        else:
            jac = 0.0
        return 0.6 * seq_score + 0.4 * jac
    return seq_score


def _similarity_en(a: str, b: str) -> float:
    """Hybrid: character-level primary + word-overlap boost for English."""
    words_a = a.split()
    words_b = b.split()

    # Character-level: handles typos, missing letters
    char_score = SequenceMatcher(None, a, b).ratio()

    if not words_a or not words_b:
        return char_score

    # Word overlap boost
    set_a = set(words_a)
    set_b = set(words_b)
    word_jac = len(set_a & set_b) / len(set_a | set_b)

    # Blend: char-level dominant, word overlap as boost
    return 0.65 * char_score + 0.35 * word_jac


MIN_MATCH_SCORE = 0.2
SKIP_PENALTY = -0.05
