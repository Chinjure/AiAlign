"""LRCLIB API client — search lyrics by artist + title."""

import re
import requests

LRCLIB_API = "https://lrclib.net/api"

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


def _fetch_get(title: str, artist: str, timeout: int) -> str:
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
    except requests.RequestException:
        pass
    return ""


def search(title: str, artist: str, timeout: int = 15) -> str:
    """Search LRCLIB for lyrics. Returns plainLyrics text or raises RuntimeError."""
    # Exact match with original title
    best = _fetch_get(title, artist, timeout)

    # If title has edition suffix, also try cleaned title — pick the longer lyrics
    clean_title = _clean_title(title)
    if clean_title != title:
        alt = _fetch_get(clean_title, artist, timeout)
        if len(alt) > len(best):
            best = alt

    if best:
        return best

    # Fuzzy search
    try:
        resp = requests.get(
            f"{LRCLIB_API}/search",
            params={"q": f"{title} {artist}"},
            timeout=timeout
        )
        if resp.status_code == 200:
            results = resp.json()
            for item in results[:5]:
                plain = item.get("plainLyrics", "")
                if plain and plain.strip():
                    return plain.strip()
    except requests.RequestException as e:
        raise RuntimeError(f"LRCLIB API unreachable: {e}")

    raise RuntimeError(f"Lyrics not found for '{artist}' - '{title}'")
