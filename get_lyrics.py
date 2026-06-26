"""Get lyrics for a song and generate aligned LRC file.

Workflow:
  1. Extract song metadata (title, artist) from audio file via mutagen
  2. Search lyrics via LRCLIB API → save as .txt
  3. (Optional) Correct lyrics via recorrect if ASR transcription exists
  4. Separate vocals via vocal_separate.py (aligner_cpu env)
  5. Align vocals + corrected lyrics → LRC via align_one.py (lyrics_align env)
  6. Clean up all intermediate files

Usage:
    python get_lyrics.py <music_file> [output_dir]
    python get_lyrics.py <music_file> [output_dir] --correct <asr_file>
"""

import sys
import os
import re
import subprocess
import requests
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError

# --- Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = SCRIPT_DIR
PYTHON_ALIGN = sys.executable
PYTHON_SEP = sys.executable
VOCAL_SEP_SCRIPT = os.path.join(PROJECT_DIR, "vocal_separate.py")
ALIGN_ONE_SCRIPT = os.path.join(PROJECT_DIR, "align_one.py")
RECORRECT_DIR = os.path.join(PROJECT_DIR, "recorrect")

LRCLIB_API = "https://lrclib.net/api"


def extract_metadata(filepath):
    """Extract (title, artist) from audio file. Falls back to filename parsing."""
    title = artist = None

    try:
        try:
            tags = EasyID3(filepath)
            title = tags.get("title", [None])[0]
            artist = tags.get("artist", [None])[0]
        except (ID3NoHeaderError, Exception):
            pass

        if not title or not artist:
            mf = MutagenFile(filepath)
            if mf:
                if not title:
                    title = mf.get("title", [None])
                    if isinstance(title, list) and title:
                        title = str(title[0])
                if not artist:
                    artist = mf.get("artist", [None])
                    if isinstance(artist, list) and artist:
                        artist = str(artist[0])
    except Exception:
        pass

    basename = os.path.splitext(os.path.basename(filepath))[0]
    basename = re.sub(r'_\(Vocals\)$', '', basename, flags=re.IGNORECASE)

    if not title:
        title = basename
    if not artist:
        if " - " in basename:
            parts = basename.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()

    return title.strip() if title else "", artist.strip() if artist else ""


# Edition suffixes that can cause LRCLIB to return truncated entries
_EDITION_RE = re.compile(
    r'\s*\([^)]*(?:Remastered|Remaster|Deluxe|Edition|Bonus'
    r'|Expanded|Version|Mix|Edit|Re-?issue|Reissue|Anniversary'
    r'|Collectors|Special|Limited|Extended|Single|EP)[^)]*\)\s*$',
    re.IGNORECASE
)


def _clean_title(title: str) -> str:
    """Strip edition suffixes like '(Remastered)', '(Deluxe Edition)' from title."""
    cleaned = _EDITION_RE.sub('', title).strip()
    return cleaned or title


def _fetch_lrclib_get(title, artist, timeout=15):
    """Try /api/get exact match. Returns plainLyrics or empty string."""
    try:
        resp = requests.get(
            f"{LRCLIB_API}/get",
            params={"artist_name": artist, "track_name": title},
            timeout=timeout
        )
        if resp.status_code == 200:
            data = resp.json()
            plain = data.get("plainLyrics", "")
            if plain and plain.strip():
                return plain.strip()
    except Exception:
        pass
    return ""


def search_lyrics_lrclib(title, artist):
    """Search lyrics on LRCLIB. Returns plain lyrics text or None."""
    # Exact match with original title
    best = _fetch_lrclib_get(title, artist)

    # If title has edition suffix, also try cleaned title — pick the longer lyrics
    clean_title = _clean_title(title)
    if clean_title != title:
        alt = _fetch_lrclib_get(clean_title, artist)
        if len(alt) > len(best):
            best = alt

    if best:
        return best

    try:
        resp = requests.get(
            f"{LRCLIB_API}/search",
            params={"q": f"{title} {artist}"},
            timeout=15
        )
        if resp.status_code == 200:
            results = resp.json()
            for item in results[:5]:
                plain = item.get("plainLyrics", "")
                if plain and plain.strip():
                    print(f"  Found via search: {item.get('trackName', '?')} - {item.get('artistName', '?')}")
                    return plain.strip()
    except Exception as e:
        print(f"  LRCLIB search failed: {e}")

    return None


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def run_recorrect(asr_file, ref_file, output_file):
    """Run recorrect-align to calibrate lyrics."""
    print("=" * 55)
    print("Step 2.5/5: Correct lyrics via recorrect")

    result = subprocess.run(
        [PYTHON_SEP, "-m", "recorrect.cli", asr_file, ref_file, "-o", output_file, "-f", "txt"],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR
    )
    if result.returncode != 0:
        print("  WARNING: recorrect failed, using original lyrics")
        print(f"  stderr: {result.stderr[:300]}")
        return None

    corrected_txt = output_file + ".txt"
    if os.path.exists(corrected_txt):
        # Count lines
        with open(corrected_txt, 'r', encoding='utf-8') as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        print(f"  Corrected: {corrected_txt} ({len(lines)} lines)")
        return corrected_txt
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python get_lyrics.py <music_file> [output_dir] [--correct <asr_file>]")
        sys.exit(1)

    music_file = sys.argv[1]
    if not os.path.exists(music_file):
        print(f"ERROR: File not found: {music_file}")
        sys.exit(1)

    # Parse optional args
    asr_file = None
    output_dir = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--correct" and i + 1 < len(args):
            asr_file = args[i + 1]
            i += 2
        else:
            output_dir = args[i]
            i += 1

    if not output_dir:
        output_dir = os.path.dirname(music_file) or "."
    os.makedirs(output_dir, exist_ok=True)

    music_abs = os.path.abspath(music_file)
    basename = os.path.splitext(os.path.basename(music_abs))[0]
    song_key = re.sub(r'_\(Vocals\)$', '', basename, flags=re.IGNORECASE)

    # ── Step 1: Extract metadata ──
    print("=" * 55)
    print("Step 1/5: Extract metadata")
    title, artist = extract_metadata(music_abs)
    print(f"  Title:  {title}")
    print(f"  Artist: {artist}")

    if not title or not artist:
        print("WARNING: Could not determine title and artist.")
        print("  Using filename as fallback...")

    # ── Step 2: Search lyrics ──
    print("=" * 55)
    print("Step 2/5: Search lyrics")

    lyrics = search_lyrics_lrclib(title, artist) if title and artist else None

    if not lyrics:
        print(f"ERROR: Lyrics not found for '{title}' - '{artist}'")
        print("  Try providing a lyrics .txt file manually and run align_one.py directly.")
        sys.exit(1)

    safe_name = sanitize_filename(f"{artist} - {title}") if artist else sanitize_filename(title)
    lyrics_txt = os.path.join(output_dir, f"{safe_name}.txt")

    with open(lyrics_txt, "w", encoding="utf-8") as f:
        f.write(lyrics)

    line_count = lyrics.count('\n') + 1
    print(f"  Saved: {lyrics_txt}  ({line_count} lines)")

    # ── Step 2.5: Correct lyrics via recorrect (if ASR available) ──
    align_lyrics_txt = lyrics_txt  # default: use raw LRCLIB lyrics

    if asr_file:
        if not os.path.exists(asr_file):
            print(f"  WARNING: ASR file not found: {asr_file}, skipping correction")
        else:
            corrected_base = os.path.join(output_dir, f"{safe_name}_corrected")
            corrected_txt = run_recorrect(asr_file, lyrics_txt, corrected_base)
            if corrected_txt:
                align_lyrics_txt = corrected_txt

    # ── Step 3: Separate vocals ──
    print("=" * 55)
    print("Step 3/5: Separate vocals")

    is_vocal_file = re.search(r'_\(Vocals\)', basename, re.IGNORECASE)
    if is_vocal_file:
        print("  Input is already a vocal file, skipping separation.")
        vocal_wav = music_abs
    else:
        result = subprocess.run(
            [PYTHON_SEP, VOCAL_SEP_SCRIPT, music_abs, output_dir],
            capture_output=False
        )
        if result.returncode != 0:
            print("ERROR: Vocal separation failed.")
            sys.exit(1)

        vocal_wav = None
        for fname in os.listdir(output_dir):
            if fname.endswith(".wav") and "_(Vocals)" in fname:
                candidate = os.path.join(output_dir, fname)
                if vocal_wav is None:
                    vocal_wav = candidate
                if song_key in fname:
                    vocal_wav = candidate
                    break

    if not os.path.exists(vocal_wav):
        print(f"ERROR: Vocal WAV not found at: {vocal_wav}")
        sys.exit(1)
    print(f"  Vocal: {vocal_wav}")

    # ── Step 4: Align lyrics → LRC ──
    print("=" * 55)
    print("Step 4/5: Align lyrics → LRC")
    print(f"  Using: {align_lyrics_txt}")

    lrc_path = os.path.join(output_dir, f"{safe_name}.lrc")

    result = subprocess.run(
        [PYTHON_ALIGN, ALIGN_ONE_SCRIPT, vocal_wav, align_lyrics_txt, lrc_path],
        capture_output=False
    )
    if result.returncode != 0:
        print("ERROR: Alignment failed.")
        sys.exit(1)

    # ── Step 5: Cleanup all intermediates ──
    print("=" * 55)
    print("Step 5/5: Cleanup")

    intermediates = [lyrics_txt, vocal_wav]
    if align_lyrics_txt != lyrics_txt:
        intermediates.append(align_lyrics_txt)

    # Alignment CSV
    csv_path = os.path.splitext(vocal_wav)[0] + "_align.csv"
    if os.path.exists(csv_path):
        intermediates.append(csv_path)

    # ASR intermediate (the split sentences file)
    if asr_file and os.path.exists(asr_file):
        intermediates.append(asr_file)

    for f in intermediates:
        try:
            if os.path.exists(f):
                os.remove(f)
                print(f"  Cleaned: {os.path.basename(f)}")
        except OSError as e:
            print(f"  Cleanup failed: {os.path.basename(f)} ({e})")

    print("=" * 55)
    print(f"Done!  LRC: {lrc_path}")


if __name__ == "__main__":
    main()
