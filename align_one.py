"""Align one vocal+lyrics pair and generate LRC file.

Usage: python align_one.py <vocal_wav> <lyrics_txt> [output_lrc]

If output_lrc is omitted, saved next to vocal_wav with _align.lrc suffix.
"""
import sys
import os
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = SCRIPT_DIR
MTL_DIR = os.path.join(PROJECT_DIR, "LyricsAlignment-MTL")
CSV2LRC = os.path.join(MTL_DIR, "csv2lrc.py")
PYTHON = sys.executable


def main():
    if len(sys.argv) < 3:
        print("Usage: python align_one.py <vocal_wav> <lyrics_txt> [output_lrc]")
        sys.exit(1)

    wav_path = sys.argv[1]
    txt_path = sys.argv[2]

    if not os.path.exists(wav_path):
        print(f"ERROR: Vocal WAV not found: {wav_path}")
        sys.exit(1)
    if not os.path.exists(txt_path):
        print(f"ERROR: Lyrics TXT not found: {txt_path}")
        sys.exit(1)

    # Derive paths — CSV keyed by both WAV and text to avoid cross-text cache pollution
    base = os.path.splitext(wav_path)[0]
    txt_tag = os.path.splitext(os.path.basename(txt_path))[0]
    csv_path = f"{base}_{txt_tag}_align.csv"

    if len(sys.argv) >= 4:
        lrc_path = sys.argv[3]
    else:
        lrc_path = base + "_align.lrc"

    song_name = os.path.splitext(os.path.basename(wav_path))[0]
    print(f"Song:  {song_name}")
    print(f"WAV:   {wav_path}")
    print(f"Lyric: {txt_path}")
    print(f"CSV:   {csv_path}")
    print(f"LRC:   {lrc_path}")
    print("-" * 50)

    # Step 1: Alignment
    if os.path.exists(csv_path):
        print(f"CSV exists, skip alignment: {csv_path}")
    else:
        print("Running alignment (MTL_BDR, CPU)...")
        align_cmd = (
            f"import sys; sys.path.insert(0, {MTL_DIR!r}); "
            f"import os; os.chdir({MTL_DIR!r}); "
            f"from wrapper import align, preprocess_from_file, write_csv; "
            f"audio, words, lyrics_p, idx_word_p, idx_line_p = preprocess_from_file("
            f"{repr(wav_path)}, {repr(txt_path)}, word_file=None); "
            f"word_align, words = align(audio, words, lyrics_p, idx_word_p, idx_line_p, "
            f"method='MTL_BDR', cuda=False); "
            f"write_csv({repr(csv_path)}, word_align, words)"
        )
        r = subprocess.run(
            [PYTHON, "-c", align_cmd],
            capture_output=True, text=True, cwd=MTL_DIR
        )
        print(r.stdout)
        if r.returncode != 0:
            print(f"ERROR during alignment:\n{r.stderr}")
            sys.exit(1)

    if not os.path.exists(csv_path):
        print("ERROR: CSV was not generated")
        sys.exit(1)

    # Step 2: CSV → LRC
    print("Converting CSV to LRC...")
    r = subprocess.run(
        [PYTHON, CSV2LRC, csv_path, txt_path, lrc_path],
        capture_output=True, text=True
    )
    print(r.stdout)
    if r.returncode != 0:
        print(f"ERROR during CSV→LRC:\n{r.stderr}")
        sys.exit(1)

    print(f"Done: {lrc_path}")


if __name__ == "__main__":
    main()
