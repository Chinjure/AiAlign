"""CLI for recorrect: calibrate ASR lyrics against reference lyrics.

Usage:
    python -m recorrect <asr_file> <ref_file> [--output OUT] [--format fmt]

Examples:
    python -m recorrect asr_output.srt ref_lyrics.txt
    python -m recorrect asr.txt ref.txt -o corrected
    python -m recorrect asr.json ref.txt -f lrc
"""

import argparse
import os
import sys
from collections import Counter

from .pipeline import correct_lyrics, correct_lyrics_lrc
from .io_utils import write_lrc, write_txt, write_json_output, write_srt, has_timing, load_asr, load_lrc


def main():
    parser = argparse.ArgumentParser(
        description='Calibrate ASR lyrics against reference lyrics',
    )
    parser.add_argument('asr', help='ASR output file (.txt, .srt, .json, .lrc)')
    parser.add_argument('ref', help='Reference lyrics file (.txt, .lrc)')
    parser.add_argument('-o', '--output', help='Output file base name (without extension)')
    parser.add_argument('-f', '--format', choices=['txt', 'lrc', 'json', 'srt', 'all'],
                        default='all', help='Output format (default: all)')

    args = parser.parse_args()

    if not os.path.exists(args.asr):
        print(f"ERROR: ASR file not found: {args.asr}")
        sys.exit(1)
    if not os.path.exists(args.ref):
        print(f"ERROR: Reference file not found: {args.ref}")
        sys.exit(1)

    # Determine output base
    if args.output:
        base = args.output
    else:
        base = os.path.splitext(args.asr)[0] + '_corrected'

    print(f"ASR:       {args.asr}")
    print(f"Reference: {args.ref}")
    print(f"Output:    {base}.*")
    print("-" * 50)

    is_dual_lrc = args.asr.lower().endswith('.lrc') and args.ref.lower().endswith('.lrc')

    if is_dual_lrc:
        _run_lrc_pipeline(args, base)
    else:
        _run_text_pipeline(args, base)


def _run_lrc_pipeline(args, base):
    """Dual-LRC mode: time-aware matching between two independently-aligned LRC files."""
    result = correct_lyrics_lrc(args.asr, args.ref)
    corrected = result['corrected']

    if not corrected:
        print("ERROR: No matches found between ASR-LRC and reference-LRC")
        sys.exit(1)

    print(f"Matched:     {len(corrected)} lines")
    merges = len({e['ref_index'] for e in corrected if e.get('is_merge')})
    splits = len({e['asr_index'] for e in corrected if e.get('is_split')})
    if merges:
        print(f"Merges:      {merges}")
    if splits:
        print(f"Splits:      {splits}")
    if result['unmatched']:
        print(f"Unmatched Ref: {result['unmatched']}")
    print(f"Avg score:   {result['avg_score']:.3f}")
    print("-" * 50)

    fmt = args.format

    if fmt in ('txt', 'all'):
        write_txt([e['text'] for e in corrected], base + '.txt')
        print(f"TXT → {base}.txt")

    if fmt in ('lrc', 'all'):
        write_lrc(corrected, base + '.lrc')
        print(f"LRC → {base}.lrc")

    if fmt in ('srt', 'all'):
        # SRT needs end_time; use next line's start_time or +2s
        for idx, e in enumerate(corrected):
            if 'end_time' not in e:
                if idx + 1 < len(corrected):
                    e['end_time'] = corrected[idx + 1]['start_time']
                else:
                    e['end_time'] = e['start_time'] + 3.0
        write_srt(corrected, base + '.srt')
        print(f"SRT → {base}.srt")

    if fmt in ('json', 'all'):
        write_json_output(corrected, base + '.json')
        print(f"JSON → {base}.json")


def _run_text_pipeline(args, base):
    """Original text-based pipeline (ASR .txt/.srt/.json + reference .txt)."""
    result = correct_lyrics(args.asr, args.ref)
    corrected = result['corrected']

    if not corrected:
        print("ERROR: No matches found between ASR and reference lyrics")
        sys.exit(1)

    print(f"Matched:   {len(corrected)} lines")
    print(f"Skipped Ref: {len(result['unmatched_ref'])} lines "
          f"({result['unmatched_ref']})")
    print(f"Avg score: {result['avg_score']:.3f}")
    print("-" * 50)

    asr_entries = load_asr(args.asr)
    timing = has_timing(asr_entries)
    fmt = args.format

    if fmt in ('txt', 'all'):
        # Use ASR structure as the blueprint, reference as the text source.
        # ASR tells us WHAT is sung WHEN; reference tells us the correct WORDS.
        # This preserves repeats at their ASR-detected positions and never
        # drops a reference line.
        with open(args.ref, 'r', encoding='utf-8') as f:
            ref_all = [line.strip() for line in f.read().splitlines() if line.strip()]

        # 1. Build output from corrected (ASR order).
        blueprint = []
        matched_refs = set()
        for e in corrected:
            matched_refs.add(e['ref_index'])
            blueprint.append(e['text'])

        # 2. Insert unmatched reference lines at the position where their
        #    ref_index neighbours appear in the blueprint.
        missing = [j for j in range(len(ref_all)) if j not in matched_refs]
        # Map: ref_index → list of blueprint positions
        ref_pos = {}
        for i, e in enumerate(corrected):
            if e['ref_index'] not in ref_pos:
                ref_pos[e['ref_index']] = []
            ref_pos[e['ref_index']].append(i)

        # Build a position in the blueprint for each ref_index
        # Use the median position of its occurrences
        ref_bp_pos = {}
        for ridx, positions in ref_pos.items():
            ref_bp_pos[ridx] = positions[len(positions) // 2]

        # Counts: how many times does each text appear in blueprint vs reference?
        bp_counts = Counter(blueprint)
        ref_counts = Counter(ref_all)

        # Insert missing ref lines, ordered by ref_index so earlier
        # insertions don't shift later ones unpredictably.
        # Skip only if blueprint already has enough copies of this text
        # (e.g. bridge section matched via earlier ref_index with identical words).
        for j in sorted(missing):
            text = ref_all[j]
            if bp_counts.get(text, 0) >= ref_counts[text]:
                # Already represented — skip duplicate
                continue
            bp_counts[text] = bp_counts.get(text, 0) + 1
            # Find neighbour ref_indices
            prev_j = max((r for r in matched_refs if r < j), default=-1)
            next_j = min((r for r in matched_refs if r > j), default=-1)
            if prev_j >= 0 and next_j >= 0:
                insert_at = (ref_bp_pos[prev_j] + ref_bp_pos[next_j]) // 2 + 1
            elif prev_j >= 0:
                insert_at = ref_bp_pos[prev_j] + 1
            elif next_j >= 0:
                insert_at = ref_bp_pos[next_j]
            else:
                insert_at = len(blueprint)
            insert_at = min(insert_at, len(blueprint))
            blueprint.insert(insert_at, text)
            # Shift later positions
            for ridx in ref_bp_pos:
                if ref_bp_pos[ridx] >= insert_at:
                    ref_bp_pos[ridx] += 1

        write_txt(blueprint, base + '.txt')
        n_diff = len(blueprint) - len(ref_all)
        sign = '+' if n_diff >= 0 else ''
        print(f"TXT → {base}.txt ({len(blueprint)} lines, "
              f"ref={len(ref_all)} {sign}{n_diff})")

    if fmt in ('lrc', 'all') and timing:
        write_lrc(corrected, base + '.lrc')
        print(f"LRC → {base}.lrc")

    if fmt in ('srt', 'all') and timing:
        write_srt(corrected, base + '.srt')
        print(f"SRT → {base}.srt")

    if fmt in ('json', 'all'):
        write_json_output(corrected, base + '.json')
        print(f"JSON → {base}.json")

    if fmt == 'lrc' and not timing:
        print("WARNING: Input has no timing info, LRC cannot be generated")
        write_txt([e['text'] for e in corrected], base + '.txt')
        print(f"TXT → {base}.txt")


if __name__ == '__main__':
    main()
