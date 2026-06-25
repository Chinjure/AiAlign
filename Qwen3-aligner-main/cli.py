"""Qwen3-aligner CLI: speech-to-text transcription only (no alignment).

Usage:
    python cli.py transcribe <audio> [-l LANGUAGE] [-m MODEL_SIZE] [-o OUTPUT]
"""

import argparse
import json
import os
import sys
import traceback

from qwen3_aligner.transcribe import run_transcribe as _run_transcribe


def cmd_transcribe(args):
    """Audio -> plain text transcription."""
    print(f"Transcribing: {args.audio}")
    print(f"Language:     {args.language}")
    print(f"Model:        Qwen3-ASR-{args.model_size}")
    print("-" * 50)

    full_text, results = _run_transcribe(args.audio, args.language, args.model_size)

    if not full_text:
        print("ERROR: No text transcribed", file=sys.stderr)
        sys.exit(1)

    out_txt = args.output or os.path.splitext(args.audio)[0] + '_transcribed.txt'
    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write(full_text + '\n')
    print(f"TXT -> {out_txt}")

    out_json = os.path.splitext(out_txt)[0] + '.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"JSON -> {out_json}")

    print(f"\nTranscribed ({len(full_text)} chars):")
    print(full_text[:300] + ("..." if len(full_text) > 300 else ""))


def main():
    parser = argparse.ArgumentParser(
        description='Qwen3-aligner CLI: speech-to-text transcription'
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p_t = sub.add_parser('transcribe', help='Audio -> text transcription')
    p_t.add_argument('audio', help='Audio file path (.mp3, .wav, .flac, etc.)')
    p_t.add_argument('-l', '--language', default='English',
                     help='Language (default: English)')
    p_t.add_argument('-m', '--model-size', default='1.7B', choices=['0.6B', '1.7B'],
                     help='ASR model size (default: 1.7B)')
    p_t.add_argument('-o', '--output', help='Output path (default: {audio}_transcribed.txt)')
    p_t.set_defaults(func=cmd_transcribe)

    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
