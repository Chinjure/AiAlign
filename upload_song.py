"""Upload a song file + matching LRC to the music player backend server.

Usage: python upload_song.py <music_file> [--server URL] [--lrc <lrc_file>]

If --lrc is omitted, auto-discovers .lrc in same directory.
Default server: http://localhost:8080
"""

import sys
import os
import re
import requests

DEFAULT_SERVER = "http://localhost:8080"


def find_lrc(music_path):
    """Auto-discover matching LRC file in the same directory."""
    music_dir = os.path.dirname(music_path) or "."
    music_basename = os.path.splitext(os.path.basename(music_path))[0]
    # Strip suffixes like _(Vocals)_UVR_MDXNET_Main
    song_key = re.sub(r'_\(Vocals\).*$', '', music_basename, flags=re.IGNORECASE)

    lrc_files = [f for f in os.listdir(music_dir) if f.endswith(".lrc")]

    if not lrc_files:
        return None
    if len(lrc_files) == 1:
        return os.path.join(music_dir, lrc_files[0])

    # Multiple LRCs: find best match
    for fname in lrc_files:
        base = os.path.splitext(fname)[0]
        if song_key in base:
            return os.path.join(music_dir, fname)

    # Looser match: any lrc that shares first N chars
    for fname in lrc_files:
        base = os.path.splitext(fname)[0]
        if base[:15] in music_basename or music_basename[:15] in base:
            return os.path.join(music_dir, fname)

    return None


def main():
    args = sys.argv[1:]
    lrc_path = None
    server_url = DEFAULT_SERVER

    i = 0
    while i < len(args):
        if args[i] == "--lrc" and i + 1 < len(args):
            lrc_path = args[i + 1]
            i += 2
        elif args[i] == "--server" and i + 1 < len(args):
            server_url = args[i + 1].rstrip("/")
            i += 2
        else:
            break

    if i >= len(args):
        print("Usage: python upload_song.py <music_file> [--lrc <lrc>] [--server URL]")
        sys.exit(1)

    music_path = args[i]
    if not os.path.exists(music_path):
        print(f"ERROR: File not found: {music_path}")
        sys.exit(1)

    # Auto-find LRC
    if not lrc_path:
        lrc_path = find_lrc(music_path)

    print(f"Server:  {server_url}")
    print(f"Audio:   {os.path.basename(music_path)}")
    if lrc_path:
        print(f"LRC:     {os.path.basename(lrc_path)}")
    else:
        print("LRC:     (none found — uploading audio only)")
    print("-" * 50)

    # Build multipart request
    files = {}
    files["audio"] = (os.path.basename(music_path), open(music_path, "rb"))
    if lrc_path:
        files["lrc"] = (os.path.basename(lrc_path), open(lrc_path, "rb"))

    try:
        resp = requests.post(f"{server_url}/api/upload", files=files, timeout=120)
    finally:
        for _, (_, fh) in files.items():
            fh.close()

    if resp.status_code == 201:
        data = resp.json()
        print(f"Uploaded  id={data['id']}  \"{data['title']}\"  {data['duration'] // 1000}s  "
              f"lyrics={'yes' if data.get('hasLyrics') else 'no'}  cover={'yes' if data.get('hasCover') else 'no'}")
    else:
        print(f"ERROR ({resp.status_code}): {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
