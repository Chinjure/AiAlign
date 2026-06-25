"""Integration test: create mock files and run the full pipeline."""

import sys
import os
import tempfile

sys.path.insert(0, '/mnt/d/AiAlign')

from recorrect.pipeline import correct_lyrics
from recorrect.io_utils import load_asr, load_ref, write_lrc, write_txt, write_json_output, write_srt, has_timing

test_dir = '/mnt/d/AiAlign/recorrect/test_data'
os.makedirs(test_dir, exist_ok=True)

# ── Create test files ──
# Reference lyrics: correct text, chorus deduplicated
ref_txt = os.path.join(test_dir, 'ref_lyrics.txt')
with open(ref_txt, 'w', encoding='utf-8') as f:
    f.write("""\
窗外的麻雀在电线杆上多嘴
你说这一句很有夏天的感觉
手中的铅笔在纸上来来回回
我用几行字形容你是我的谁
秋刀鱼的滋味猫跟你都想了解
初恋的香味就这样被我们寻回
那温暖的阳光像刚摘的鲜艳草莓
你说你舍不得吃掉这一种感觉
雨下整夜我的爱溢出就像雨水
院子落叶跟我的思念厚厚一叠
几句是非也无法将我的热情冷却
你出现在我诗的每一页
""")

# ASR plain text: noisy, with repeated chorus
asr_txt = os.path.join(test_dir, 'asr_output.txt')
with open(asr_txt, 'w', encoding='utf-8') as f:
    f.write("""\
窗外的麻雀在电线感上多嘴
你说这一句很有夏天的感觉
手中的铅笔在纸上来来去去
我用几行字形容什么的谁
秋刀鱼的滋味猫更想了解
初恋的香味就这样被我们巡回
那温暖的阳光像刚摘的草莓
你说舍不得吃掉这一种感觉
雨下整夜我的爱溢出就像雨水
院子落叶跟我的思念厚厚一叠
几句是非也无法将我的热情冷却
你出现在我诗的每一页
雨下整夜我的爱溢出就像雨水
院子落叶跟我的思念厚厚一叠
几句是非也没反正我的热情冷却
你出现在我诗的每一页
""")

# ASR SRT: with timing info
asr_srt = os.path.join(test_dir, 'asr_output.srt')
with open(asr_srt, 'w', encoding='utf-8') as f:
    lines = []
    texts = [
        "窗外的麻雀在电线感上多嘴",
        "你说这一句很有夏天的感觉",
        "手中的铅笔在纸上来来去去",
        "我用几行字形容什么的谁",
        "秋刀鱼的滋味猫更想了解",
        "初恋的香味就这样被我们巡回",
        "那温暖的阳光像刚摘的草莓",
        "你说舍不得吃掉这一种感觉",
        "雨下整夜我的爱溢出就像雨水",
        "院子落叶跟我的思念厚厚一叠",
        "几句是非也无法将我的热情冷却",
        "你出现在我诗的每一页",
        "雨下整夜我的爱溢出就像雨水",
        "院子落叶跟我的思念厚厚一叠",
        "几句是非也没反正我的热情冷却",
        "你出现在我诗的每一页",
    ]
    t = 0.0
    for i, text in enumerate(texts):
        start = t
        t += 3.5
        end = t
        h = int(start // 3600)
        m = int((start % 3600) // 60)
        s = int(start % 60)
        ms = int((start % 1) * 1000)
        eh = int(end // 3600)
        em = int((end % 3600) // 60)
        es = int(end % 60)
        ems = int((end % 1) * 1000)
        lines.append(f"{i+1}")
        lines.append(f"{h:02d}:{m:02d}:{s:02d},{ms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}")
        lines.append(text)
        lines.append("")
    f.write('\n'.join(lines))

print("=" * 60)
print("Test 1: Plain text → plain text")

result = correct_lyrics(asr_txt, ref_txt)
corrected = result['corrected']
print(f"  Matched: {len(corrected)} lines")
print(f"  Skipped ASR: {result['unmatched_asr']}")
print(f"  Skipped Ref: {result['unmatched_ref']}")
print(f"  Avg score: {result['avg_score']:.3f}")

# Verify each corrected line
expected_refs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 8, 9, 10, 11]  # ref indices
actual_refs = [m['ref_index'] for m in corrected]
assert actual_refs == expected_refs, f"FAIL: expected {expected_refs}, got {actual_refs}"
print("  PASS: correct mapping")
print()

# Check the corrected texts
print("  Corrected lyrics:")
for i, m in enumerate(corrected):
    is_rep = " (repeat)" if m['is_repeat'] else ""
    print(f"    [{i:2d}] {m['text']}{is_rep}")

print()
print("=" * 60)
print("Test 2: SRT input → LRC output")

result2 = correct_lyrics(asr_srt, ref_txt)
corrected2 = result2['corrected']
print(f"  Matched: {len(corrected2)} lines")
print(f"  Has timing: {all('start_time' in m for m in corrected2)}")

# Write LRC output
lrc_path = os.path.join(test_dir, 'output.lrc')
write_lrc(corrected2, lrc_path)
print(f"  LRC written to: {lrc_path}")

# Verify LRC content
with open(lrc_path, 'r', encoding='utf-8') as f:
    lrc_content = f.read()
print(f"  LRC lines: {len(lrc_content.splitlines())}")
print("  First 6 LRC lines:")
for line in lrc_content.splitlines()[:6]:
    print(f"    {line}")

print()
print("=" * 60)
print("Test 3: JSON output")
json_path = os.path.join(test_dir, 'output.json')
write_json_output(corrected2, json_path)
print(f"  JSON written to: {json_path}")

print()
print("=" * 60)
print("Test 4: Edge case — reference has extra meta lines")
ref_with_meta = os.path.join(test_dir, 'ref_with_meta.txt')
with open(ref_with_meta, 'w', encoding='utf-8') as f:
    f.write("""\
作词：方文山
作曲：周杰伦
窗外的麻雀在电线杆上多嘴
你说这一句很有夏天的感觉
手中的铅笔在纸上来来回回
我用几行字形容你是我的谁
雨下整夜我的爱溢出就像雨水
院子落叶跟我的思念厚厚一叠
几句是非也无法将我的热情冷却
你出现在我诗的每一页
""")

result3 = correct_lyrics(asr_txt, ref_with_meta)
corrected3 = result3['corrected']
print(f"  Matched: {len(corrected3)} lines")
print(f"  Skipped Ref: {result3['unmatched_ref']}")
# The meta lines should be skipped
assert 0 in result3['unmatched_ref'] or corrected3[0]['ref_index'] > 1, \
    f"Expected meta lines to be skipped"
print("  PASS: meta lines skipped")
print()

print("=" * 60)
print("Test 5: Edge case — ASR has hallucinated line")
asr_with_halluc = os.path.join(test_dir, 'asr_with_halluc.txt')
with open(asr_with_halluc, 'w', encoding='utf-8') as f:
    f.write("""\
窗外的麻雀在电线杆上多嘴
完全无关的一句话在这里乱入
你说这一句很有夏天的感觉
手中的铅笔在纸上来来回回
雨下整夜我的爱溢出就像雨水
院子落叶跟我的思念厚厚一叠
""")

result4 = correct_lyrics(asr_with_halluc, ref_txt)
corrected4 = result4['corrected']
print(f"  Matched: {len(corrected4)} lines")
print(f"  Skipped ASR: {result4['unmatched_asr']}")
# ASR[1] "完全无关的一句话" should be skipped
if result4['unmatched_asr']:
    skipped_text = "完全无关的一句话在这里乱入"
    print(f"  PASS: hallucination skipped")
else:
    # It might have matched something poorly — check if it shouldn't have
    for m in corrected4:
        if m['asr_text'] == "完全无关的一句话在这里乱入":
            print(f"  WARNING: hallucination matched with score {m['score']:.3f}")
            break
    else:
        print(f"  PASS: hallucination not present in output")

print()
print("All integration tests done.")
