"""DTW-based sequence alignment for ASR → reference lyrics matching.

Supports five transitions:
  match     — ASR[i]→Ref[j], ASR[i-1]→Ref[j-1] (sequential)
  repeat    — ASR[i]→Ref[j], ASR[i-1]→Ref[j]   (same line repeated)
  jump_back — ASR[i]→Ref[j], ASR[i-1]→best     (jump back, chorus restart)
  skip_asr  — drop ASR[i] (hallucination)
  skip_ref  — drop Ref[j]  (unmatched reference line)
"""

from .similarity import similarity, MIN_MATCH_SCORE, SKIP_PENALTY

NEG_INF = float('-inf')
TERMINAL = (-1, -1)


def build_similarity_matrix(asr_texts: list[str], ref_texts: list[str]) -> list[list[float]]:
    n, m = len(asr_texts), len(ref_texts)
    M = [[NEG_INF] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            s = similarity(asr_texts[i], ref_texts[j])
            if s >= MIN_MATCH_SCORE:
                M[i][j] = s
    return M


def align(asr_texts: list[str], ref_texts: list[str]) -> list[tuple]:
    """Run DTW alignment with jump-back support for chorus repeats.

    Returns list of (asr_idx, ref_idx, score, transition) in forward order.
    """
    n = len(asr_texts)
    m = len(ref_texts)
    if n == 0 or m == 0:
        return []

    M = build_similarity_matrix(asr_texts, ref_texts)

    dp = [[NEG_INF] * m for _ in range(n)]
    bp = [[None] * m for _ in range(n)]
    best_j = [0] * n

    # ---- Row 0: ASR[0] matches at most one ref (the best) ----
    best_j0 = max(range(m), key=lambda j: M[0][j] if M[0][j] > NEG_INF else NEG_INF)
    if M[0][best_j0] > NEG_INF:
        # Best match will be used; all others are skips
        pass
    else:
        best_j0 = -1  # no match for ASR[0]

    # Column 0
    if best_j0 == 0:
        dp[0][0] = M[0][0]
        bp[0][0] = (TERMINAL, 'match')
    else:
        dp[0][0] = SKIP_PENALTY
        bp[0][0] = (TERMINAL, 'skip_ref')

    for j in range(1, m):
        candidates = []
        if j == best_j0:
            candidates.append((M[0][j] + dp[0][j - 1], ((0, j - 1), 'match')))
        candidates.append((SKIP_PENALTY + dp[0][j - 1], ((0, j - 1), 'skip_ref')))
        best = max(candidates, key=lambda x: x[0])
        dp[0][j] = best[0]
        bp[0][j] = best[1]

    best_j[0] = _argmax(dp[0])

    # ---- Rows 1..n-1 ----
    for i in range(1, n):
        best_prev = dp[i - 1][best_j[i - 1]]
        best_prev_j = best_j[i - 1]

        # Column 0
        candidates = []
        if M[i][0] > NEG_INF:
            candidates.append((M[i][0] + dp[i - 1][0], ((i - 1, 0), 'repeat')))
            candidates.append((M[i][0] + best_prev, ((i - 1, best_prev_j), 'jump_back')))
        candidates.append((SKIP_PENALTY + dp[i - 1][0], ((i - 1, 0), 'skip_asr')))
        best = max(candidates, key=lambda x: x[0])
        dp[i][0] = best[0]
        bp[i][0] = best[1]

        # Columns 1..m-1
        for j in range(1, m):
            candidates = []

            if M[i][j] > NEG_INF:
                candidates.append((M[i][j] + dp[i - 1][j], ((i - 1, j), 'repeat')))
                candidates.append((M[i][j] + dp[i - 1][j - 1], ((i - 1, j - 1), 'match')))
                candidates.append((M[i][j] + best_prev, ((i - 1, best_prev_j), 'jump_back')))

            candidates.append((SKIP_PENALTY + dp[i - 1][j], ((i - 1, j), 'skip_asr')))
            candidates.append((SKIP_PENALTY + dp[i][j - 1], ((i, j - 1), 'skip_ref')))

            best = max(candidates, key=lambda x: x[0])
            dp[i][j] = best[0]
            bp[i][j] = best[1]

        best_j[i] = _argmax(dp[i])

    return _backtrack(M, bp, n - 1, best_j[-1])


def _argmax(arr):
    return max(range(len(arr)), key=lambda j: arr[j])


def _backtrack(M, bp, end_i, end_j):
    alignment = []
    i, j = end_i, end_j
    while i >= 0 and j >= 0:
        (prev_pos, trans) = bp[i][j]
        score = 0.0
        if trans in ('match', 'repeat', 'jump_back'):
            score = M[i][j] if M[i][j] > NEG_INF else 0.0
        alignment.append((i, j, score, trans))

        if prev_pos == TERMINAL:
            break
        i, j = prev_pos

    alignment.reverse()
    return alignment


def get_matched_lines(alignment: list[tuple]) -> list[dict]:
    result = []
    for asr_idx, ref_idx, score, trans in alignment:
        if trans in ('match', 'repeat', 'jump_back'):
            result.append({
                'asr_index': asr_idx,
                'ref_index': ref_idx,
                'score': score,
                'is_repeat': trans in ('repeat', 'jump_back'),
            })
    return result


def get_unmatched_asr(alignment: list[tuple], n_asr: int) -> list[int]:
    matched = {item[0] for item in alignment if item[3] in ('match', 'repeat', 'jump_back')}
    return [i for i in range(n_asr) if i not in matched]


def get_unmatched_ref(alignment: list[tuple], n_ref: int) -> list[int]:
    matched = {item[1] for item in alignment if item[3] in ('match', 'repeat', 'jump_back')}
    return [j for j in range(n_ref) if j not in matched]
