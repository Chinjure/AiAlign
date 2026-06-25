recorrect - ASR 歌词校准工具
=================================

功能：将 Qwen3-aligner 识别的歌词（ASR 文本）与 LRCLIB 搜索的参考歌词合并，
      用 ASR 的时序和顺序 + 参考歌词的准确文字，生成正确的歌词/LRC 文件。

原理：DTW 动态规划对齐，支持副歌重复跳回（jump_back），自动跳过幻听行和元数据行。


== 命令行用法 ==

python -m recorrect <asr文件> <参考歌词文件> [-o 输出前缀] [-f 输出格式]

  参数：
    asr文件          ASR 识别文本 (.txt / .srt / .json)
                       .txt  纯文本，一行一句
                       .srt  标准 SRT 字幕，保留时序信息
                       .json Qwen3-aligner 的 sentences JSON 输出
    参考歌词文件      纯文本 (.txt)，一行一句歌词 (来自 LRCLIB)

  可选：
    -o, --output     输出文件前缀 (不含扩展名)，默认 = asr文件名 + "_corrected"
    -f, --format     输出格式: txt, lrc, srt, json, all (默认 all)

  示例：
    # 纯文本对齐
    python -m recorrect asr.txt ref.txt

    # SRT 输入，输出 LRC + 校正 SRT
    python -m recorrect asr_output.srt lyrics.txt -o corrected -f all

    # 指定输出路径
    python -m recorrect asr.txt ref.txt -o result/七里香_corrected -f lrc


== Python API ==

    from recorrect import correct_lyrics

    result = correct_lyrics('asr.srt', 'ref_lyrics.txt')

    for line in result['corrected']:
        print(f"[{line['start_time']:.2f}] {line['text']}")
        # line['asr_text']   - ASR 原始文本
        # line['score']      - 匹配置信度 (0~1)
        # line['is_repeat']  - 是否为重复副歌行


== 输入格式说明 ==

[ASR 纯文本 .txt]
  一行一句，无时序：
    窗外的麻雀在电线感上多嘴
    你说这一句很有夏天的感觉
    ...

[ASR SRT .srt]
  标准 SRT 格式：
    1
    00:00:00,000 --> 00:00:03,500
    窗外的麻雀在电线感上多嘴
    ...

[ASR JSON .json]
  Qwen3 align() 输出格式：
    [
      {"text": "...", "start_time": 0.0, "end_time": 3.5},
      ...
    ]

[参考歌词 .txt]
  LRCLIB plainLyrics 格式，纯文本逐行：
    窗外的麻雀在电线杆上多嘴
    你说这一句很有夏天的感觉
    ...
  注意：副歌只需出现一次，程序会自动检测重复。


== 输出格式 ==

  .txt  校正后纯文本，一行一句，顺序同 ASR
  .lrc  标准 LRC 格式 [mm:ss.xx]，仅当输入含时序时生成
  .srt  校正后 SRT 字幕
  .json 完整对齐信息 (每行的 text, asr_text, score, ref_index 等)


== 依赖 ==

  Python >= 3.8 (仅标准库: difflib, json, re, argparse)


== 典型工作流 ==

  1. get_lyrics.py        → 从 LRCLIB 搜索参考歌词 (ref.txt)
  2. Qwen3-aligner        → 音频转录+对齐 (asr_output.srt)
  3. python -m recorrect asr_output.srt ref.txt -o result
                          → 校正生成 result.lrc + result.srt
  4. upload_song.py        → 上传歌曲 + LRC 到服务器
