# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`recorrect` calibrates ASR (speech-to-text) lyrics against reference lyrics using DTW dynamic programming alignment. It corrects ASR transcription errors by matching noisy ASR text against clean LRCLIB reference text while preserving ASR timing (SRT/LRC timestamps).

## Commands

```bash
# Run the tool
python -m recorrect <asr_file> <ref_file> [-o OUTPUT_PREFIX] [-f FORMAT]

# Run unit tests (standalone scripts, no framework)
python test_align.py
python test_integration.py
```

No build system, no install step, no external dependencies. Python >= 3.8, stdlib only.

## Architecture

```
__main__.py → cli.py → pipeline.py → aligner.py + similarity.py + io_utils.py
```

### Data flow

1. **Load**: `io_utils.load_asr()` parses `.txt`/`.srt`/`.json` ASR input; `io_utils.load_ref()` loads reference `.txt`
2. **Merge**: `pipeline._merge_short_asr()` joins very short consecutive ASR sentences (< 5 words) that are likely fragments
3. **Normalize**: `similarity.normalize()` strips punctuation, lowercases, collapses whitespace
4. **Align**: `aligner.align()` runs DTW with 5 transition types (see below), returns `[(asr_idx, ref_idx, score, transition), ...]`
5. **Output**: `io_utils.write_*()` produces `.txt`/`.lrc`/`.srt`/`.json`

### DTW alignment (`aligner.py`)

The core algorithm supports five transitions at each DP cell `[i][j]`:

| Transition | Meaning | Formula |
|---|---|---|
| `match` | ASR[i]→Ref[j], sequential progression | `M[i][j] + dp[i-1][j-1]` |
| `repeat` | ASR[i]→Ref[j], same ref as previous ASR line | `M[i][j] + dp[i-1][j]` |
| `jump_back` | ASR[i]→Ref[j], jumping back from best column of row i-1 | `M[i][j] + dp[i-1][best_j]` |
| `skip_asr` | Drop ASR[i] (hallucination/noise) | `SKIP_PENALTY + dp[i-1][j]` |
| `skip_ref` | Drop Ref[j] (unmatched metadata/extra line) | `SKIP_PENALTY + dp[i][j-1]` |

- Similarity matrix is pre-built: entries below `MIN_MATCH_SCORE` (0.2) become `NEG_INF`
- `SKIP_PENALTY` is -0.05
- `jump_back` enables chorus repeats: the reference only needs to contain the chorus once; ASR lines at the second/third chorus occurrence jump back to the chorus ref index

### Similarity (`similarity.py`)

Auto-selects strategy based on script:
- **CJK text**: `SequenceMatcher` character-level ratio, blended with Jaccard for short strings (< 4 chars)
- **Latin text**: 65% character-level + 35% word-overlap Jaccard

### Output blueprint logic (`cli.py`)

The TXT output uses the ASR structure as a blueprint: it preserves the ASR-detected order (including repeats at their ASR positions), deduplicates consecutive identical lines, then inserts unmatched reference lines at positions inferred from their neighbouring matched ref indices.

### Key types

```python
# ASR entry (from load_asr)
{"text": str, "start_time"?: float, "end_time"?: float}

# Corrected entry (from correct_lyrics)
{"text": str, "asr_text": str, "asr_index": int, "ref_index": int,
 "score": float, "is_repeat": bool, "start_time"?: float, "end_time"?: float}

# Pipeline result
{"corrected": list[dict], "unmatched_asr": list[int],
 "unmatched_ref": list[int], "avg_score": float}
```

## Context in broader ecosystem

This package is one component in a lyrics-processing pipeline under `/mnt/d/AiAlign/`:

```
get_lyrics.py (LRCLIB search) → Qwen3-aligner (ASR transcription)
    → recorrect/ (this package: calibrate ASR against reference)
    → upload_song.py (upload to server)
```

Other sibling packages: `generate-lyrics/`, `Qwen3-aligner-main/`, `LyricsAlignment-MTL/`.
