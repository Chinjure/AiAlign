# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AiAlign is an end-to-end lyrics pipeline: extract metadata → search LRCLIB → separate vocals (UVR MDX-NET) → transcribe (Qwen3-ASR 1.7B) → calibrate against reference lyrics (recorrect) → align to LRC (MTL_BDR) → optionally upload to music server.

## Environment

- **Linux (WSL2)** — all commands run in bash. The project was recently migrated from Windows (commit `64b93be`), so some subproject docs still reference PowerShell paths — ignore those.
- **Python venv** at `venv/` — activate with `source venv/bin/activate`
- **System dependency**: `ffmpeg` (apt-installed)

## Common commands

```bash
# Activate venv
source venv/bin/activate

# End-to-end LRC generation (single file)
python -m generate-lyrics <music_file> [-o output_dir] [--keep] [--upload]

# End-to-end (batch)
python -m generate-lyrics --batch <dir> [--keep]

# Run a single step manually:
python vocal_separate.py <audio> [output_dir]           # Vocal separation
python -m recorrect <asr_file> <ref_file> -o out -f all  # ASR calibration
python align_one.py <vocal_wav> <lyrics_txt> [output_lrc] # Lyrics alignment
python upload_song.py <music_file> [--lrc <lrc>] [--server URL]

# recorrect tests (stdlib only, no framework)
cd recorrect && python test_align.py && python test_integration.py

# Qwen3-aligner: transcribe vocals
python Qwen3-aligner-main/cli.py transcribe <audio> -l English -m 1.7B -o output.txt
```

## Architecture

```
music file
  │
  ├─ vocal_separate.py ──→ SeperateModels/UVR_MDXNET_Main.onnx ──→ _(Vocals).wav
  ├─ Qwen3-aligner-main/cli.py ──→ Qwen3-ASR 1.7B ──→ _transcribed.txt
  ├─ recorrect/ (ASR calibration)
  │     ├─ text pipeline:  ASR .txt/.srt/.json + ref .txt → similarity probe-matching
  │     └─ dual-LRC pipeline: ASR .lrc + ref .lrc → time-aware 1:1 matching + merge/split
  ├─ align_one.py ──→ LyricsAlignment-MTL/ (MTL_BDR, CPU) ──→ .lrc
  └─ upload_song.py ──→ POST /api/upload
```

### Top-level scripts

| File | Role |
|------|------|
| `generate-lyrics/` | Main entry point — orchestrates the full pipeline |
| `get_lyrics.py` | Standalone script variant (same workflow, less cleanup logic) |
| `vocal_separate.py` | Wrapper around `audio-separator` CLI with fixed MDX-NET config |
| `align_one.py` | Vocal WAV + lyrics TXT → MTL_BDR alignment → CSV → LRC |
| `batch_align_lrc.py` | Batch version; imports MTL wrapper directly (in-process) |
| `upload_song.py` | Multipart POST audio + LRC to music server |

### Key packages

- **`recorrect/`** — ASR→reference lyric calibration. Stdlib only, two pipelines (text + dual-LRC). Entry: `python -m recorrect`. See `recorrect/CLAUDE.md` for detailed architecture.
- **`generate-lyrics/`** — End-to-end orchestrator. Each pipeline step returns `(ok, result, [tracked_files])`; a `Cleaner` accumulates tracked files for rollback on fatal errors. Non-fatal steps (search, correct, upload) warn and continue.
- **`Qwen3-aligner-main/`** — Qwen3-ASR 1.7B transcription. `cli.py transcribe` subcommand.
- **`LyricsAlignment-MTL/`** — MTL_BDR forced alignment model. `wrapper.py` exposes `align()`, `preprocess_from_file()`, `write_csv()`. `csv2lrc.py` converts alignment CSV to LRC.
- **`VolcalParse/`** — Singing voice transcription to AST tokens (lyrics + pitch + note + BPM). Separate research project, not in the main pipeline. See `VolcalParse/CLAUDE.md`.

### recorrect pipelines (high-level)

The recorrect package has two distinct matching strategies:
1. **Text pipeline** (`correct_lyrics`): slides reference lines across ASR blob, scores similarity, resolves overlaps. Input: ASR `.txt`/`.srt`/`.json` + reference `.txt`.
2. **Dual-LRC pipeline** (`correct_lyrics_lrc`): both inputs as LRC → 1:1 time-aware matching with merge (consecutive ASR lines matching same ref) and split (single ASR line matching combined ref[j]+ref[j+1]) detection. Used by `generate-lyrics` for higher accuracy.

### generate-lyrics correction flow

When `generate-lyrics` runs with correction (the default path):
1. Aligns transcribed text → LRC (step_align on ASR output)
2. Aligns reference lyrics → LRC (step_align on LRCLIB output)
3. Feeds both LRCs to `recorrect` dual-LRC pipeline → corrected `.txt`
4. That corrected `.txt` is then used for the final alignment → LRC

This ensures time-aware matching rather than pure text similarity.

### Python environments

The project is self-contained in `venv/`. The Windows version used separate conda environments (`aligner_cpu` Python 3.10 for separation/transcription, `lyrics_align` Python 3.9 for alignment) — these are no longer relevant on Linux.

## Git-managed model weights

Large files are `.gitignore`d and must be obtained separately:
- `SeperateModels/UVR_MDXNET_Main.onnx`
- `LyricsAlignment-MTL/checkpoints/checkpoint_MTL` and `checkpoint_BDR`
- `Qwen3-aligner-main/FireRedVAD/model.pth.tar`
- `Qwen3-aligner-main/Qwen/` (model weights)
- `VolcalParse/vocalparse-weights/`
