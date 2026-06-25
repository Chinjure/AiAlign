"""Track and clean intermediate files."""

import os
from .logger import log_info


class Cleaner:
    """Tracks created files and cleans them on failure or completion."""

    def __init__(self):
        self.files: list[str] = []

    def track(self, path: str):
        """Register a file for later cleanup."""
        if path and os.path.exists(path):
            self.files.append(path)

    def track_all(self, paths: list[str]):
        for p in paths:
            self.track(p)

    def clean_all(self):
        """Remove all tracked files."""
        cleaned = 0
        for f in self.files:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    log_info(f"  Cleaned: {os.path.basename(f)}")
                    cleaned += 1
            except OSError:
                pass
        self.files.clear()
        return cleaned

    def clean_and_exit(self, error_log: str, msg: str, code: int = 1):
        """Clean all tracked files, write error log, and exit."""
        from .logger import log_error
        log_error(f"ERROR: {msg}", error_log)
        n = self.clean_all()
        if n > 0:
            log_error(f"Cleaned {n} intermediate files", error_log)
        import sys
        sys.exit(code)
