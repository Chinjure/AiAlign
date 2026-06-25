"""Error logging for generate-lyrics pipeline."""

import sys
from datetime import datetime


def log_error(msg: str, log_file: str = None):
    """Write timestamped error message to stderr and optional log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr)
    if log_file:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def log_info(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")
