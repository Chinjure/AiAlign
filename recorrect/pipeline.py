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
    """Calibrate ASR-transcribed LRC against official-lyric LRC using
    time-stamp probes.

    Each ASR line is matched to the ref line with the closest timestamp
    within the time window (time-probe matching). Each ref line is also
    matched back to its closest ASR line. The intersection of both
    directions produces high-confidence 1:1 pairs. Unmatched ref lines
    are inserted in chronological position.

    Returns:
        corrected:  list[dict]  — {text, start_time, asr_index, ref_index, score,
                                    is_merge, is_split}
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

    # ── Bidirectional time-probe matching ──

    # ASR → ref: each ASR line picks its closest ref by time
    asr_to_ref = {}  # i → j
    for i in range(n_asr):
        t_asr = asr_entries[i]['start_time']
        best_j = -1
        best_dt = time_window + 1
        for j in range(n_ref):
            dt = abs(ref_entries[j]['start_time'] - t_asr)
            if dt < best_dt:
                best_dt = dt
                best_j = j
        if best_dt <= time_window:
            # Only pair if text agrees — pure time match with wrong text
            # is worse than no match (unmatched lines keep ref text+time)
            if similarity(asr_norms[i], ref_norms[best_j]) >= MIN_MATCH_SCORE:
                asr_to_ref[i] = best_j

    # Ref → ASR: each ref line picks its closest ASR by time
    ref_to_asr = {}  # j → i
    for j in range(n_ref):
        t_ref = ref_entries[j]['start_time']
        best_i = -1
        best_dt = time_window + 1
        for i in range(n_asr):
            dt = abs(asr_entries[i]['start_time'] - t_ref)
            if dt < best_dt:
                best_dt = dt
                best_i = i
        if best_dt <= time_window:
            if similarity(asr_norms[best_i], ref_norms[j]) >= MIN_MATCH_SCORE:
                ref_to_asr[j] = best_i

    # ── Build output in ref order ──
    corrected = []
    matched_refs = set()
    scores = []

    # Group: ref → list of ASR indices that claim it
    ref_claimed_by = {}  # j → [i, ...]
    for i, j in asr_to_ref.items():
        if j not in ref_claimed_by:
            ref_claimed_by[j] = []
        ref_claimed_by[j].append(i)

    # Group: ASR → list of ref indices that claim it
    asr_claimed_by = {}  # i → [j, ...]
    for j, i in ref_to_asr.items():
        if i not in asr_claimed_by:
            asr_claimed_by[i] = []
        asr_claimed_by[i].append(j)

    j = 0
    while j < n_ref:
        if j not in ref_to_asr:
            # Ref has no close ASR — insert with ref time, ref text
            corrected.append({
                'text': ref_entries[j]['text'],
                'start_time': ref_entries[j]['start_time'],
                'asr_index': -1,
                'ref_index': j,
                'score': 0.0,
                'is_merge': False,
                'is_split': False,
            })
            j += 1
            continue

        i = ref_to_asr[j]  # ASR that ref j claims as closest

        # Check SPLIT: does this ASR get claimed by multiple consecutive refs
        # AND does the ASR text have reasonable similarity to each ref?
        if i in asr_claimed_by and len(asr_claimed_by[i]) > 1:
            split_refs = sorted(asr_claimed_by[i])
            is_consecutive = all(
                split_refs[k] == split_refs[0] + k for k in range(len(split_refs))
            )
            if is_consecutive and j == split_refs[0]:
                # Verify: ASR text must be similar to every ref in the split
                all_sims = [similarity(asr_norms[i], ref_norms[sj]) for sj in split_refs]
                if all(s >= MIN_MATCH_SCORE for s in all_sims):
                    for sj in split_refs:
                        corrected.append({
                            'text': ref_entries[sj]['text'],
                            'start_time': ref_entries[sj]['start_time'],
                            'asr_index': i,
                            'ref_index': sj,
                            'score': all_sims[split_refs.index(sj)],
                            'is_merge': False,
                            'is_split': True,
                        })
                        matched_refs.add(sj)
                        scores.append(all_sims[split_refs.index(sj)])
                    j = split_refs[-1] + 1
                    continue

        # Check MERGE: do multiple ASR lines claim this ref?
        is_merge = j in ref_claimed_by and len(ref_claimed_by[j]) > 1
        # Use earliest ASR time among the merged ASR lines
        start_t = ref_entries[j]['start_time']  # default: ref time
        if is_merge:
            merged_asr_indices = ref_claimed_by[j]
            start_t = min(asr_entries[ai]['start_time'] for ai in merged_asr_indices)

        text_sim = similarity(asr_norms[i], ref_norms[j])
        corrected.append({
            'text': ref_entries[j]['text'],
            'start_time': start_t,
            'asr_index': i,
            'ref_index': j,
            'score': text_sim,
            'is_merge': is_merge,
            'is_split': False,
        })
        matched_refs.add(j)
        scores.append(text_sim)
        j += 1

    unmatched = [j for j in range(n_ref) if j not in matched_refs]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        'corrected': corrected,
        'unmatched': unmatched,
        'avg_score': avg_score,
    }
