"""Run MTL-BDR alignment on a vocal+lyrics pair. Demo script."""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from wrapper import align, preprocess_from_file, write_csv

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Align vocals with lyrics using MTL-BDR')
    p.add_argument('audio_file', help='Vocal WAV file')
    p.add_argument('lyrics_file', help='Lyrics TXT file')
    p.add_argument('-o', '--output', default=None, help='Output CSV path')
    args = p.parse_args()

    audio_file = args.audio_file
    lyrics_file = args.lyrics_file
    pred_file = args.output or os.path.splitext(audio_file)[0] + '_align.csv'

    # Preprocess
    print("Loading audio and lyrics...")
    audio, words, lyrics_p, idx_word_p, idx_line_p = preprocess_from_file(
        audio_file, lyrics_file, word_file=None)

    # Align with MTL_BDR (best method)
    print("Aligning...")
    word_align, words = align(audio, words, lyrics_p, idx_word_p, idx_line_p,
                              method="MTL_BDR", cuda=False)

    # Write CSV
    write_csv(pred_file, word_align, words)
    print(f"CSV saved: {pred_file}")
