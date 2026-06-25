"""Separate vocals from audio using UVR MDX-Net model with GPU acceleration.

Fixed config:
  - Architecture: MDX-NET (UVR_MDXNET_Main.onnx)
  - Segment size: 128
  - Overlap: 0.25
  - GPU autocast: enabled
  - Output: Vocals only, WAV format

Usage: python vocal_separate.py <input_file> [output_dir]
"""
import sys, os, subprocess

VENV_BIN        = os.path.dirname(sys.executable)
AUDIO_SEPARATOR = os.path.join(VENV_BIN, "audio-separator")
MODEL_DIR       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SeperateModels")
MODEL           = "UVR_MDXNET_Main.onnx"

if len(sys.argv) < 2:
    print("Usage: python vocal_separate.py <input_file> [output_dir]")
    sys.exit(1)

input_file  = sys.argv[1]
output_dir  = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(input_file) or "."

if not os.path.exists(input_file):
    print(f"Error: Input file not found: {input_file}")
    sys.exit(1)

os.makedirs(output_dir, exist_ok=True)

env = os.environ.copy()
env["PATH"] = os.pathsep.join([VENV_BIN, env.get("PATH", "")])

print(f"Input:      {input_file}")
print(f"Output:     {output_dir}")
print(f"Model:      {MODEL}  |  segment=128  overlap=0.25  GPU=on")
print("-" * 50)

result = subprocess.run([
    AUDIO_SEPARATOR,
    input_file,
    "--model_filename", MODEL,
    "--model_file_dir", MODEL_DIR,
    "--output_dir", output_dir,
    "--output_format", "WAV",
    "--single_stem", "Vocals",
    "--mdx_segment_size", "128",
    "--mdx_overlap", "0.25",
    "--use_autocast",
], env=env)

sys.exit(result.returncode)
