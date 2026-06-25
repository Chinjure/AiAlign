import sys
sys.path.insert(0, r'D:\AiAlign')
from recorrect.io_utils import load_asr
entries = load_asr(r'D:\CloudMusic\download\The Kinks\To the Bone\The Kinks - Village Green Preservation Society_transcribed.txt')
print(f'Lines: {len(entries)}')
for i, e in enumerate(entries):
    t = e['text']
    print(f'  {i}: {t[:90]}')
