# generate-lyrics

从音乐文件一键生成 LRC 歌词。全流程自动化，任一步失败自动回滚。

## 用法

```bash
python -m generate-lyrics <music_file> [options]
```

### 参数

| 参数 | 说明 |
|------|------|
| `music_file` | 音乐文件路径，支持 `.mp3` `.flac` `.wav` |
| `-o, --output` | 输出目录，默认同目录 |
| `--keep` | 保留中间文件（调试用） |

### 示例

```powershell
# 基本用法
D:\miniconda\envs\lyrics_align\python.exe -m generate-lyrics song.mp3

# 指定输出目录
D:\miniconda\envs\lyrics_align\python.exe -m generate-lyrics song.mp3 -o D:\output

# 保留中间文件调试
D:\miniconda\envs\lyrics_align\python.exe -m generate-lyrics song.mp3 --keep
```

## 流水线

```
音乐文件 (.mp3/.flac/.wav)
    │
    ├─ Step 1: 提取元数据 (mutagen)
    │     从 ID3/Vorbis 标签读取歌名、艺人
    │
    ├─ Step 2: 人声分离 (UVR MDX-NET, GPU)
    │     → {歌名}_(Vocals).wav
    │
    ├─ Step 3: 转录歌词 (Qwen3-ASR 1.7B, GPU)
    │     人声 → 文本
    │     → {艺人} - {歌名}_transcribed.txt
    │
    ├─ Step 4: 搜索歌词 + 校准 (LRCLIB API + recorrect)
    │     先精确匹配，再模糊搜索
    │     用参考歌词修正 ASR 转录错误
    │     → {艺人} - {歌名}_corrected.txt
    │     失败非致命：回退到原始 ASR 转录
    │
    ├─ Step 5: 歌词对齐 (MTL_BDR, CPU)
    │     人声 + 歌词 → 逐词强制对齐
    │     → {艺人} - {歌名}.lrc
    │
    └─ Step 6: 清理
           删除 .txt .wav .csv .lrc .srt .json 中间文件
```

## 错误处理

- **致命错误** (Step 1/2/3/5)：立即删除所有中间文件 → 写入 `error.log` → `exit(1)`
- **非致命错误** (Step 4)：警告后继续，不影响 LRC 生成
- `error.log` 格式：
  ```
  [2026-06-23 17:30:00] ERROR Step 1/6 (extract): Could not determine title/artist
  [2026-06-23 17:30:00] Cleaned 1 intermediate files
  ```

## 输出

| 产物 | 说明 |
|------|------|
| `{艺人} - {歌名}.lrc` | 最终 LRC 歌词文件（唯一保留产物） |
| `error.log` | 错误日志（仅在出错时生成） |

## 环境

- **Python**: `lyrics_align` conda 环境 (Python 3.9)
- **依赖**: mutagen, requests
- **子进程环境**:
  - `aligner_cpu` (Python 3.10) — 人声分离 + 转录 + 歌词校准
  - `lyrics_align` (Python 3.9) — 歌词对齐
