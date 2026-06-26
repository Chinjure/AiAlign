"""generate-lyrics — end-to-end LRC generation.

Pipeline: extract → separate → transcribe → search → correct → align → cleanup
"""

import argparse
import os
import sys
from typing import Optional, List

from .pipeline import (
    step_extract, step_separate, step_transcribe, step_correct, step_search,
    step_align, step_upload, sanitize_filename,
)
from .cleaner import Cleaner
from .logger import log_info, log_error

MUSIC_EXTS = {'.mp3', '.flac', '.wav'}


def _process_one(music_file: str, args: argparse.Namespace) -> Optional[str]:
    """Process a single music file through the pipeline.

    Returns the LRC path on success, None on failure.
    Does NOT call sys.exit on failure — caller decides.
    """
    if not os.path.exists(music_file):
        log_error(f"Music file not found, skipping: {music_file}")
        return None

    output_dir = args.output_dir or os.path.dirname(os.path.abspath(music_file)) or "."
    os.makedirs(output_dir, exist_ok=True)
    error_log = os.path.join(output_dir, "error.log")
    if os.path.exists(error_log):
        os.remove(error_log)

    cleaner = Cleaner()

    def fatal(step: str, error: str):
        cleaner.clean_and_exit(error_log, f"Step {step}: {error}")

    print("=" * 55)
    print(f"generate-lyrics")
    print(f"  Input:  {music_file}")
    print(f"  Output: {output_dir}")
    print("=" * 55)

    # Step 1: Extract metadata
    ok, result, files = step_extract(music_file)
    if not ok:
        fatal("1 (extract)", result)
    title, artist = result
    safe_name = sanitize_filename(f"{artist} - {title}")

    # Step 2: Separate vocals
    ok, result, files = step_separate(music_file, output_dir)
    cleaner.track_all(files)
    if not ok:
        fatal("2 (separate)", result)
    vocal_wav = result

    # Step 3: Transcribe vocals → lyrics
    ok, result, files = step_transcribe(vocal_wav, output_dir, safe_name)
    cleaner.track_all(files)
    if not ok:
        fatal("3 (transcribe)", result)
    lyrics_txt = result

    # Step 4: Search LRCLIB + recorrect (non-fatal, fall back to raw ASR)
    align_input = lyrics_txt
    ok, result, files = step_search(title, artist, output_dir)
    if ok:
        ref_lyrics = result
        cleaner.track_all(files)
        ok, result, files = step_correct(lyrics_txt, ref_lyrics, output_dir, safe_name,
                                         vocal_wav=vocal_wav)
        cleaner.track_all(files)
        if ok:
            align_input = result
    else:
        log_info(f"  WARNING: LRCLIB search failed: {result}")

    # Step 5: Align → LRC
    if align_input.endswith('.lrc'):
        # Already an LRC from recorrect fallback (e.g. poor ASR quality)
        lrc_path = align_input
    else:
        ok, result, files = step_align(vocal_wav, align_input, output_dir, safe_name)
        if not ok:
            fatal("4 (align)", result)
        lrc_path = result
        for f in files:
            if f != lrc_path:
                cleaner.track(f)

    # Upload (optional)
    if args.upload:
        ok, result, _ = step_upload(music_file, lrc_path, args.server)
        if not ok:
            log_info(f"  Upload WARNING: {result}")

    # Cleanup
    if not args.keep:
        print("=" * 55)
        log_info("Cleanup")
        n = cleaner.clean_all()
        if n > 0:
            log_info(f"  Removed {n} intermediate files")

    print("=" * 55)
    log_info(f"Done!  LRC: {lrc_path}")
    return lrc_path


def _collect_files(dir_path: str) -> List[str]:
    """Collect music files from directory, sorted by name."""
    files = []
    for fname in sorted(os.listdir(dir_path)):
        if os.path.splitext(fname)[1].lower() in MUSIC_EXTS:
            files.append(os.path.join(dir_path, fname))
    return files


def main():
    parser = argparse.ArgumentParser(description='Generate LRC lyrics from music file')
    parser.add_argument('music_file', nargs='?', default=None,
                        help='Path to music file (.mp3/.flac/.wav)')
    parser.add_argument('-o', '--output', dest='output_dir', default=None,
                        help='Output directory (default: same as music file)')
    parser.add_argument('--batch', metavar='DIR',
                        help='Batch process all music files in directory')
    parser.add_argument('--upload', action='store_true', help='Upload after generation')
    parser.add_argument('--server', default='http://localhost:8080', help='Server URL')
    parser.add_argument('--keep', action='store_true', help='Keep intermediate files')
    args = parser.parse_args()

    if not args.music_file and not args.batch:
        parser.error("either music_file or --batch DIR is required")

    if args.batch:
        batch_dir = args.batch
        if not os.path.isdir(batch_dir):
            log_error(f"Not a directory: {batch_dir}")
            sys.exit(1)

        files = _collect_files(batch_dir)
        if not files:
            log_error(f"No music files found in: {batch_dir}")
            sys.exit(1)

        print("=" * 55)
        print(f"generate-lyrics --batch")
        print(f"  Dir:   {batch_dir}")
        print(f"  Files: {len(files)}")
        print("=" * 55)

        ok_count = 0
        fail_count = 0
        for i, f in enumerate(files, 1):
            print(f"\n{'#' * 55}")
            print(f"# [{i}/{len(files)}] {os.path.basename(f)}")
            print(f"{'#' * 55}")
            try:
                result = _process_one(f, args)
                if result:
                    ok_count += 1
                else:
                    fail_count += 1
            except SystemExit:
                fail_count += 1
            except Exception as e:
                log_error(f"Unexpected error: {e}")
                fail_count += 1

        print(f"\n{'#' * 55}")
        print(f"# Batch complete: {ok_count} ok, {fail_count} failed (total {len(files)})")
        print(f"{'#' * 55}")
    else:
        result = _process_one(args.music_file, args)
        if not result:
            sys.exit(1)


if __name__ == '__main__':
    main()
