"""I/O utilities for loading ASR and reference files, writing output."""

import json
import os
import re
import sys


# ── ASR Input ──

def load_asr(path: str) -> list[dict]:
    """Load ASR output from .txt, .srt, .json, or .lrc file.

    Returns list of dicts with keys: text, start_time (opt), end_time (opt), words (opt).
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == '.json':
        return _load_asr_json(path)
    elif ext == '.srt':
        return _load_asr_srt(path)
    elif ext == '.lrc':
        return load_lrc(path)
    else:
        return _load_asr_txt(path)





_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
# Known abbreviations whose period is not a sentence boundary.
_ABBREV = re.compile(r'\b(Mrs|Mr|Ms|Dr|Prof|St|Jr|Sr|Capt|Col|Gen|Lt|Maj|Rev|Hon)\.')


def _split_sentences(text: str) -> list[str]:
    """Split a continuous ASR blob into sentences at . ! ? boundaries,
    protecting known abbreviations (Mr. Mrs. Dr. etc.) from false splits."""
    protected = _ABBREV.sub(r'\1<DOT>', text.strip())
    parts = _SENTENCE_END.split(protected)
    return [p.strip().replace('<DOT>', '.') for p in parts if p.strip()]


def _is_continuous_blob(lines: list[str]) -> bool:
    """Heuristic: few very-long lines → ASR blob that needs sentence splitting."""
    if len(lines) <= 3:
        total = sum(len(l) for l in lines if l.strip())
        return total > 100
    return False


def _load_asr_txt(path: str) -> list[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()

    lines = raw.splitlines()
    stripped = [l.strip() for l in lines if l.strip()]

    # ASR blob: few long lines → split into sentences
    if _is_continuous_blob(lines):
        all_text = ' '.join(stripped)
        stripped = _split_sentences(all_text)

    return [{'text': line} for line in stripped if line]


def _load_asr_srt(path: str) -> list[dict]:
    entries = _parse_srt(path)
    return [{'text': e['text'], 'start_time': e['start_time'], 'end_time': e['end_time']}
            for e in entries]


def _load_asr_json(path: str) -> list[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and 'sentences' in data:
        entries = data['sentences']
    else:
        return []

    # Split blob entries into sentences (same logic as _load_asr_txt)
    result = []
    for entry in entries:
        text = entry.get('text', '')
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            result.append(entry)
            continue
        # Multiple sentences found — split with proportional timing if available
        total_len = sum(len(s) for s in sentences)
        start_time = entry.get('start_time')
        end_time = entry.get('end_time')
        has_times = start_time is not None and end_time is not None
        char_pos = 0
        for sent in sentences:
            new_entry = {'text': sent}
            if has_times:
                duration = end_time - start_time
                frac = len(sent) / total_len if total_len > 0 else 1.0 / len(sentences)
                new_entry['start_time'] = start_time + char_pos / total_len * duration if total_len > 0 else start_time
                new_entry['end_time'] = new_entry['start_time'] + frac * duration
            result.append(new_entry)
            char_pos += len(sent)
    return result


# ── SRT Parsing (self-contained, no external deps) ──

def _parse_srt(path: str) -> list[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    entries = []
    for block in re.split(r'\r?\n\r?\n', content):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        try:
            int(lines[0].strip())
        except ValueError:
            continue
        time_match = re.match(
            r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
            lines[1].strip(),
        )
        if not time_match:
            continue
        text = '\n'.join(lines[2:]).strip()
        entries.append({
            'start_time': _srt_time_to_seconds(time_match.group(1)),
            'end_time': _srt_time_to_seconds(time_match.group(2)),
            'text': text,
        })
    return entries


def _srt_time_to_seconds(s: str) -> float:
    h, m, rest = s.split(':')
    sec, ms = rest.split(',')
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


# ── LRC Input ──

_LRC_LINE = re.compile(r'\[(\d{2}):(\d{2})[.:](\d{2,3})\](.*)')


def load_lrc(path: str) -> list[dict]:
    """Parse LRC file into entries with timing.

    Returns list of dicts with keys: text, start_time.
    Handles both [mm:ss.xx] and [mm:ss.xxx] formats.
    """
    entries = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _LRC_LINE.match(line)
            if m:
                minutes, seconds, centiseconds, text = m.groups()
                t = int(minutes) * 60 + int(seconds) + int(centiseconds) / (1000 if len(centiseconds) == 3 else 100)
                entries.append({'text': text.strip(), 'start_time': t})
    return entries


# ── Reference Input ──

def load_ref(path: str) -> list[str]:
    """Load reference lyrics from plain text file, one line per lyric.

    For .lrc files, returns entries with timing (via load_lrc).
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == '.lrc':
        return load_lrc(path)
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    return [line.strip() for line in lines if line.strip()]


# ── Output ──

def write_txt(lines: list[str], path: str):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def write_lrc(corrected: list[dict], path: str):
    """Write LRC file. Each corrected dict must have: text, start_time (float seconds)."""
    lrc_lines = []
    for item in corrected:
        ts = item.get('start_time')
        if ts is not None:
            lrc_lines.append(f"[{_fmt_lrc_time(ts)}]{item['text']}")
        else:
            lrc_lines.append(item['text'])
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lrc_lines) + '\n')


def write_json_output(corrected: list[dict], path: str):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(corrected, f, ensure_ascii=False, indent=2)


def write_srt(corrected: list[dict], path: str):
    """Write SRT file from corrected entries with start_time/end_time."""
    lines = []
    for i, item in enumerate(corrected, 1):
        start = item.get('start_time', 0)
        end = item.get('end_time', start + 1)
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
        lines.append(item['text'])
        lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _fmt_lrc_time(seconds: float) -> str:
    """Convert seconds to LRC [mm:ss.xx] format."""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"


def _fmt_srt_time(seconds: float) -> str:
    """Convert seconds to SRT HH:MM:SS,mmm format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def has_timing(entries: list[dict]) -> bool:
    """Check if ASR entries contain timing information."""
    if not entries:
        return False
    return entries[0].get('start_time') is not None
