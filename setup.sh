#!/bin/bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

echo "=== Installing system dependencies ==="
if ! command -v ffmpeg &>/dev/null; then
    sudo apt-get install -y ffmpeg
fi

echo "=== Creating Python venv ==="
python3 -m venv "$PROJECT_DIR/venv"
source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip setuptools wheel

echo "=== Installing Python dependencies ==="
pip install -r "$PROJECT_DIR/requirements.txt"

echo "=== Verifying model files ==="
check() {
    local f="$PROJECT_DIR/$1"
    if [ -f "$f" ]; then
        echo "  OK: $1 ($(du -h "$f" | cut -f1))"
    else
        echo "  MISSING: $1"
    fi
}
check "SeperateModels/UVR_MDXNET_Main.onnx"
check "LyricsAlignment-MTL/checkpoints/checkpoint_MTL"
check "LyricsAlignment-MTL/checkpoints/checkpoint_BDR"
check "Qwen3-aligner-main/FireRedVAD/model.pth.tar"

echo ""
echo "=== Setup complete ==="
echo "Activate:  source $PROJECT_DIR/venv/bin/activate"
echo "GUI start: $PROJECT_DIR/Qwen3-aligner-main/start.sh"
