"""LRCLIB API client — search lyrics by artist + title."""

import requests

LRCLIB_API = "https://lrclib.net/api"


def search(title: str, artist: str, timeout: int = 15) -> str:
    """Search LRCLIB for lyrics. Returns plainLyrics text or raises RuntimeError."""
    # Exact match first
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
        pass  # fall through to search

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
