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
    """Hybrid: character-level primary + trigram-overlap boost for English.

    Uses character trigrams instead of word overlap because input text
    is pre-normalized (no spaces), making word-split useless.
    """
    # Character-level: handles typos, missing letters
    char_score = SequenceMatcher(None, a, b).ratio()

    # Character trigram overlap — works with or without spaces
    def _trigrams(s):
        return {s[i:i + 3] for i in range(len(s) - 2)}

    tri_a = _trigrams(a)
    tri_b = _trigrams(b)
    if tri_a and tri_b:
        tri_jac = len(tri_a & tri_b) / len(tri_a | tri_b)
    else:
        tri_jac = 0.0

    # Blend: char-level dominant, trigram overlap as boost
    return 0.65 * char_score + 0.35 * tri_jac


MIN_MATCH_SCORE = 0.2
SKIP_PENALTY = -0.05
FULL_TEXT_SIMILARITY_THRESHOLD = 0.9


def full_text_similarity(corrected_lines: list[str], ref_lines: list[str]) -> float:
    """Compare corrected output against reference at full-text level.

    Joins both into normalized strings and computes similarity.
    Returns 0.0-1.0.
    """
    corrected_blob = ''.join(normalize(l) for l in corrected_lines)
    ref_blob = ''.join(normalize(l) for l in ref_lines)
    if not corrected_blob or not ref_blob:
        return 0.0
    return similarity(corrected_blob, ref_blob)
