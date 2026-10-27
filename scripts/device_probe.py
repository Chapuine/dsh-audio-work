"""Probe available local audio engines and hardware codecs."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Literal

from utils import AudioWorkError, log, platform_tag, run, which


TTSEngine = Literal["piper", "macos_say", "espeak_ng", "sapi5", "none"]


@dataclass
class ProbeResult:
    platform: str
    tts_engine: TTSEngine = "none"
    tts_voices: list[str] = field(default_factory=list)
    ffmpeg: str | None = None
    ffprobe: str | None = None
    audio_encoder: str = "libmp3lame"
    aac_encoder: str = "aac"
    whisper_available: bool = False
    whisper_impl: str = "none"
    notes: list[str] = field(default_factory=list)


def probe() -> ProbeResult:
    res = ProbeResult(platform=platform_tag())

    res.ffmpeg = which("ffmpeg")
    res.ffprobe = which("ffprobe")
    if not res.ffmpeg:
        res.notes.append("ffmpeg not found; audio editing/export will not work.")

    res.aac_encoder = _pick_aac_encoder(res.ffmpeg)
    res.audio_encoder = "libmp3lame"

    res.tts_engine, res.tts_voices = _probe_tts(res.platform)
    res.whisper_available, res.whisper_impl = _probe_whisper()

    return res


def _pick_aac_encoder(ffmpeg: str | None) -> str:
    if not ffmpeg:
        return "aac"
    try:
        proc = run([ffmpeg, "-hide_banner", "-encoders"], capture=True, check=False)
        out = (proc.stdout or "").lower()
    except Exception:
        return "aac"
    if platform_tag() == "macos" and "aac_at" in out:
        return "aac_at"
    if "libfdk_aac" in out:
        return "libfdk_aac"
    return "aac"


def _probe_tts(plat: str) -> tuple[TTSEngine, list[str]]:
    piper = which("piper")
    if piper:
        return "piper", []
    if plat == "macos" and which("say"):
        return "macos_say", _list_macos_voices()
    if plat == "linux" and which("espeak-ng"):
        return "espeak_ng", []
    if plat == "windows":
        ps = which("powershell") or which("pwsh")
        if ps:
            return "sapi5", []
    return "none", []


def _list_macos_voices() -> list[str]:
    try:
        proc = run(["say", "-v", "?"], capture=True, check=False)
    except Exception:
        return []
    voices: list[str] = []
    for line in (proc.stdout or "").splitlines():
        if line.strip():
            voices.append(line.split()[0])
    return voices


def _probe_whisper() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401
        return True, "faster_whisper"
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return True, "openai_whisper"
    except ImportError:
        pass
    return False, "none"


def main() -> None:
    res = probe()
    print(json.dumps({
        "platform": res.platform,
        "tts_engine": res.tts_engine,
        "tts_voices": res.tts_voices[:30],
        "tts_voices_count": len(res.tts_voices),
        "ffmpeg": res.ffmpeg,
        "ffprobe": res.ffprobe,
        "aac_encoder": res.aac_encoder,
        "mp3_encoder": res.audio_encoder,
        "whisper_available": res.whisper_available,
        "whisper_impl": res.whisper_impl,
        "notes": res.notes,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
