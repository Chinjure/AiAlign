# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`recorrect` calibrates ASR (speech-to-text) lyrics against reference lyrics. It corrects ASR transcription errors by matching noisy ASR text against clean LRCLIB reference text while preserving ASR timing (SRT/LRC timestamps).

Two pipelines:
- **Text pipeline** (`correct_lyrics`): ASR `.txt/.srt/.json` + reference `.txt` — probe-matching via sliding-window similarity
- **Dual-LRC pipeline** (`correct_lyrics_lrc`): ASR `.lrc` + reference `.lrc` — time-aware 1:1 matching with merge/split detection

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
__main__.py → cli.py → pipeline.py → similarity.py + io_utils.py
                                       aligner.py (legacy DTW, still exported)
```

### Data flow (text pipeline)

1. **Load**: `io_utils.load_asr()` parses `.txt`/`.srt`/`.json`; `io_utils.load_ref()` loads reference `.txt`
2. **Normalize**: `similarity.normalize()` strips punctuation, lowercases, collapses whitespace; full ASR text joined into one blob
3. **Probe**: `pipeline._find_all_matches()` slides each unique reference line across the ASR blob with stride, collects score peaks
4. **Resolve**: `pipeline._resolve_overlaps()` removes overlapping matches (keep higher score); matches sorted by ASR position → output order
5. **Attach timing**: each match mapped to nearest ASR entry by character position
6. **Output**: `io_utils.write_*()` produces `.txt`/`.lrc`/`.srt`/`.json`

### Data flow (dual-LRC pipeline)

1. **Load**: both ASR and reference as LRC via `io_utils.load_lrc()`
2. **Match**: each ASR line finds best-matching ref line by text similarity (1:1)
3. **Merge detection**: consecutive ASR lines matching same ref AND close in time (< 4s) AND textually similar (> 0.7) → merged to one output line
4. **Split detection**: single ASR line matching combined ref[j]+ref[j+1] better than ref[j] alone (1.2× threshold) → split into two output lines
5. **Output**: ASR order is authoritative; unmatched ASR lines keep original text + timing

### Input handling

- **ASR blob detection**: `_is_continuous_blob()` identifies ASR output with few very-long lines; `_split_sentences()` splits at `. ! ?` boundaries, protecting abbreviations (Mr. Mrs. Dr. etc.)
- **JSON input**: supports both flat arrays and `{"sentences": [...]}` objects; blob entries get sentence-split with proportional timing
- **LRC input**: parses both `[mm:ss.xx]` and `[mm:ss.xxx]` formats

### Similarity (`similarity.py`)

Auto-selects strategy based on script:
- **CJK text**: `SequenceMatcher` character-level ratio, blended with Jaccard for short strings (< 4 chars)
- **Latin text**: 65% character-level + 35% word-overlap Jaccard

Constants: `MIN_MATCH_SCORE = 0.2`, `SKIP_PENALTY = -0.05`

### DTW aligner (`aligner.py`) — legacy, still exported

Original DTW algorithm with 5 transitions: `match`, `repeat`, `jump_back`, `skip_asr`, `skip_ref`. `jump_back` enables chorus repeats by allowing jumps back to the best column of the previous row. Not used by the current pipeline but available via `from recorrect import align`.

### Output blueprint logic (`cli.py`, text pipeline TXT output)

Uses ASR structure as blueprint: preserves ASR-detected order (including repeats), deduplicates consecutive identical lines, inserts unmatched reference lines at positions inferred from neighbouring matched ref indices.

### Key types

```python
# ASR entry (from load_asr)
{"text": str, "start_time"?: float, "end_time"?: float}

# Text pipeline result (from correct_lyrics)
{"corrected": [
    {"text": str, "asr_position": int, "ref_index": int,
     "score": float, "is_repeat": bool, "start_time"?: float, "end_time"?: float}
], "unmatched_ref": list[int], "avg_score": float}

# Dual-LRC pipeline result (from correct_lyrics_lrc)
{"corrected": [
    {"text": str, "start_time": float, "asr_index": int, "ref_index": int,
     "score": float, "is_merge"?: bool, "is_split"?: bool}
], "unmatched": list[int], "avg_score": float}
```

## Context in broader ecosystem

This package is one component in a lyrics-processing pipeline under `/home/user/AiAlign/`:

```
get_lyrics.py (LRCLIB search) → Qwen3-aligner (ASR transcription)
    → recorrect/ (this package: calibrate ASR against reference)
    → upload_song.py (upload to server)
```

Other sibling packages: `generate-lyrics/`, `Qwen3-aligner-main/`, `LyricsAlignment-MTL/`.
