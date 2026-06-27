#!/bin/bash
set -euo pipefail

# ============================================================
# AiAlign — One-shot setup script
# ============================================================
# Usage:
#   bash install.sh               # Full install (GPU torch + models)
#   bash install.sh --cpu         # CPU-only torch
#   bash install.sh --no-models   # Skip small model download
# ============================================================

# ── Config ──────────────────────────────────────────────────
# PyTorch CUDA index. Change this to match your CUDA driver:
#   cu130 — CUDA 13.0 (default, for RTX 50 series / latest)
#   cu128 — CUDA 12.8
#   cu126 — CUDA 12.6 (older GPUs)
TORCH_INDEX="https://download.pytorch.org/whl/cu130"

# GitHub Releases URL for small model files (tar.gz assets).
# Users MUST update this before releasing.
REPO_URL="${AIMODELS_URL:-https://github.com/YOUR_USERNAME/YOUR_REPO/releases/download/v1.0.0}"

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

check_file() {
    local path="$PROJECT_DIR/$1"
    if [ -f "$path" ]; then
        ok "$1  ($(du -h "$path" | cut -f1))"
    else
        err "$1  MISSING"
        return 1
    fi
}

download() {
    local url="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    if command -v wget &>/dev/null; then
        wget -q --show-progress -O "$dest" "$url"
    elif command -v curl &>/dev/null; then
        curl -fSL --progress-bar -o "$dest" "$url"
    else
        err "Neither wget nor curl found. Install one and re-run."
        return 1
    fi
}

# ── CLI ─────────────────────────────────────────────────────
USE_GPU=1
DOWNLOAD_MODELS=1

for arg in "${@:-}"; do
    case "$arg" in
        --cpu)       USE_GPU=0 ;;
        --no-models) DOWNLOAD_MODELS=0 ;;
    esac
done

echo ""
echo "========================================"
echo "   AiAlign Setup"
echo "========================================"
echo ""

# ── Step 1: System dependencies ─────────────────────────────
say "[1/5] System dependencies..."

# Detect package manager
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
            err "Unknown package manager. Please install ffmpeg manually."
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

# Python dev headers (for diffq)
if [ ! -f "$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))' 2>/dev/null)/Python.h" ]; then
    warn "Python dev headers missing (needed to build diffq)."
    case "$PKG_MANAGER" in
        apt)   CMD="sudo apt-get install -y python3-dev" ;;
        brew)  ;;  # Homebrew python includes headers by default
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
say "[2/5] Python virtual environment..."

PYTHON_BIN="python3"
if [ -d "$PROJECT_DIR/venv" ]; then
    warn "venv/ already exists, skipping creation."
else
    $PYTHON_BIN -m venv "$PROJECT_DIR/venv"
    ok "venv created"
fi

source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip setuptools wheel -q
ok "pip / setuptools / wheel up-to-date"

# ── Step 3: Core Python dependencies ────────────────────────
say "[3/5] Core Python dependencies..."

# First pass: install everything except audio-separator.
# audio-separator lists diffq as a dependency, which needs C
# compilation (no pre-built wheel). When python3-dev is missing,
# diffq fails — but it's not actually needed at runtime.
pip install -r "$PROJECT_DIR/requirements.txt"

# Install audio-separator. If diffq build fails, install without it
# (the pipeline doesn't use diffq at runtime).
if ! pip install audio-separator 2>/dev/null; then
    warn "audio-separator install failed (likely diffq build error)."
    warn "Installing audio-separator without diffq..."
    # Install all runtime deps with their version constraints, minus diffq
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
say "[4/5] Deep-learning stack..."

if [ "$USE_GPU" -eq 1 ]; then
    if command -v nvidia-smi &>/dev/null; then
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
        warn "nvidia-smi not found. Falling back to CPU torch."
        warn "Use --cpu to suppress this warning, or install NVIDIA drivers."
        pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
        ok "torch  ($(python3 -c 'import torch; print(torch.__version__)'))  (CPU)"
    fi
else
    echo "  Installing CPU-only torch..."
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    ok "torch  ($(python3 -c 'import torch; print(torch.__version__)'))  (CPU)"
fi

# ── Step 5: Small model files ───────────────────────────────
say "[5/5] Small model files..."

if [ "$DOWNLOAD_MODELS" -eq 0 ]; then
    warn "Skipped (--no-models). Download manually with:"
    echo "  bash download_models.sh"
else
    echo "  Downloading from GitHub Releases..."
    echo "  (skip with --no-models, or set AIMODELS_URL env var)"
    echo ""

    TMPDIR="$(mktemp -d)"
    trap "rm -rf $TMPDIR" EXIT

    # -- UVR MDX-NET (64 MB) --
    echo "  UVR MDX-NET (64 MB)..."
    download "$REPO_URL/UVR_MDXNET_Main.onnx" \
             "$PROJECT_DIR/SeperateModels/UVR_MDXNET_Main.onnx" || true

    # -- FireRedVAD (2.3 MB) --
    echo "  FireRedVAD (2.3 MB)..."
    download "$REPO_URL/FireRedVAD.tar.gz" \
             "$TMPDIR/FireRedVAD.tar.gz" || true
    if [ -f "$TMPDIR/FireRedVAD.tar.gz" ]; then
        tar -xzf "$TMPDIR/FireRedVAD.tar.gz" -C "$PROJECT_DIR/Qwen3-aligner-main/"
        ok "FireRedVAD extracted"
    fi

    # -- MTL checkpoints (123 MB) --
    echo "  MTL_BDR checkpoints (123 MB)..."
    download "$REPO_URL/checkpoints.tar.gz" \
             "$TMPDIR/checkpoints.tar.gz" || true
    if [ -f "$TMPDIR/checkpoints.tar.gz" ]; then
        tar -xzf "$TMPDIR/checkpoints.tar.gz" -C "$PROJECT_DIR/LyricsAlignment-MTL/"
        ok "checkpoints extracted"
    fi

    echo ""
fi

# ── Verify ──────────────────────────────────────────────────
echo ""
say "Verifying model files..."

MISSING=0
check_file "SeperateModels/UVR_MDXNET_Main.onnx"                || MISSING=1
check_file "LyricsAlignment-MTL/checkpoints/checkpoint_MTL"     || MISSING=1
check_file "LyricsAlignment-MTL/checkpoints/checkpoint_Baseline" || MISSING=1
check_file "LyricsAlignment-MTL/checkpoints/checkpoint_BDR"     || MISSING=1
check_file "Qwen3-aligner-main/FireRedVAD/model.pth.tar"        || MISSING=1
check_file "Qwen3-aligner-main/FireRedVAD/cmvn.ark"             || MISSING=1
check_file "SeperateModels/mdx_model_data.json"                 || MISSING=1

if [ "$MISSING" -eq 1 ]; then
    echo ""
    warn "Some model files are missing."
    echo "  Run:  bash download_models.sh"
    echo "  Or set AIMODELS_URL and re-run this script."
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
echo "  To pre-download it (faster first run):"
echo ""
echo "    # From HuggingFace (global):"
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
