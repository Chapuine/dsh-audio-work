# dsh-audio-work

> 完全本地的音频制作工作台 —— 借用 dsh 当前调用的 DeepSeek 模型做任务规划，
> 用你自己设备的硬件完成 TTS 合成、Whisper 转写与 FFmpeg 硬件编码。
> **不调用任何云端音频 API。**

## 功能

- **录音/视频转写**：本地 `faster-whisper`，输出纯文字稿 + 可选 SRT 字幕。
- **AI 配音 TTS**：跨平台自动探测最优本地引擎——
  - 优先 [piper](https://github.com/rhasspy/piper) 神经 TTS（离线、音质接近真人）
  - macOS 自动回退到系统 `say`
  - Linux 回退到 `espeak-ng`
  - Windows 回退到 SAPI5（PowerShell）
- **剪辑混音**：分段 wav 拼接、跨淡入淡出、背景音乐叠混、淡入淡出。
- **硬件加速导出**：mp3（libmp3lame）、m4a/aac（macOS 自动用 `aac_at` 硬件编码器）、wav、flac。
- **规划层**：DeepSeek 模型把自然语言需求拆成结构化 JSON 计划（见 [`prompts/audio_planner.md`](prompts/audio_planner.md)），脚本只负责执行。

## 目录结构

```
dsh-audio-work/
├── SKILL.md                 # dsh Skill 定义：工作流与输出规范
├── README.md
├── requirements.txt
├── prompts/
│   └── audio_planner.md     # 给 DeepSeek 的规划提示词
├── examples/
│   └── demo_plan.json       # 可直接跑的示例计划
└── scripts/
    ├── audio_work.py        # 主入口：按 JSON 计划跑完整流水线
    ├── device_probe.py      # 探测本机 TTS / Whisper / FFmpeg 能力
    ├── tts_engine.py        # 跨平台 TTS 合成
    ├── transcribe.py        # 本地 Whisper 转写
    ├── editor.py            # FFmpeg 拼接 / 混音 / 编码导出
    └── utils.py
```

## 安装

把本仓库克隆到 dsh 的 skills 目录：

```bash
git clone https://github.com/Chapuine/dsh-audio-work.git
# 然后把 dsh-audio-work/ 文件夹放入 dsh 的 skills 目录（如 ~/.dsh/skills/）
```

## 依赖

| 组件 | 用途 | 安装 |
| --- | --- | --- |
| Python 3.9+ | 运行脚本 | 系统自带 / [python.org](https://python.org) |
| ffmpeg | 剪辑、编码导出 | macOS: `brew install ffmpeg`；Ubuntu: `sudo apt install ffmpeg` |
| faster-whisper | 本地语音转写（可选） | `pip install faster-whisper` |
| piper TTS | 高质量神经 TTS（可选，推荐） | [release](https://github.com/rhasspy/piper/releases) 或 `brew install piper` |
| macOS say | 系统 TTS（macOS 自带） | 无需安装 |
| espeak-ng | Linux 回退 TTS | `sudo apt install espeak-ng` |

最小可用（macOS，只做配音+导出）：仅需 ffmpeg，`say` 系统自带。

## 使用

### 1. 探测本机能力

```bash
python3 scripts/device_probe.py
```

输出示例：

```json
{
  "platform": "macos",
  "tts_engine": "macos_say",
  "tts_voices": ["zh_CN", "en_US"],
  "ffmpeg": "/opt/homebrew/bin/ffmpeg",
  "aac_encoder": "aac_at",
  "whisper_available": true,
  "whisper_impl": "faster_whisper"
}
```

### 2. 让 DeepSeek 生成计划

在 dsh 里直接说：
> "帮我把这段文案做成 2 分钟配音，加一点轻柔背景音乐，导出 mp3。"

dsh 会读 `prompts/audio_planner.md`，输出一份 JSON 计划并保存为 `plan.json`。

### 3. 执行

```bash
python3 scripts/audio_work.py examples/demo_plan.json --workdir ./workdir
```

产物会出现在 `./workdir/` 下：
- `seg1.wav`、`seg2.wav` … 分段配音
- `demo-final.mp3` 最终导出

### 4. 只做转写

```json
{
  "project_name": "my-episode",
  "transcribe": {
    "input": "/absolute/path/episode.mp3",
    "language": "zh",
    "model": "base",
    "output_text": "transcript.txt",
    "output_srt": "subtitles.srt"
  }
}
```

```bash
python3 scripts/audio_work.py plan.json
```

## 配置 piper（可选，推荐）

1. 下载一个语音模型，例如 `zh_CN-huayan-medium.onnx` 及同名 `.onnx.json`：
   https://huggingface.co/rhasspy/piper-voices
2. 设环境变量：
   ```bash
   export PIPER_VOICE=/absolute/path/zh_CN-huayan-medium.onnx
   ```
3. 脚本会自动从 `say`/`espeak` 切换到 piper。

## 设计原则

- **模型不动手，只动脑**：DeepSeek 只输出 JSON 计划，不直接生成二进制音频。
- **本机硬件优先**：TTS、ASR、编码全部本地执行；macOS 自动用 `aac_at` 硬件 AAC 编码。
- **引擎自动降级**：piper → say → espeak-ng，按本机能力透明切换，计划无需改动。
- **可复现**：JSON 计划可保存、可版本化、可二次执行。

## License

MIT
