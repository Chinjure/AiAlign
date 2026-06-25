#!/usr/bin/env python3
"""
tran-whisper: Transcribe song vocals to lyrics using faster-whisper.

Usage:
    python tran_whisper.py <audio> [-o OUTPUT] [-l LANGUAGE] [-m MODEL]
"""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Transcribe song vocals to lyrics")
    parser.add_argument("audio", help="Audio file path (WAV/MP3/FLAC)")
    parser.add_argument("-o", "--output", default="", help="Output txt path")
    parser.add_argument("-l", "--lang", default="en", help="Language code (default: en, auto=detect)")
    parser.add_argument("-m", "--model", default="small", help="Model size (tiny/base/small/medium)")
    args = parser.parse_args()

    audio_path = args.audio
    if not os.path.isfile(audio_path):
        print(f"Error: file not found: {audio_path}")
        sys.exit(1)

    from faster_whisper import WhisperModel

    # Load model
    model = WhisperModel(args.model, device="cuda", compute_type="float16")

    # Transcribe
    kwargs = {"beam_size": 5}
    if args.lang != "auto":
        kwargs["language"] = args.lang
    segments, info = model.transcribe(audio_path, **kwargs)

    print(f"Language: {info.language} (prob={info.language_probability:.3f})")
    print(f"Duration: {info.duration:.1f}s")
    print()

    lines = []
    for seg in segments:
        text = seg.text.strip()
        print(f"[{seg.start:.1f}s -> {seg.end:.1f}s] {text}")
        lines.append(text)

    full_text = " ".join(lines)

    # Output path
    if args.output:
        out_path = args.output
    else:
        base = audio_path.rsplit(".", 1)[0]
        out_path = base + "_lyrics_whisper.txt"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"\nSaved: {out_path}")
    print(f"Lines: {len(lines)}, Words: {sum(len(l.split()) for l in lines)}")


if __name__ == "__main__":
    main()
