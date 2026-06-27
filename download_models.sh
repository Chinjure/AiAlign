#!/bin/bash
# ============================================================
# AiAlign — Download small model files from GitHub Releases
# ============================================================
# Usage:
#   bash download_models.sh
#   AIMODELS_URL="https://..." bash download_models.sh
#
# This only downloads the three small models (~190 MB total).
# The Qwen3-ASR model (~4.4 GB) is fetched automatically by
# the pipeline on first run from HuggingFace / ModelScope.
# ============================================================

set -euo pipefail

REPO_URL="${AIMODELS_URL:-https://github.com/YOUR_USERNAME/YOUR_REPO/releases/download/v1.0.0}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMPDIR="$(mktemp -d)"
trap "rm -rf $TMPDIR" EXIT

BOLD="$(tput bold 2>/dev/null || echo '')"
GREEN="$(tput setaf 2 2>/dev/null || echo '')"
RESET="$(tput sgr0 2>/dev/null || echo '')"

ok() { echo "  ${GREEN}v${RESET} $*"; }

download() {
    local url="$1" dest="$2" label="$3"
    echo "  Downloading $label..."
    mkdir -p "$(dirname "$dest")"
    if command -v wget &>/dev/null; then
        wget -q --show-progress -O "$dest" "$url"
    elif command -v curl &>/dev/null; then
        curl -fSL --progress-bar -o "$dest" "$url"
    else
        echo "  ERROR: install wget or curl first" >&2
        exit 1
    fi
    ok "$label"
}

echo ""
echo "${BOLD}AiAlign — Model Download${RESET}"
echo ""

# 1. UVR MDX-NET + config — vocal separation (~64 MB + tiny JSON)
download \
    "$REPO_URL/UVR_MDXNET_Main.onnx" \
    "$PROJECT_DIR/SeperateModels/UVR_MDXNET_Main.onnx" \
    "UVR MDX-NET  (64 MB)"
# Also need the model data JSON files that audio-separator references
download \
    "$REPO_URL/mdx_model_data.json" \
    "$PROJECT_DIR/SeperateModels/mdx_model_data.json" \
    "MDX model data"
download \
    "$REPO_URL/vr_model_data.json" \
    "$PROJECT_DIR/SeperateModels/vr_model_data.json" \
    "VR model data"
download \
    "$REPO_URL/download_checks.json" \
    "$PROJECT_DIR/SeperateModels/download_checks.json" \
    "download checks"

# 2. FireRedVAD — voice activity detection (~2.3 MB)
#    Contains: model.pth.tar + cmvn.ark
download \
    "$REPO_URL/FireRedVAD.tar.gz" \
    "$TMPDIR/FireRedVAD.tar.gz" \
    "FireRedVAD   (2.3 MB)"
tar -xzf "$TMPDIR/FireRedVAD.tar.gz" -C "$PROJECT_DIR/Qwen3-aligner-main/"
ok "FireRedVAD extracted"

# 3. MTL_BDR checkpoints — lyrics alignment (~123 MB)
download \
    "$REPO_URL/checkpoints.tar.gz" \
    "$TMPDIR/checkpoints.tar.gz" \
    "MTL checkpoints (123 MB)"
tar -xzf "$TMPDIR/checkpoints.tar.gz" -C "$PROJECT_DIR/LyricsAlignment-MTL/"
ok "checkpoints extracted"

echo ""
echo "${BOLD}Done.${RESET} Run: source venv/bin/activate && python -m generate-lyrics <file>"
echo ""
