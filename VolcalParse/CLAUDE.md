# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment constraints

- **Windows PowerShell only** — all commands must run in PowerShell on Windows. Do NOT use WSL or bash.
- **No cross-system interaction** — do not reference WSL paths or interact with WSL filesystem.
- **Local dependencies only** — all packages install under the current project directory (e.g. `.venv`), never system-wide.

## Project overview

VocalParse 是一个基于 Qwen3-ASR-1.7B 的歌唱声音转录系统,将歌唱音频转为统一的 AST (Automatic Singing Transcription) token 序列,在单一 LALM 解码器中同时输出歌词、音高 (MIDI)、音符时值、BPM。核心思路是在 Qwen3-ASR 词表上扩展约 400 个 AST token (128 pitch + 12 note + 256 BPM)。

## Common commands

```powershell
# Install (recommended: uv, in project directory)
uv venv --python 3.10
.\.venv\Scripts\activate
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
uv pip install -e .              # standard (PyTorch SDPA)
uv pip install -e ".[flash]"    # with flash-attn

# Preprocess data (mel → Arrow, zero audio I/O during training)
python scripts/preprocess.py --config configs/preprocess.yaml --num_workers 16

# Single-GPU training
python -m vocalparse.train --config configs/train.yaml

# Multi-GPU training (DDP)
torchrun --nproc_per_node=2 -m vocalparse.train --config configs/train.yaml

# Single-sample inference (quick demo)
python -m vocalparse.demo --audio path/to/song.wav --checkpoint ./vocalparse-weights

# Batch inference benchmark (multi-GPU via torchrun)
torchrun --nproc_per_node=4 scripts/benchmark_api.py \
    --checkpoint /path/to/vocalparse \
    --json data/Opencpop.json --audio_root /path/to/Opencpop

# Transcribe song vocals to lyrics (faster-whisper)
python scripts/tran_whisper.py <audio> -l en -m small
```

**Training auto-resumes**: if `output_dir` contains `checkpoint-*`, training picks up from the latest one. To start fresh, change `output_dir`.

## Architecture

```
vocalparse/
  __init__.py       — Pure-Python helpers are eager-imported; heavy symbols (model, API, demo)
                      are lazy via PEP 562 __getattr__ so downstream can use parsing/metrics
                      without pulling in torch/transformers/qwen-asr.
  tokens.py         — AST token definitions: 128 pitch, 12 note, 256 BPM, duration map
  prompts.py        — Annotation→syllable conversion, interleaved text builder, chat prefix builder
  evaluation.py     — AST text parser, word aggregation (melisma grouping), Needleman-Wunsch
                      alignment, per-sample metrics (CER, pitch/note/dur/bpm MAE), aggregation
  model.py          — Model loading (checkpoint auto-detect, processor from base, safetensors
                      loading), token registration, Whisper encoder length helper, audio I/O
  demo.py           — transcribe_one(): single wav in, text out (entry point for newcomers)
  api.py            — VocalParseTranscriber: batch production inference with per-sample mel
                      encoding, CPU-prep ‖ GPU-generate pipeline, cross-rank work-steal
  train.py          — Training entry: loads data (Arrow or raw scan), builds collator, custom
                      Trainer with dynamic batch sampler, auto-resume
  data.py           — Data loading (folder_based / json_file), Arrow Dataset loading, train/val
                      split by dataset_name, two DataCollators (raw audio vs precomputed mel)
  validation.py     — GenerateSamplesCallback: multi-GPU validation via model.generate(),
                      TensorBoard logging (CER/Pitch MAE/Note MAE/Dur MAE/BPM MAE + GT vs Pred
                      score condition figures)
  checkpoint.py     — find_latest_checkpoint, MakeEveryCheckpointInferableCallback (copies HF
                      config files so every checkpoint is directly loadable for inference)
  distributed.py    — DDP init/cleanup, /dev/shm gathering (polling-based, no NCCL barrier),
                      per-sample audio encoding (no cross-sample padding in Conv2d),
                      batch packing (sort by mel frames, within token budget), left-pad utils
scripts/
  preprocess.py     — Mel extraction → Arrow shards with ThreadPoolExecutor; stores trimmed mel
                      (not 30s-padded), serialized syllables JSON, BPM, dataset_name
  benchmark_api.py  — End-to-end VocalParseTranscriber benchmark on Opencpop
  tran_whisper.py   — Song lyrics transcription via faster-whisper (English/multilingual)
data/
  *.json            — Bundled annotations for Opencpop, GTSinger, M4Singer (audio must be
                      obtained separately from official sources)
configs/
  preprocess.yaml   — Preprocessing config: model path, output dir, dataset list
  train.yaml        — Training config: model, data, prompt format (bpm_position, asr_cot),
                      hyperparams, dynamic batching budget, val split
```

### Key architectural patterns

- **Two data paths for training**: (1) `preprocessed_dir` — fast, memory-mapped Arrow with precomputed mel, zero audio I/O; prompt format (bpm_position, asr_cot) is applied online in collator so format changes don't require re-preprocessing. (2) Raw scan — loads audio on-the-fly from NFS, used when no Arrow data exists.
- **Two inference paths**: `transcribe_one` (simple, one file, for beginners) and `VocalParseTranscriber` (batch, multi-GPU work-steal via /dev/shm counter, CPU prep overlapped with GPU generate).
- **Per-sample audio encoding** (`pre_encode_audio_features`): each sample's mel is encoded individually through the Whisper encoder to avoid cross-sample padding Conv2d artifacts. Audio features are then injected into the correct positions in the shared inputs_embeds before the decoder runs.
- **Separator `bpm_position`/`asr_cot`**: these prompt-format settings are baked into training targets. Changing them requires retraining but NOT re-preprocessing (since Arrow stores raw metadata, not tokenized text).
- **Two-layer Needleman-Wunsch alignment** in evaluation: Layer 1 aligns GT/Pred word sequences for CER; Layer 2 aligns pitch/note pairs within aligned words for structural metrics. Same-pitch consecutive pairs are merged (tie resolution) before pair-level alignment.
- **`asr_cot` mode**: training target is `"language Chinese<asr_text>{lyrics}<|file_sep|>{ast_text}"`. At inference with CoT model, the assistant turn is pre-filled with `"language Chinese<asr_text>{GT lyrics}<|file_sep|>"` (audio-lyric inference mode), so the model only generates the AST tail.
