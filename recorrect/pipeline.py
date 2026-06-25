"""Pipeline: probe-match reference lines into ASR text.

Algorithm:
  1. Deduplicate reference lyrics → unique probes (preserving first-seen order)
  2. Join all ASR text into one normalized blob
  3. For each probe, find ALL matching positions in the ASR blob
  4. Sort matches by ASR position → output order
  5. Resolve overlapping matches (keep higher score)
"""

from difflib import SequenceMatcher

from .similarity import normalize, similarity, MIN_MATCH_SCORE
from .io_utils import load_asr, load_ref, has_timing, load_lrc


def _find_all_matches(asr_norm: str, ref_norm: str, min_score: float = None) -> list[tuple[int, float]]:
    """Find all positions where ref_norm matches within asr_norm.

    Uses a sliding window across the full ASR text, scoring similarity
    at each position. This avoids the bias of find_longest_match which
    can anchor to common substrings in the wrong sentence.

    Returns list of (asr_char_position, score), sorted by position.
    """
    if min_score is None:
        min_score = MIN_MATCH_SCORE
    if not ref_norm or not asr_norm:
        return []

    ref_len = len(ref_norm)
    asr_len = len(asr_norm)
    window_margin = 15  # extra chars on each side for context
    stride = max(1, ref_len // 4)  # step size

    # Phase 1: scan with sliding window, collect all scores above threshold
    raw = []  # (pos, score)
    pos = 0
    while pos < asr_len:
        window_start = max(0, pos - window_margin)
        window_end = min(asr_len, pos + ref_len + window_margin)
        score = similarity(asr_norm[window_start:window_end], ref_norm)
        if score >= min_score:
            raw.append((pos, score))
        pos += stride

    if not raw:
        return []

    # Phase 2: find local maxima — peaks in the score landscape
    peaks = []
    i = 0
    while i < len(raw):
        # Find the best score within a neighbourhood of ref_len chars
        best_pos, best_score = raw[i]
        j = i + 1
        while j < len(raw) and raw[j][0] - raw[i][0] < ref_len:
            if raw[j][1] > best_score:
                best_pos, best_score = raw[j]
            j += 1
        peaks.append((best_pos, best_score))
        i = j

    return peaks


def _resolve_overlaps(matches: list[dict], asr_norm: str) -> list[dict]:
    """When two matches overlap significantly in the ASR, keep the higher-scored one."""
    if len(matches) <= 1:
        return matches

    matches = sorted(matches, key=lambda m: m['asr_pos'])
    resolved = []

    for m in matches:
        m_len = len(normalize(m['text']))
        m_end = m['asr_pos'] + m_len

        if resolved:
            last = resolved[-1]
            last_len = len(normalize(last['text']))
            last_end = last['asr_pos'] + last_len
            overlap = min(m_end, last_end) - max(m['asr_pos'], last['asr_pos'])
            if overlap > 0 and overlap > min(m_len, last_len) * 0.5:
                if m['score'] > last['score']:
                    resolved[-1] = m
                continue

        resolved.append(m)

    return resolved


def correct_lyrics(asr_input: str, ref_input: str, merge_fragments: bool = True) -> dict:
    """Calibrate ASR lyrics against reference lyrics using probe matching.

    Each unique reference line is independently searched in the full ASR text.
    This avoids the problem where ASR punctuation merges multiple lyric lines
    into one sentence, causing the DTW to lose lines.

    Args:
        asr_input: path to ASR output (.txt/.srt/.json)
        ref_input: path to reference lyrics (.txt)

    Returns:
        corrected: list[dict]  — text, asr_position, score, ref_index, is_repeat, start_time?, end_time?
        unmatched_ref: list[int] — reference lines with no ASR match
        avg_score: float
    """
    asr_entries = load_asr(asr_input)
    ref_lines = load_ref(ref_input)

    if not asr_entries or not ref_lines:
        return {'corrected': [], 'unmatched_ref': [], 'avg_score': 0.0}

    # 1. Deduplicate reference lines, preserving first-seen order
    unique_refs = list(dict.fromkeys(ref_lines))

    # Map: unique index → first original ref_index
    ref_first_occurrence = {}
    for uidx, text in enumerate(unique_refs):
        for oidx, otext in enumerate(ref_lines):
            if otext == text:
                ref_first_occurrence[uidx] = oidx
                break

    # 2. Join all ASR text into one normalized blob
    asr_norm = ' '.join(normalize(e['text']) for e in asr_entries)

    # 3. For each unique ref line, find all matching positions in the ASR
    all_matches = []
    matched_texts = set()

    for uidx, ref_text in enumerate(unique_refs):
        ref_norm = normalize(ref_text)
        if not ref_norm:
            continue
        positions = _find_all_matches(asr_norm, ref_norm)
        if positions:
            matched_texts.add(ref_text)
        for pos, score in positions:
            all_matches.append({
                'text': ref_text,
                'asr_pos': pos,
                'score': score,
                'ref_index': ref_first_occurrence[uidx],
            })

    if not all_matches:
        return {'corrected': [], 'unmatched_ref': list(range(len(ref_lines))), 'avg_score': 0.0}

    # 4. Sort by ASR position, resolve overlaps
    all_matches.sort(key=lambda m: m['asr_pos'])
    resolved = _resolve_overlaps(all_matches, asr_norm)

    # 5. Mark repeats and attach timing
    ref_occurrence_count = {}
    corrected = []
    char_pos = 0
    asr_entry_idx = 0

    for m in resolved:
        ridx = m['ref_index']
        count = ref_occurrence_count.get(ridx, 0)
        ref_occurrence_count[ridx] = count + 1

        entry = {
            'text': m['text'],
            'asr_position': m['asr_pos'],
            'ref_index': m['ref_index'],
            'score': m['score'],
            'is_repeat': count > 0,
        }

        # Attach timing from nearest ASR entry by character position
        for ei, asr_entry in enumerate(asr_entries):
            entry_len = len(normalize(asr_entry['text']))
            if char_pos <= m['asr_pos'] < char_pos + entry_len + 5:
                if 'start_time' in asr_entry:
                    entry['start_time'] = asr_entry['start_time']
                if 'end_time' in asr_entry:
                    entry['end_time'] = asr_entry['end_time']
                break
            char_pos += entry_len + 1  # +1 for joining space

        corrected.append(entry)

    # 6. Unmatched ref lines: any whose text was never found in the ASR
    unmatched_ref = [j for j, text in enumerate(ref_lines)
                     if text not in matched_texts]

    avg_score = sum(m['score'] for m in resolved) / len(resolved) if resolved else 0.0

    return {
        'corrected': corrected,
        'unmatched_ref': unmatched_ref,
        'avg_score': avg_score,
    }


# ── LRC-to-LRC time-probe matching ──

TIME_WINDOW = 3.0       # seconds — max time gap for matching


def correct_lyrics_lrc(asr_lrc_path: str, ref_lrc_path: str,
                       time_window: float = TIME_WINDOW) -> dict:
    """Calibrate ASR-transcribed LRC against reference LRC using text matching.

    Strategy: ASR order is authoritative (reflects actual song structure).
    Reference provides correct words. Each ASR line is matched to its best
    reference counterpart by text similarity. ASR lines are never discarded.
    Timestamps come from the ASR.

    Returns:
        corrected:  list[dict]  — {text, start_time, asr_index, ref_index, score}
        unmatched:  list[int]   — ref indices with no ASR match
        avg_score:  float
    """
    asr_entries = load_lrc(asr_lrc_path)
    ref_entries = load_lrc(ref_lrc_path)

    if not asr_entries or not ref_entries:
        return {'corrected': [], 'unmatched': [], 'avg_score': 0.0}

    n_asr = len(asr_entries)
    n_ref = len(ref_entries)

    asr_norms = [normalize(e['text']) for e in asr_entries]
    ref_norms = [normalize(e['text']) for e in ref_entries]

    # ── Text-based matching: ASR → Ref by similarity ──

    # For each ASR line, find best-matching ref line (purely by text)
    asr_to_ref = {}  # i → j  (1:1 best match)
    matched_refs = set()
    scores = []

    for i in range(n_asr):
        best_j = -1
        best_score = 0.0
        for j in range(n_ref):
            s = similarity(asr_norms[i], ref_norms[j])
            if s > best_score:
                best_score = s
                best_j = j
        if best_score >= MIN_MATCH_SCORE:
            asr_to_ref[i] = best_j
            matched_refs.add(best_j)
            scores.append(best_score)

    # ── Build output in ASR order ──

    corrected = []
    i = 0
    while i < n_asr:
        if i not in asr_to_ref:
            # ASR line has no good ref match — keep ASR text + time
            corrected.append({
                'text': asr_entries[i]['text'],
                'start_time': asr_entries[i]['start_time'],
                'asr_index': i,
                'ref_index': -1,
                'score': 0.0,
            })
            i += 1
            continue

        j = asr_to_ref[i]  # best ref match for this ASR line

        # Check MERGE: do consecutive ASR lines match the same ref,
        # look textually similar, AND are close in time?
        # (Close = ASR artifact; far apart = real repeated lyric)
        merge_count = 1
        k = i + 1
        while k < n_asr and asr_to_ref.get(k) == j:
            dt = asr_entries[k]['start_time'] - asr_entries[k - 1]['start_time']
            if dt > 4.0 or similarity(asr_norms[k], asr_norms[i]) < 0.7:
                break
            merge_count += 1
            k += 1

        if merge_count > 1:
            corrected.append({
                'text': ref_entries[j]['text'],
                'start_time': asr_entries[i]['start_time'],
                'asr_index': i,
                'ref_index': j,
                'score': similarity(asr_norms[i], ref_norms[j]),
                'is_merge': True,
                'is_split': False,
            })
            i += merge_count
            continue

        # Check SPLIT: does this ASR match multiple consecutive refs better?
        # ASR text similarity to ref[j] vs ref[j]+ref[j+1] combined
        if j + 1 < n_ref:
            combined_ref = ref_norms[j] + ' ' + ref_norms[j + 1]
            if similarity(asr_norms[i], combined_ref) > similarity(asr_norms[i], ref_norms[j]) * 1.2:
                # ASR merges two ref lines — split them
                for sj in (j, j + 1):
                    corrected.append({
                        'text': ref_entries[sj]['text'],
                        'start_time': asr_entries[i]['start_time'],
                        'asr_index': i,
                        'ref_index': sj,
                        'score': similarity(asr_norms[i], ref_norms[sj]),
                        'is_merge': False,
                        'is_split': True,
                    })
                    matched_refs.add(sj)
                i += 1
                continue

        # Default: 1:1 match
        corrected.append({
            'text': ref_entries[j]['text'],
            'start_time': asr_entries[i]['start_time'],
            'asr_index': i,
            'ref_index': j,
            'score': similarity(asr_norms[i], ref_norms[j]),
            'is_merge': False,
            'is_split': False,
        })
        i += 1

    unmatched = [j for j in range(n_ref) if j not in matched_refs]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        'corrected': corrected,
        'unmatched': unmatched,
        'avg_score': avg_score,
    }
