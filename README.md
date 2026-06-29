# AiAlign

端到端歌词 LRC 生成管线：提取元数据 → 搜索歌词 → 人声分离 → 语音转录 → 校准 → 对齐 → LRC 文件。

*An end-to-end lyrics-to-LRC pipeline: metadata extraction → lyric search → vocal separation → transcription → calibration → alignment → LRC output.*

---

## ⚠️ 硬件要求 / Hardware Requirements

> **强烈建议使用 NVIDIA 独立显卡运行本项目。** CPU 模式可以运行，但人声分离和语音转录两个步骤会非常慢（单首歌可能需要 20–30 分钟甚至更长）。使用独显可将总耗时缩短至 2–5 分钟。
>
> **A dedicated NVIDIA GPU is strongly recommended.** While CPU mode works, the vocal separation and transcription steps will be extremely slow without one (20–30+ minutes per song). With a GPU, the entire pipeline completes in 2–5 minutes.

| 模式 / Mode | 人声分离 / Separation | 语音转录 / Transcription | 总耗时（估算） / Est. Total |
|-------------|----------------------|--------------------------|---------------------------|
| **NVIDIA GPU** | ~30s–1min | ~1–2min | **2–5 min** |
| CPU only | ~10–15min | ~15–20min | **20–30+ min** |

### GPU 模式要求 / GPU Requirements

- **NVIDIA GPU**（AMD / Intel 核显不支持 CUDA）
- **驱动版本 / Driver >= 535**
- **CUDA 13.0**（install.sh 默认安装；如需其他版本，修改脚本中的 `TORCH_INDEX`）

---

## 安装 / Installation

### 一键安装 / One-shot Setup

```bash
# GPU 版（默认，自动检测独显）/ GPU mode (default)
bash install.sh

# CPU 版 / CPU-only mode
bash install.sh --cpu
```

`install.sh` 会自动完成以下步骤：

1. 安装系统依赖（ffmpeg, python3-dev），支持 apt/brew/pacman/dnf
2. 创建 Python 虚拟环境 `venv/`
3. 安装 Python 依赖
4. 安装 PyTorch + torchaudio + torchcodec
5. 下载 UVR MDX-NET 人声分离模型（~64 MB）

### 手动安装 / Manual Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# GPU
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu130
pip install onnxruntime-gpu torchcodec

# CPU
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install torchcodec
```

---

## 模型文件 / Model Files

| 模型 / Model | 大小 / Size | 用途 / Purpose | 获取方式 / Source |
|-------------|------------|---------------|-----------------|
| **Qwen3-ASR 1.7B** | ~4.4 GB | 歌声转录 / Vocal transcription | 首次运行时自动下载 / Auto-downloaded on first run |
| UVR MDX-NET | 64 MB | 人声分离 / Vocal separation | `install.sh` 自动下载 |
| MTL_BDR checkpoints | 123 MB | 歌词对齐 / Lyrics alignment | Git LFS |
| FireRedVAD | 2.3 MB | 语音活动检测 / VAD | Git LFS |

### 手动下载 Qwen3-ASR（可选，加速首次运行）

```bash
# HuggingFace
pip install huggingface_hub
huggingface-cli download Qwen/Qwen3-ASR-1.7B \
  --local-dir Qwen3-aligner-main/Qwen/Qwen3-ASR-1.7B

# ModelScope（国内更快 / faster in mainland China）
pip install modelscope
python -c "from modelscope import snapshot_download; \
  snapshot_download('qwen/Qwen3-ASR-1.7B', \
  local_dir='Qwen3-aligner-main/Qwen/Qwen3-ASR-1.7B')"
```

---

## 使用 / Usage

```bash
source venv/bin/activate

# 单文件 / Single file
python -m generate-lyrics music.mp3

# 使用本地歌词参考 / With local reference lyrics
python -m generate-lyrics music.mp3 --ref lyrics.txt

# 指定输出目录 / Specify output directory
python -m generate-lyrics music.mp3 -o ./output

# 保留中间文件 / Keep intermediate files
python -m generate-lyrics music.mp3 --keep

# 批量处理 / Batch processing
python -m generate-lyrics --batch ./music_dir
```

### 分步运行 / Step-by-step

```bash
source venv/bin/activate

# 1. 人声分离 / Vocal separation
python vocal_separate.py music.mp3 output/

# 2. 语音转录 / Transcription
python Qwen3-aligner-main/cli.py transcribe output/music_(Vocals).wav -l English -m 1.7B

# 3. ASR 校准（可选） / ASR calibration (optional)
python -m recorrect asr.txt reference.txt -o out -f all

# 4. 歌词对齐 / Lyrics alignment
python align_one.py output/music_(Vocals).wav lyrics.txt output.lrc
```

---

## 管线架构 / Pipeline Architecture

```
music file
  ├─ 元数据提取 / Metadata extraction (mutagen)
  ├─ LRCLIB 歌词搜索 / Lyric search  or  --ref local file
  ├─ 人声分离 / Vocal separation (UVR MDX-NET)
  ├─ 语音转录 / Transcription (Qwen3-ASR 1.7B)
  ├─ ASR 校准 / Calibration (recorrect)
  ├─ 歌词对齐 / Alignment (MTL_BDR)
  └─ LRC 输出 / LRC output
```

---

## 目录结构 / Directory Structure

```
AiAlign/
├── install.sh                 # 一键安装脚本 / One-shot setup
├── requirements.txt           # Python 依赖
├── generate-lyrics/           # 管线入口 / Pipeline entry point
├── recorrect/                 # ASR 歌词校准 / Lyric calibration
├── Qwen3-aligner-main/        # Qwen3-ASR 转录 / Transcription
├── LyricsAlignment-MTL/       # MTL_BDR 歌词对齐 / Alignment
├── SeperateModels/            # UVR 人声分离模型 / Separation models
├── vocal_separate.py          # 人声分离脚本 / Vocal separator
└── align_one.py               # 单文件对齐脚本 / Single-file aligner
```

---

## 致谢 / Acknowledgments

本项目基于以下开源项目构建 / *Built on the following open-source projects:*

| 项目 / Project | 用途 / Purpose | 协议 / License |
|------|------|------|
| [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) | 语音转录 / Transcription | Apache 2.0 |
| [LyricsAlignment-MTL](https://github.com/jhuang448/LyricsAlignment-MTL) | 歌词对齐 / Alignment | MIT |
| [python-audio-separator](https://github.com/karaokenerds/python-audio-separator) | 人声分离 / UVR MDX-NET | MIT |

## License

本项目基于 MIT 协议开源。依赖的子项目各保留其原始协议，详见 [NOTICE](NOTICE)。

*MIT License. Dependent subprojects retain their original licenses — see [NOTICE](NOTICE).*
