---
name: dsh-audio-work
description: 本地全流程音频工作台：录音/视频转写（Whisper）、AI 配音 TTS（跨平台自动选最优引擎）、剪辑拼接、背景音乐混音、硬件加速编码导出。直接复用 dsh 当前调用的 DeepSeek 模型做任务规划，音频合成与编码全部在用户本机硬件完成，不调用任何云端音频 API。适用于"把这段文案做成配音""给录音加背景音乐""把视频转成文字稿""剪辑一段音频导出 mp3"等场景。
---

# dsh-audio-work

## 概述

让 dsh（DeepSeek Harness）成为一个**完全本地**的音频制作工作台：

- **规划大脑**：dsh 当前的 DeepSeek 模型把用户的自然语言需求拆成结构化 JSON 任务计划（见 `prompts/audio_planner.md`）。
- **本地手脚**：`scripts/audio_work.py` 在用户设备上执行——
  - 语音转写：`faster-whisper`（本地 CPU/CUDA 推理）
  - 语音合成：自动探测最优本地引擎（piper 神经 TTS → macOS `say` → espeak-ng → Windows SAPI5）
  - 剪辑混音：`ffmpeg`，自动选用硬件加速 AAC 编码器（macOS `aac_at`）
- **零云端音频 API**：不调用火山、Azure、Google 等任何 TTS/ASR 云服务。

## 工作流

### 第 1 步：理解需求并探测设备

收到用户音频需求后，先在本机跑一次能力探测：

```bash
python3 <SKILL_ROOT>/scripts/device_probe.py
```

确认：TTS 引擎、ffmpeg 是否存在、Whisper 是否安装、可用音色列表。
若关键组件缺失，明确告知用户安装命令（见 README「依赖」），不要假装能跑。

### 第 2 步：生成任务计划

把 `prompts/audio_planner.md` 作为系统提示词，让 DeepSeek 模型根据用户需求输出一份 JSON 计划。
计划必须严格遵循提示词中的 schema，**只输出一个 ```json 代码块**。

把计划保存为 `<workdir>/plan.json`。

### 第 3 步：本地执行

```bash
python3 <SKILL_ROOT>/scripts/audio_work.py <workdir>/plan.json --workdir <workdir> --out-report <workdir>/report.json
```

脚本会依次执行：
1. 可选：`transcribe` 段——用 Whisper 把输入音视频转成文字稿（可选同时输出 `.srt`）。
2. `tts` 段——逐段合成语音为 wav。
3. `tracks` + `output`——拼接人声轨、混入背景音乐、硬件编码导出最终文件。

### 第 4 步：交付

从 `report.json` 读取 `artifacts.final`（最终音频）、`artifacts.transcript`（文字稿）、`artifacts.tts_segments`（分段 wav），把绝对路径返回给用户。

## 模式选择

| 用户意图 | 计划中包含 |
| --- | --- |
| 录音/视频转文字、出字幕 | `transcribe`（+ `output_srt`），无 tts/tracks |
| 文案转配音、多段朗读 | `tts` + `tracks[voice]` + `output` |
| 配音 + 背景音乐 | `tts` + `tracks[voice, bgm]` + `output` |
| 剪辑已有音频（裁剪/拼接/转码） | `tracks[raw]` + `output`，无 tts |
| 录音 → 转写 → 改写文案 → 重新配音 | `transcribe` → 读 transcript → `tts` + `output` |

## 输出规范

- 最终交付必须给出**绝对路径**，并标注格式（mp3/m4a/wav）和时长。
- 转写稿要按说话人/段落分段，不要把整段压成一行。
- 若某步失败（缺 ffmpeg / 缺 Whisper / 缺语音模型），报告具体缺失组件和安装命令，**不要编造音频**。
- 中间产物（分段 wav、concat list）保留在 workdir，方便用户二次调整；最终文件单独标注。

## 注意事项

- TTS 引擎由脚本自动探测，不要在计划里硬编码音色名；用 `"voice": "auto"`，让本机选最优。
- piper 语音模型（.onnx）需要用户自行下载并通过环境变量 `PIPER_VOICE` 指定路径；否则自动回退到系统 TTS。
- Whisper 首次运行会下载模型（base 约 150MB），下载后完全离线。
- 所有输入文件路径必须是用户提供或本会话解析过的绝对路径，不要臆造。
- 处理含隐私的录音时，仅输出与任务相关的转写/剪辑结果。
