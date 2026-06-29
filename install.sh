#!/bin/bash
set -euo pipefail

# ============================================================
# AiAlign — One-shot setup script
# ============================================================
# Usage:
#   bash install.sh          # Full install (GPU torch)
#   bash install.sh --cpu    # CPU-only torch
# ============================================================

# ── Config ──────────────────────────────────────────────────
# PyTorch CUDA index. Change this to match your CUDA driver:
#   cu130 — CUDA 13.0 (default, RTX 50 series / latest)
#   cu128 — CUDA 12.8
#   cu126 — CUDA 12.6 (older GPUs)
TORCH_INDEX="https://download.pytorch.org/whl/cu130"

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── Helpers ─────────────────────────────────────────────────
BOLD="$(tput bold 2>/dev/null || printf '\033[1m')"
GREEN="$(tput setaf 2 2>/dev/null || printf '\033[32m')"
YELLOW="$(tput setaf 3 2>/dev/null || printf '\033[33m')"
RED="$(tput setaf 1 2>/dev/null || printf '\033[31m')"
RESET="$(tput sgr0 2>/dev/null || printf '\033[0m')"

say()  { printf "%b\n" "${BOLD}$*${RESET}"; }
ok()   { printf "  %b %s\n" "${GREEN}✔${RESET}" "$*"; }
warn() { printf "  %b %s\n" "${YELLOW}⚠${RESET}" "$*"; }
err()  { printf "  %b %s\n" "${RED}✘${RESET}" "$*"; }

# ── CLI ─────────────────────────────────────────────────────
USE_GPU=1
[ "${1:-}" = "--cpu" ] && USE_GPU=0

echo ""
echo "========================================"
echo "   AiAlign Setup"
echo "========================================"
echo ""

# ── Step 1: System dependencies ─────────────────────────────
say "[1/4] System dependencies..."

PKG_MANAGER=""
if command -v apt-get &>/dev/null; then
    PKG_MANAGER="apt"
elif command -v brew &>/dev/null; then
    PKG_MANAGER="brew"
elif command -v pacman &>/dev/null; then
    PKG_MANAGER="pacman"
elif command -v dnf &>/dev/null; then
    PKG_MANAGER="dnf"
fi

# ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg not found."
    case "$PKG_MANAGER" in
        apt)   CMD="sudo apt-get install -y ffmpeg" ;;
        brew)  CMD="brew install ffmpeg" ;;
        pacman) CMD="sudo pacman -S --noconfirm ffmpeg" ;;
        dnf)   CMD="sudo dnf install -y ffmpeg" ;;
        *)
            err "Unknown package manager. Install ffmpeg manually."
            echo "  https://ffmpeg.org/download.html"
            exit 1
            ;;
    esac
    echo "  Running: $CMD"
    $CMD 2>/dev/null && ok "ffmpeg installed  ($(ffmpeg -version 2>&1 | head -1 | awk '{print $3}'))" || {
        err "Could not install ffmpeg automatically. Install it manually:"
        echo "    $CMD"
        exit 1
    }
else
    ok "ffmpeg  ($(ffmpeg -version 2>&1 | head -1 | awk '{print $3}'))"
fi

# Python dev headers (needed for diffq C extension)
if [ ! -f "$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))' 2>/dev/null)/Python.h" ]; then
    warn "Python dev headers missing (needed to build diffq)."
    case "$PKG_MANAGER" in
        apt)   CMD="sudo apt-get install -y python3-dev" ;;
        brew)  ;;  # Homebrew includes headers by default
        pacman) CMD="sudo pacman -S --noconfirm python" ;;
        dnf)   CMD="sudo dnf install -y python3-devel" ;;
        *)
            warn "Unknown package manager. Install python dev headers manually."
            ;;
    esac
    if [ -n "${CMD:-}" ]; then
        echo "  Running: $CMD"
        $CMD 2>/dev/null && ok "python dev headers installed" || \
            warn "Could not install python-dev. The script will work around this."
    fi
fi

# ── Step 2: Python virtual environment ──────────────────────
say "[2/4] Python virtual environment..."

if [ -d "$PROJECT_DIR/venv" ]; then
    warn "venv/ already exists, skipping creation."
else
    python3 -m venv "$PROJECT_DIR/venv"
    ok "venv created"
fi

source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip setuptools wheel -q
ok "pip / setuptools / wheel up-to-date"

# ── Step 3: Core Python dependencies ────────────────────────
say "[3/4] Core Python dependencies..."

pip install -r "$PROJECT_DIR/requirements.txt"

# audio-separator lists diffq as a dependency but it doesn't
# need it at runtime. When python3-dev is missing, diffq fails
# to compile from source. Work around it.
if ! pip install audio-separator 2>/dev/null; then
    warn "audio-separator install failed (likely diffq build error)."
    warn "Installing audio-separator without diffq..."
    pip install "beartype>=0.18.5,<0.19.0" "einops>=0.7" "julius>=0.2" \
        "librosa>=0.9" "ml_collections" "numpy>=1.20" \
        "onnx-weekly>=1.21" "onnx2torch>=1.5" \
        "pydub>=0.25" "pyyaml>=6.0" "requests>=2.25" \
        "resampy>=0.4" "rotary-embedding-torch>=0.6.1,<0.7.0" \
        "samplerate>=0.1" "scipy>=1.9" "six>=1.16" \
        "soundfile>=0.12" "tqdm>=4.65" \
        2>/dev/null
    pip install --no-deps audio-separator
fi

ok "Core packages installed"

# ── Step 4: GPU / CPU deep-learning stack ───────────────────
say "[4/4] Deep-learning stack..."

if [ "$USE_GPU" -eq 1 ] && command -v nvidia-smi &>/dev/null; then
    echo "  GPU detected ($(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1))"
    echo "  Installing torch + torchaudio with CUDA..."
    echo "  Index: $TORCH_INDEX"
    echo ""

    pip install torch torchaudio \
        --index-url "$TORCH_INDEX" \
        --extra-index-url https://pypi.org/simple

    pip install onnxruntime-gpu torchcodec

    ok "torch  ($(python3 -c 'import torch; print(torch.__version__)'))"
    ok "CUDA available: $(python3 -c 'import torch; print(torch.cuda.is_available())')"
else
    if [ "$USE_GPU" -eq 1 ]; then
        warn "nvidia-smi not found. Installing CPU torch."
        warn "Use --cpu to suppress this warning."
    else
        echo "  Installing CPU-only torch..."
    fi
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    pip install torchcodec
    ok "torch  ($(python3 -c 'import torch; print(torch.__version__)'))  (CPU)"
fi

# ── Step 5: Download model weights ──────────────────────────
say "[5/5] Model weights..."

UVR_MODEL="UVR_MDXNET_Main.onnx"
UVR_URL="https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/$UVR_MODEL"
MODEL_DIR="$PROJECT_DIR/SeperateModels"

if [ -f "$MODEL_DIR/$UVR_MODEL" ] && [ "$(stat -c%s "$MODEL_DIR/$UVR_MODEL" 2>/dev/null)" -gt 1000000 ]; then
    ok "UVR MDX-NET model already present ($(du -h "$MODEL_DIR/$UVR_MODEL" | cut -f1))"
else
    echo "  Downloading UVR MDX-NET Main (~64 MB)..."
    echo "  Source: $UVR_URL"
    if wget -q --show-progress --timeout=60 -O "$MODEL_DIR/$UVR_MODEL" "$UVR_URL" 2>/dev/null; then
        ok "UVR MDX-NET Main downloaded ($(du -h "$MODEL_DIR/$UVR_MODEL" | cut -f1))"
    else
        err "Failed to download UVR model. You can download it manually:"
        echo "    wget -O $MODEL_DIR/$UVR_MODEL $UVR_URL"
        echo "  The pipeline will still attempt to download it on first run."
    fi
fi

# ── Done ────────────────────────────────────────────────────
echo ""
say "Setup complete!"
echo ""
echo "  Activate:   source venv/bin/activate"
echo "  Run:        python -m generate-lyrics <music_file>"
echo ""
echo "  Qwen3-ASR model (~4.4 GB) will be auto-downloaded"
echo "  from HuggingFace / ModelScope on your first pipeline run."
echo "  To pre-download it:"
echo ""
echo "    # From HuggingFace:"
echo "    pip install huggingface_hub"
echo "    huggingface-cli download Qwen/Qwen3-ASR-1.7B \\"
echo "      --local-dir Qwen3-aligner-main/Qwen/Qwen3-ASR-1.7B"
echo ""
echo "    # From ModelScope (faster in mainland China):"
echo "    pip install modelscope"
echo "    python -c \"from modelscope import snapshot_download; \\"
echo "      snapshot_download('qwen/Qwen3-ASR-1.7B', \\"
echo "      local_dir='Qwen3-aligner-main/Qwen/Qwen3-ASR-1.7B')\""
echo ""
