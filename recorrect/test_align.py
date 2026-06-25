"""Test script for recorrect DTW alignment algorithm.

Simulates: ASR with noisy/repeated lines + reference with correct but deduplicated lines.
"""

import sys
sys.path.insert(0, '/mnt/d/AiAlign')

from recorrect.aligner import align, get_matched_lines
from recorrect.similarity import normalize, similarity, MIN_MATCH_SCORE
from recorrect.io_utils import load_asr, load_ref, write_lrc, write_txt

# ── Test 1: Chinese lyrics with repetition ──
print("=" * 60)

# Reference: correct lyrics, chorus only written once
ref_lines = [
    "窗外的麻雀在电线杆上多嘴",
    "你说这一句很有夏天的感觉",
    "手中的铅笔在纸上来来回回",
    "我用几行字形容你是我的谁",
    "秋刀鱼的滋味猫跟你都想了解",
    "初恋的香味就这样被我们寻回",
    "那温暖的阳光像刚摘的鲜艳草莓",
    "你说你舍不得吃掉这一种感觉",
    "雨下整夜我的爱溢出就像雨水",
    "院子落叶跟我的思念厚厚一叠",
    "几句是非也无法将我的热情冷却",
    "你出现在我诗的每一页",
]

# ASR: noisy text with correct order, chorus appears multiple times
asr_lines = [
    "窗外的麻雀在电线感上多嘴",         # 0→0 错字: 杆→感
    "你说这一句很有夏天的感觉",         # 1→1 正确
    "手中的铅笔在纸上来来去去",         # 2→2 近似错字
    "我用几行字形容什么的谁",           # 3→3 缺字
    "秋刀鱼的滋味猫更想了解",           # 4→4 缺字
    "初恋的香味就这样被我们巡回",       # 5→5 错字: 回→回(不同语义)
    "那温暖的阳光像刚摘的草莓",         # 6→6 缺词: 鲜艳
    "你说舍不得吃掉这一种感觉",         # 7→7 缺字
    "雨下整夜我的爱溢出就像雨水",       # 8→8 近似
    "院子落叶跟我的思念厚厚一叠",       # 9→9 正确
    "几句是非也无法将我的热情冷却",     # 10→10 正确
    "你出现在我诗的每一页",            # 11→11 正确
    # ── 副歌重复 (Ref 只有一次, ASR 出现多次) ──
    "雨下整夜我的爱溢出就像雨水",       # 12→8 重复
    "院子落叶跟我的思念厚厚一叠",       # 13→9 重复
    "几句是非也没法将我的热情冷却",     # 14→10 近似重复
    "你出现在我诗的每一页",            # 15→11 重复
    # ── 第三遍副歌 ──
    "雨下整夜我的爱溢出就像雨水",       # 16→8 再重复
    "院子落叶跟我的思念厚厚一叠",       # 17→9 再重复
    "几句是非也无法将我的热情冷却",     # 18→10 再重复
    "你出现在我诗的每一页",            # 19→11 再重复
]

print("Test 1: Chinese lyrics with repeated chorus")
print(f"  ASR lines: {len(asr_lines)}")
print(f"  Ref lines: {len(ref_lines)}")

asr_norm = [normalize(s) for s in asr_lines]
ref_norm = [normalize(s) for s in ref_lines]

alignment = align(asr_norm, ref_norm)
matched = get_matched_lines(alignment)

print(f"  Matched: {len(matched)}")
print(f"  Repeat count: {sum(1 for m in matched if m['is_repeat'])}")
print()

# Verify: all ASR lines should be matched
matched_asr = {m['asr_index'] for m in matched}
if len(matched_asr) == len(asr_lines):
    print("  PASS: All ASR lines matched")
else:
    print(f"  FAIL: {len(asr_lines)} ASR lines, {len(matched_asr)} matched")

# Verify correct mapping
print("  Alignment:")
for m in matched:
    arrow = "→" if not m['is_repeat'] else "↻"
    print(f"    ASR[{m['asr_index']:2d}] {arrow} Ref[{m['ref_index']:2d}] "
          f"score={m['score']:.3f}  "
          f"asr=\"{asr_lines[m['asr_index']]}\""
          f" → ref=\"{ref_lines[m['ref_index']]}\"")

print()

# ── Test 2: Simple English with repetition ──
print("=" * 60)
print("Test 2: English lyrics with repetition")

ref_en = [
    "Hello darkness my old friend",
    "I've come to talk with you again",
    "Because a vision softly creeping",
    "Left its seeds while I was sleeping",
    "And the vision that was planted in my brain",
    "Still remains",
    "Within the sound of silence",
]

# ASR with noise and repetition
asr_en = [
    "Hello darkness my old friend",      # 0→0
    "I come to talk with you again",     # 1→1 've missing
    "Because a vision softly creeping",  # 2→2
    "Left its seeds while I was sleeping", # 3→3
    "And the vision planted in my brain", # 4→4 'that was' missing
    "Still remains",                     # 5→5
    "Within the sound of silence",       # 6→6
    # Repeat first verse
    "Hello darkness my old friend",      # 7→0 repeat
    "I come to talk with you again",     # 8→1 repeat
]

asr_en_norm = [normalize(s) for s in asr_en]
ref_en_norm = [normalize(s) for s in ref_en]

alignment_en = align(asr_en_norm, ref_en_norm)
matched_en = get_matched_lines(alignment_en)

print(f"  ASR lines: {len(asr_en)}, Ref lines: {len(ref_en)}, Matched: {len(matched_en)}")
for m in matched_en:
    arrow = "→" if not m['is_repeat'] else "↻"
    print(f"    ASR[{m['asr_index']}] {arrow} Ref[{m['ref_index']}] "
          f"score={m['score']:.3f}  \"{asr_en[m['asr_index']]}\" → \"{ref_en[m['ref_index']]}\"")

print()

# ── Test 3: Similarity function ──
print("=" * 60)
print("Test 3: Similarity function")
pairs = [
    ("雨下整夜我的爱溢出就像雨水", "雨下整夜我的爱溢出就像雨水", "identical"),
    ("雨下整夜我的爱溢出就像雨水", "雨下整夜我的爱就要像雨水", "partial error"),
    ("你出现在我诗的每一页", "你在我诗的每页", "missing chars"),
    ("Hello darkness my old friend", "Hello darkness my old friend", "identical EN"),
    ("Hello darkness my old friend", "Hello dark my friend", "missing EN"),
    ("Hello darkness", "黑暗", "different language"),
]
for a, b, label in pairs:
    s = similarity(a, b)
    print(f"  {label:20s}: \"{a}\" vs \"{b}\" → {s:.3f}")

print()
print("All tests done.")
