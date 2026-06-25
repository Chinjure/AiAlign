"""generate-lyrics: end-to-end LRC generation from music files."""

from .main import main
from .lrclib import search as search_lrclib
from .pipeline import sanitize_filename

__version__ = '0.1.0'
__all__ = ['main', 'search_lrclib', 'sanitize_filename']
