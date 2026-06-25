"""Core pipeline: each step returns (success, error_msg, [created_files])."""

import os
import re
import sys
import subprocess

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError

from .lrclib import search as lrclib_search
from .logger import log_info
from .cleaner import Cleaner

# --- Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
VENV_BIN = os.path.dirname(sys.executable)

PYTHON_SEP = sys.executable
PYTHON_ALIGN = sys.executable
VOCAL_SEP_SCRIPT = os.path.join(PROJECT_DIR, "vocal_separate.py")
ALIGN_ONE_SCRIPT = os.path.join(PROJECT_DIR, "align_one.py")
QWEN3_CLI = os.path.join(PROJECT_DIR, "Qwen3-aligner-main", "cli.py")


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)


# ── Sentence splitting for ASR output ──────────────────────────────────

_ABBREVS = [
    'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sr', 'Jr',
    'St', 'Ave', 'Blvd', 'Rd', 'Ct', 'Ln',
    'Jan', 'Feb', 'Mar', 'Apr', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    'Capt', 'Col', 'Gen', 'Lt', 'Maj', 'Sgt', 'Gov', 'Sen', 'Rep', 'Rev', 'Hon',
    'Inc', 'Ltd', 'Co', 'Corp', 'Dept', 'Univ',
    'etc', 'vs', 'fig', 'eq', 'approx', 'esp',
]


def _split_transcribed_lines(text: str) -> str:
    """Split continuous ASR text into lines at sentence boundaries (. ! ?).

    Preserves abbreviations (Mr., Ms., Jr., etc.) so they are not
    treated as sentence terminators.
    """
    if not text:
        return text

    # If already multi-line, join and re-split for consistency
    cleaned = ' '.join(text.splitlines())

    # Step 1: replace periods in known abbreviations with placeholder
    for abbr in _ABBREVS:
        cleaned = re.sub(
            r'\b' + re.escape(abbr) + r'\.',
            abbr + '\x00',
            cleaned,
            flags=re.IGNORECASE,
        )

    # Step 2: handle i.e. / e.g. / U.S. style multi-dot abbreviations
    cleaned = re.sub(
        r'\b([A-Za-z])\.([A-Za-z])\.',
        lambda m: m.group(1) + '\x00' + m.group(2) + '\x00',
        cleaned,
    )

    # Step 3: split on . ! ? followed by whitespace
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)

    # Step 4: restore periods
    sentences = [s.replace('\x00', '.') for s in sentences]

    # Step 5: filter empty lines
    lines = [s.strip() for s in sentences if s.strip()]

    return '\n'.join(lines)


# ── Step 1: Extract metadata ──────────────────────────────────────────

def step_extract(music_file: str) -> tuple:
    """Returns (True, (title, artist), []) or (False, error, [])."""
    log_info("Step 1/6: Extract metadata")

    title = artist = None
    try:
        try:
            tags = EasyID3(music_file)
            title = tags.get("title", [None])[0]
            artist = tags.get("artist", [None])[0]
        except (ID3NoHeaderError, Exception):
            pass

        if not title or not artist:
            mf = MutagenFile(music_file)
            if mf:
                if not title:
                    t = mf.get("title", [None])
                    if isinstance(t, list) and t:
                        title = str(t[0])
                if not artist:
                    a = mf.get("artist", [None])
                    if isinstance(a, list) and a:
                        artist = str(a[0])
    except Exception as e:
        pass  # fall through to filename parsing

    basename = os.path.splitext(os.path.basename(music_file))[0]
    basename = re.sub(r'_\(Vocals\)$', '', basename, flags=re.IGNORECASE)

    if not title:
        title = basename
    if not artist:
        if " - " in basename:
            parts = basename.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()

    title = title.strip() if title else ""
    artist = artist.strip() if artist else ""

    log_info(f"  Title:  {title}")
    log_info(f"  Artist: {artist}")

    if not title or not artist:
        return (False, "Could not determine title/artist from metadata or filename", [])

    return (True, (title, artist), [])


# ── Step 2: Search LRCLIB ─────────────────────────────────────────────

def step_search(title: str, artist: str, output_dir: str) -> tuple:
    """Returns (True, lyrics_txt_path, [lyrics_txt_path]) or (False, error, [])."""
    log_info("Step 2/6: Search LRCLIB lyrics")

    safe_name = sanitize_filename(f"{artist} - {title}")
    lyrics_txt = os.path.join(output_dir, f"{safe_name}.txt")

    try:
        lyrics = lrclib_search(title, artist)
    except RuntimeError as e:
        return (False, str(e), [])

    with open(lyrics_txt, "w", encoding="utf-8") as f:
        f.write(lyrics)

    lines = lyrics.count('\n') + 1
    log_info(f"  Saved: {lyrics_txt} ({lines} lines)")
    return (True, lyrics_txt, [lyrics_txt])


# ── Step 3: recorrect (optional) ──────────────────────────────────────

def step_correct(asr_file: str, ref_file: str, output_dir: str, safe_name: str,
                 vocal_wav: str = None) -> tuple:
    """Calibrate ASR against reference lyrics.

    Two modes:
      - vocal_wav=None (legacy): text-based recorrect → corrected.txt
      - vocal_wav provided (dual-LRC): align both texts → LRC → time-probe
        recorrect → corrected.lrc

    Returns (True, path, [files]) or (False, error, []).
    Failure is non-fatal — caller should fall back to original.
    """
    log_info("Step 4/6: Calibrate lyrics via recorrect")

    if not asr_file:
        log_info("  Skipped (no ASR file provided)")
        return (True, ref_file, [])

    if not os.path.exists(asr_file):
        log_info(f"  WARNING: ASR file not found: {asr_file}, skipping")
        return (True, ref_file, [])

    # ── Dual-LRC mode: align both → recorrect with time probes ──
    if vocal_wav:
        return _step_correct_lrc(asr_file, ref_file, output_dir, safe_name, vocal_wav)

    # ── Legacy text-based mode ──
    return _step_correct_txt(asr_file, ref_file, output_dir, safe_name)


def _step_correct_lrc(asr_file: str, ref_file: str, output_dir: str,
                      safe_name: str, vocal_wav: str) -> tuple:
    """Dual-LRC time-probe correction → corrected TXT for step_align."""
    asr_lrc = os.path.join(output_dir, f"{safe_name}_transcribed_align.lrc")
    ref_lrc = os.path.join(output_dir, f"{safe_name}_ref_align.lrc")

    # CSV paths from align_one.py (naming: {vocal_base}_{txt_tag}_align.csv)
    vocal_base = os.path.splitext(vocal_wav)[0]
    asr_tag = os.path.splitext(os.path.basename(asr_file))[0]
    ref_tag = os.path.splitext(os.path.basename(ref_file))[0]
    csv_asr = f"{vocal_base}_{asr_tag}_align.csv"
    csv_ref = f"{vocal_base}_{ref_tag}_align.csv"

    # 1. Align transcribed text → transcribed_align.lrc
    log_info("  Aligning transcribed lyrics...")
    result = subprocess.run(
        [PYTHON_ALIGN, ALIGN_ONE_SCRIPT, vocal_wav, asr_file, asr_lrc],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        err = result.stdout.strip() or result.stderr.strip() or '(no output)'
        log_info(f"  WARNING: transcribed alignment failed: {err[:200]}")
        return _step_correct_txt(asr_file, ref_file, output_dir, safe_name)
    log_info(f"    -> {asr_lrc}")

    # 2. Align reference text -> ref_align.lrc
    log_info("  Aligning reference lyrics...")
    result = subprocess.run(
        [PYTHON_ALIGN, ALIGN_ONE_SCRIPT, vocal_wav, ref_file, ref_lrc],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        err = result.stdout.strip() or result.stderr.strip() or '(no output)'
        log_info(f"  WARNING: reference alignment failed: {err[:200]}")
        csvs = [csv_asr] if os.path.exists(csv_asr) else []
        return _step_correct_txt(asr_file, ref_file, output_dir, safe_name, extra_tracked=csvs)
    log_info(f"    -> {ref_lrc}")

    # Collect both alignment CSVs for cleanup tracking
    _both_csvs = [c for c in [csv_asr, csv_ref] if os.path.exists(c)]

    # 3. Dual-LRC recorrect -> corrected TXT + LRC
    corrected_base = os.path.join(output_dir, f"{safe_name}_corrected")
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_DIR
    result = subprocess.run(
        [PYTHON_SEP, "-m", "recorrect", asr_lrc, ref_lrc, "-o", corrected_base, "-f", "all"],
        capture_output=True, text=True, cwd=PROJECT_DIR, env=env
    )
    if result.returncode != 0:
        log_info(f"  WARNING: LRC recorrect failed, falling back to text mode")
        log_info(f"  stderr: {result.stderr[:200] if result.stderr else '(empty)'}")
        return _step_correct_txt(asr_file, ref_file, output_dir, safe_name, extra_tracked=_both_csvs)

    corrected_txt = corrected_base + ".txt"
    if not os.path.exists(corrected_txt):
        return _step_correct_txt(asr_file, ref_file, output_dir, safe_name, extra_tracked=_both_csvs)

    with open(corrected_txt, 'r', encoding='utf-8') as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    with open(ref_file, 'r', encoding='utf-8') as f:
        ref_lines = [l for l in f.read().splitlines() if l.strip()]
    loss_ratio = (len(ref_lines) - len(lines)) / max(len(ref_lines), 1)
    if loss_ratio > 0.5:
        log_info(f"  WARNING: calibration lost {loss_ratio:.0%} lines ({len(ref_lines)}->{len(lines)}), keeping reference")
        csvs = [csv_asr, csv_ref]
        return (True, ref_file, [asr_lrc, ref_lrc] + [c for c in csvs if os.path.exists(c)])

    log_info(f"  Corrected: {corrected_txt} ({len(lines)} lines, ref={len(ref_lines)})")
    tracked = [asr_lrc, ref_lrc, corrected_txt, corrected_base + ".lrc"]
    for ext in ['.srt', '.json']:
        f = corrected_base + ext
        if os.path.exists(f):
            tracked.append(f)
    # Track alignment CSVs for cleanup (align_one.py naming: {vocal_base}_{txt_tag}_align.csv)
    for csv_file in [csv_asr, csv_ref]:
        if os.path.exists(csv_file):
            tracked.append(csv_file)
    return (True, corrected_txt, tracked)


def _step_correct_txt(asr_file: str, ref_file: str, output_dir: str,
                      safe_name: str, extra_tracked: list = None) -> tuple:
    """Legacy text-based recorrect path."""
    extra_tracked = extra_tracked or []
    corrected_base = os.path.join(output_dir, f"{safe_name}_corrected")
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_DIR
    result = subprocess.run(
        [PYTHON_SEP, "-m", "recorrect", asr_file, ref_file, "-o", corrected_base, "-f", "txt"],
        capture_output=True, text=True, cwd=PROJECT_DIR, env=env
    )
    if result.returncode != 0:
        log_info(f"  WARNING: recorrect failed, using ASR transcription")
        log_info(f"  stderr: {result.stderr[:200] if result.stderr else '(empty)'}")
        return (True, asr_file, extra_tracked)

    corrected_txt = corrected_base + ".txt"
    if os.path.exists(corrected_txt):
        with open(corrected_txt, 'r', encoding='utf-8') as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        with open(ref_file, 'r', encoding='utf-8') as f:
            ref_lines = [l for l in f.read().splitlines() if l.strip()]
        loss_ratio = (len(ref_lines) - len(lines)) / max(len(ref_lines), 1)
        if loss_ratio > 0.5:
            log_info(f"  WARNING: calibration lost {loss_ratio:.0%} lines ({len(ref_lines)}->{len(lines)}), keeping original reference")
            return (True, ref_file, extra_tracked)
        log_info(f"  Corrected: {corrected_txt} ({len(lines)} lines, ref={len(ref_lines)}, repeats={max(0, len(lines)-len(ref_lines))})")
        return (True, corrected_txt, [corrected_txt] + extra_tracked)

    return (True, ref_file, extra_tracked)


# ── Step 2: Separate vocals ───────────────────────────────────────────

def step_separate(music_file: str, output_dir: str) -> tuple:
    """Returns (True, vocal_wav_path, [vocal_wav_path]) or (False, error, [])."""
    log_info("Step 2/6: Separate vocals (UVR MDX-NET, GPU)")

    basename = os.path.splitext(os.path.basename(music_file))[0]
    basename = re.sub(r'_\(Vocals\)$', '', basename, flags=re.IGNORECASE)

    is_vocal = re.search(r'_\(Vocals\)', os.path.basename(music_file), re.IGNORECASE)
    if is_vocal:
        log_info("  Input is already a vocal file, skipping")
        return (True, music_file, [])

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([VENV_BIN, env.get("PATH", "")])

    result = subprocess.run(
        [PYTHON_SEP, VOCAL_SEP_SCRIPT, music_file, output_dir],
        capture_output=False, env=env
    )
    if result.returncode != 0:
        return (False, "Vocal separation failed", [])

    # Find the output vocal wav
    vocal_wav = None
    for fname in os.listdir(output_dir):
        if fname.endswith(".wav") and "_(Vocals)" in fname:
            candidate = os.path.join(output_dir, fname)
            if vocal_wav is None:
                vocal_wav = candidate
            if basename in fname:
                vocal_wav = candidate
                break

    if not vocal_wav or not os.path.exists(vocal_wav):
        return (False, "Vocal WAV not found after separation", [])

    # Also track instrumental wav from UVR
    tracked = [vocal_wav]
    inst_wav = re.sub(r'_\(Vocals\)', '_(Instrumental)', vocal_wav)
    if os.path.exists(inst_wav):
        tracked.append(inst_wav)

    log_info(f"  Vocal: {vocal_wav}")
    return (True, vocal_wav, tracked)


# ── Step 3: Transcribe vocals → lyrics (Qwen3-ASR 1.7B, GPU) ──────────────


def step_transcribe(vocal_wav: str, output_dir: str, safe_name: str,
                    language: str = "English", model_size: str = "1.7B") -> tuple:
    """Returns (True, lyrics_txt_path, [lyrics_txt_path]) or (False, error, [])."""
    log_info("Step 3/6: Transcribe vocals → lyrics (Qwen3-ASR 1.7B)")
    log_info(f"  Audio:  {vocal_wav}")
    log_info(f"  Lang:   {language}")

    lyrics_txt = os.path.join(output_dir, f"{safe_name}_transcribed.txt")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([VENV_BIN, env.get("PATH", "")])

    result = subprocess.run(
        [PYTHON_SEP, QWEN3_CLI, "transcribe", vocal_wav,
         "-l", language, "-m", model_size, "-o", lyrics_txt],
        capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        return (False, f"Transcription failed: {result.stderr[:300] if result.stderr else 'unknown'}", [])

    if not os.path.exists(lyrics_txt):
        return (False, "Transcribed txt not generated", [])

    with open(lyrics_txt, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    # Split continuous ASR text into sentence lines
    split_text = _split_transcribed_lines(raw_text)
    if split_text != raw_text:
        with open(lyrics_txt, 'w', encoding='utf-8') as f:
            f.write(split_text)

    lines = [l for l in split_text.splitlines() if l.strip()]

    tracked = [lyrics_txt]
    json_file = os.path.splitext(lyrics_txt)[0] + '.json'
    if os.path.exists(json_file):
        tracked.append(json_file)

    log_info(f"  Lyrics: {lyrics_txt} ({len(lines)} lines)")
    return (True, lyrics_txt, tracked)


# ── Step 5: Align lyrics → LRC (MTL_BDR, CPU, uses separated vocals) ──

def step_align(vocal_wav: str, lyrics_txt: str, output_dir: str, safe_name: str) -> tuple:
    """Returns (True, lrc_path, [lrc_path, csv_path]) or (False, error, [])."""
    log_info("Step 5/6: Align lyrics → LRC (MTL_BDR, CPU)")
    log_info(f"  Vocal:  {vocal_wav}")
    log_info(f"  Lyrics: {lyrics_txt}")

    lrc_path = os.path.join(output_dir, f"{safe_name}.lrc")

    result = subprocess.run(
        [PYTHON_ALIGN, ALIGN_ONE_SCRIPT, vocal_wav, lyrics_txt, lrc_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return (False, f"Alignment failed: {result.stderr[:300] if result.stderr else 'unknown'}", [])

    if not os.path.exists(lrc_path):
        return (False, "LRC file not generated", [])

    # Track CSV for cleanup — matches align_one.py naming: {vocal_base}_{txt_tag}_align.csv
    vocal_base = os.path.splitext(vocal_wav)[0]
    txt_tag = os.path.splitext(os.path.basename(lyrics_txt))[0]
    csv_path = f"{vocal_base}_{txt_tag}_align.csv"
    files = [lrc_path]
    if os.path.exists(csv_path):
        files.append(csv_path)

    log_info(f"  LRC: {lrc_path}")
    return (True, lrc_path, files)


# ── Step 6: Upload (optional) ────────────────────────────────────────

def step_upload(music_file: str, lrc_path: str, server_url: str = "http://localhost:8080") -> tuple:
    """Returns (True, response_text, []) or (False, error, []). Non-fatal."""
    import requests
    log_info("Step 6/6: Upload to server")

    try:
        with open(music_file, 'rb') as af, open(lrc_path, 'rb') as lf:
            resp = requests.post(
                f"{server_url}/api/upload",
                files={"audio": af, "lrc": lf},
                timeout=30
            )
        if resp.status_code == 201:
            data = resp.json()
            info = f"id={data.get('id','?')} title={data.get('title','?')}"
            log_info(f"  Uploaded: {info}")
            return (True, info, [])
        else:
            return (False, f"Upload returned {resp.status_code}: {resp.text[:200]}", [])
    except Exception as e:
        return (False, f"Upload failed: {e}", [])
