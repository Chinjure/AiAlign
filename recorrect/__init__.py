"""recorrect: Calibrate ASR lyrics against reference lyrics using DTW alignment."""

from .pipeline import correct_lyrics, correct_lyrics_lrc
from .aligner import align, get_matched_lines
from .similarity import similarity, normalize
from .io_utils import load_asr, load_ref, load_lrc, write_lrc, write_txt, write_srt, write_json_output, has_timing

__version__ = '0.1.0'
__all__ = [
    'correct_lyrics',
    'align',
    'get_matched_lines',
    'similarity',
    'normalize',
    'load_asr',
    'load_ref',
    'write_lrc',
    'write_txt',
    'write_srt',
    'write_json_output',
    'load_lrc',
    'has_timing',
    'correct_lyrics_lrc',
]
