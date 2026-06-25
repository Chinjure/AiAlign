"""Convert alignment CSV to LRC lyrics file.

Usage: python csv2lrc.py <align_csv> <lyrics_txt> [output_lrc]

If output_lrc is omitted, replaces .csv with .lrc in the input path.
"""
import sys, os, re


def load_csv(csv_path):
    """Parse alignment CSV: start_time, end_time, word."""
    words = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 3:
                words.append((float(parts[0]), float(parts[1]), parts[2].strip()))
    return words


def load_lines(txt_path):
    """Parse raw lyrics TXT, return per-line word lists."""
    from string import ascii_lowercase
    d = {ascii_lowercase[i]: i for i in range(26)}
    d["'"] = 26
    d[" "] = 27
    d["~"] = 28

    with open(txt_path, 'r', encoding='utf-8') as f:
        raw_lines = f.read().splitlines()

    processed_lines = []
    word_counts = []
    for line in raw_lines:
        cleaned = "".join([c for c in line.lower() if c in d]).strip()
        cleaned = " ".join(cleaned.split())
        if cleaned:
            words = cleaned.split()
            processed_lines.append(line)
            word_counts.append(len(words))

    return processed_lines, word_counts


def csv2lrc(csv_path, txt_path, out_path):
    words = load_csv(csv_path)
    lines, word_counts = load_lines(txt_path)

    # Map CSV words to lyrics lines using word counts
    lrc_lines = []
    word_idx = 0
    for i, count in enumerate(word_counts):
        if word_idx >= len(words):
            break
        # Start time = first word of this line
        start_sec = words[word_idx][0]
        timestamp = fmt_time(start_sec)
        lrc_lines.append(f"[{timestamp}]{lines[i]}")
        word_idx += count

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lrc_lines) + '\n')

    print(f"LRC written to: {out_path}")


def fmt_time(seconds):
    """Convert seconds to [mm:ss.xx] format."""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python csv2lrc.py <align_csv> <lyrics_txt> [output_lrc]")
        sys.exit(1)

    csv_path = sys.argv[1]
    txt_path = sys.argv[2]

    if len(sys.argv) >= 4:
        out_path = sys.argv[3]
    else:
        out_path = os.path.splitext(csv_path)[0] + '.lrc'

    csv2lrc(csv_path, txt_path, out_path)
