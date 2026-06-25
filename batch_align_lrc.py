"""Batch align vocals+lyrics and generate LRC files.

Usage: python batch_align_lrc.py --vocal-dir /path/to/vocals
"""
import sys, os, re, glob, subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = SCRIPT_DIR
MTL_DIR = os.path.join(PROJECT_DIR, "LyricsAlignment-MTL")

sys.path.insert(0, MTL_DIR)
os.chdir(MTL_DIR)

from wrapper import align, preprocess_from_file, write_csv


VOVAL_DIR = os.environ.get("VOVAL_DIR", "")
CSV2LRC   = os.path.join(MTL_DIR, "csv2lrc.py")
PYTHON    = sys.executable


def find_pairs():
    wavs = glob.glob(os.path.join(VOVAL_DIR, "*_(Vocals).wav"))
    txs  = glob.glob(os.path.join(VOVAL_DIR, "*.txt"))
    txt_map = {}
    for t in txs:
        key = os.path.splitext(os.path.basename(t))[0]
        txt_map[key] = t
    pairs = []
    for wav in sorted(wavs):
        base = re.sub(r'^\d+_', '', os.path.basename(wav))
        base = base.replace('_(Vocals).wav', '')
        if base in txt_map:
            pairs.append((wav, txt_map[base], base))
        else:
            print(f"  [WARN] No lyrics for: {os.path.basename(wav)}")
    return pairs


def main():
    pairs = find_pairs()
    print(f"Found {len(pairs)} song(s).\n")

    for i, (wav_path, txt_path, base_name) in enumerate(pairs, 1):
        csv_path = os.path.join(VOVAL_DIR, base_name + '_align.csv')
        lrc_path = os.path.join(VOVAL_DIR, base_name + '_align.lrc')

        print(f"[{i}/{len(pairs)}] {base_name}")

        if os.path.exists(csv_path):
            print(f"  CSV exists, skip alignment: {csv_path}")
        else:
            try:
                print("  Loading + aligning (MTL_BDR, CPU)...")
                audio, words, lyrics_p, idx_word_p, idx_line_p = preprocess_from_file(
                    wav_path, txt_path, word_file=None)
                word_align, words = align(audio, words, lyrics_p, idx_word_p, idx_line_p,
                                         method="MTL_BDR", cuda=False)
                write_csv(csv_path, word_align, words)
                print(f"  CSV saved: {csv_path}")
            except Exception as e:
                print(f"  [ERROR] {e}")
                continue

        if not os.path.exists(csv_path):
            print("  Skip LRC: no CSV")
            continue

        r = subprocess.run([PYTHON, CSV2LRC, csv_path, txt_path, lrc_path],
                          capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  LRC: {lrc_path}")
        else:
            print(f"  [ERROR] csv2lrc: {r.stderr}")
        print()

    print("Done.")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--vocal-dir', default=VOVAL_DIR, help='Directory containing vocal WAVs + lyrics TXTs')
    args = p.parse_args()
    if args.vocal_dir:
        VOVAL_DIR = args.vocal_dir
    main()
