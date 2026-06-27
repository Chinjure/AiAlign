# AiAlign

端到端歌词 LRC 生成管线：提取元数据 → 搜索歌词 → 人声分离 → 语音转录 → 校准 → 对齐 → LRC 文件。

## 安装

### 系统要求

- Python >= 3.10
- ffmpeg（安装脚本会自动安装）
- NVIDIA GPU + 驱动 >= 535（可选，CPU 也能跑但会慢很多）

### 一键安装

```bash
# 默认安装（GPU 版 PyTorch，自动检测 GPU）
bash install.sh

# CPU 版
bash install.sh --cpu
```

`install.sh` 做了这些事：

1. 自动安装系统依赖（ffmpeg, python3-dev），支持 apt/brew/pacman/dnf
2. 创建 Python 虚拟环境 `venv/`
3. 安装 Python 依赖
4. 安装 PyTorch（GPU 版，使用 `--index-url` 从 PyTorch CUDA 索引下载）

### 手动安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu130
pip install onnxruntime-gpu
```

## 模型文件

| 模型 | 大小 | 用途 | 获取方式 |
|------|------|------|----------|
| **Qwen3-ASR 1.7B** | ~4.4 GB | 歌声转录 | 首次运行时自动从 HuggingFace/ModelScope 下载 |
| UVR MDX-NET | 64 MB | 人声分离 | 已包含在仓库中 |
| MTL_BDR checkpoints | 123 MB | 歌词音频对齐 | 已包含在仓库中 |
| FireRedVAD | 2.3 MB | 语音活动检测 | 已包含在仓库中 |

### 手动下载 Qwen3-ASR（可选，加速首次运行）

```bash
# HuggingFace
pip install huggingface_hub
huggingface-cli download Qwen/Qwen3-ASR-1.7B \
  --local-dir Qwen3-aligner-main/Qwen/Qwen3-ASR-1.7B

# ModelScope（国内更快）
pip install modelscope
python -c "from modelscope import snapshot_download; \
  snapshot_download('qwen/Qwen3-ASR-1.7B', \
  local_dir='Qwen3-aligner-main/Qwen/Qwen3-ASR-1.7B')"
```

## 使用

```bash
source venv/bin/activate

# 单文件
python -m generate-lyrics music.mp3

# 指定输出目录
python -m generate-lyrics music.mp3 -o ./output

# 保留中间文件
python -m generate-lyrics music.mp3 --keep

# 批量处理
python -m generate-lyrics --batch ./music_dir

# 上传到服务器
python -m generate-lyrics music.mp3 --upload
```

### 分步运行

```bash
source venv/bin/activate

# 1. 人声分离
python vocal_separate.py music.mp3 output/

# 2. 语音转录
python Qwen3-aligner-main/cli.py transcribe output/music_(Vocals).wav -l English -m 1.7B

# 3. ASR 校准（可选）
python -m recorrect asr.txt reference.txt -o out -f all

# 4. 歌词对齐
python align_one.py output/music_(Vocals).wav lyrics.txt output.lrc

# 5. 上传
python upload_song.py music.mp3 --lrc output.lrc --server http://your-server:port
```

## 管线架构

```
music file
  ├─ 元数据提取 (mutagen)
  ├─ LRCLIB 歌词搜索
  ├─ 人声分离 (UVR MDX-NET, GPU)
  ├─ 语音转录 (Qwen3-ASR 1.7B, GPU)
  ├─ ASR 校准 (recorrect, CPU)
  ├─ 歌词对齐 (MTL_BDR, CPU)
  └─ LRC 输出 / 上传
```

## 目录结构

```
AiAlign/
├── install.sh                 # 一键安装脚本
├── requirements.txt           # Python 依赖
├── generate-lyrics/           # 管线入口
├── recorrect/                 # ASR 歌词校准
├── Qwen3-aligner-main/        # Qwen3-ASR 转录
├── LyricsAlignment-MTL/       # MTL_BDR 歌词对齐
├── SeperateModels/            # UVR 人声分离模型
├── vocal_separate.py          # 人声分离脚本
├── align_one.py               # 单文件对齐脚本
└── upload_song.py             # 上传脚本
```

## 致谢

本项目基于以下开源项目构建：

| 项目 | 用途 | 协议 |
|------|------|------|
| [Qwen3-Aligner](https://github.com/QwenLM/Qwen3-ASR) | 语音转录与对齐 | Apache 2.0 |
| [LyricsAlignment-MTL](https://github.com/jhuang448/LyricsAlignment-MTL) | 歌词音频对齐 | MIT |
| [python-audio-separator](https://github.com/karaokenerds/python-audio-separator) | 人声分离 (UVR MDX-NET) | MIT |

## License

本项目基于 MIT 协议开源。依赖的子项目各保留其原始协议，详见 [NOTICE](NOTICE)。
