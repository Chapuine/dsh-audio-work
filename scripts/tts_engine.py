"""Cross-platform local TTS synthesis.

Engine resolution order (best quality first, fully offline):
  1. piper neural TTS
  2. macOS `say`
  3. espeak-ng
  4. Windows SAPI5 via PowerShell
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from device_probe import ProbeResult, probe
from utils import AudioWorkError, ensure_dir, log, run, which


DEFAULT_VOICE_HINTS = {
    "zh": {"macos_say": "Tingting", "espeak_ng": "cmn", "sapi5": "Microsoft Huihui Desktop"},
    "en": {"macos_say": "Samantha", "espeak_ng": "en", "sapi5": "Microsoft David Desktop"},
    "ja": {"macos_say": "Kyoko", "espeak_ng": "ja", "sapi5": "Microsoft Haruka Desktop"},
}


def synthesize(segment: dict[str, Any], workdir: Path, probe_result: ProbeResult | None = None) -> Path:
    probe_result = probe_result or probe()
    if probe_result.tts_engine == "none":
        raise AudioWorkError(
            "No local TTS engine found. Install one of:\n"
            "  - piper: https://github.com/rhasspy/piper (recommended, neural)\n"
            "  - espeak-ng on Linux: sudo apt install espeak-ng\n"
            "  - on macOS the built-in `say` command is used automatically"
        )

    text = (segment.get("text") or "").strip()
    if not text:
        raise AudioWorkError(f"empty text in segment {segment.get('id')!r}")

    seg_id = segment.get("id") or "seg"
    out_name = segment.get("output") or f"{seg_id}.wav"
    out_path = workdir / out_name
    ensure_dir(out_path.parent)

    voice = segment.get("voice") or "auto"
    rate = float(segment.get("rate") or 1.0)
    lang = segment.get("lang") or "zh"

    log(f"TTS [{seg_id}] engine={probe_result.tts_engine} voice={voice} rate={rate}")

    if probe_result.tts_engine == "piper":
        _synth_piper(text, voice, rate, out_path, lang)
    elif probe_result.tts_engine == "macos_say":
        _synth_say(text, voice, rate, out_path, lang)
    elif probe_result.tts_engine == "espeak_ng":
        _synth_espeak(text, voice, rate, out_path, lang)
    elif probe_result.tts_engine == "sapi5":
        _synth_sapi5(text, voice, rate, out_path, lang)
    else:
        raise AudioWorkError(f"unsupported tts engine: {probe_result.tts_engine}")

    if not out_path.exists() or out_path.stat().st_size < 100:
        raise AudioWorkError(f"TTS output missing or too small: {out_path}")
    log(f"TTS [{seg_id}] -> {out_path} ({out_path.stat().st_size} bytes)")
    return out_path


def _resolve_voice(segment_voice: str, engine: str, lang: str, probe_voices: list[str]) -> str:
    if segment_voice and segment_voice != "auto":
        return segment_voice
    hint = DEFAULT_VOICE_HINTS.get(lang, DEFAULT_VOICE_HINTS["en"]).get(engine, "")
    if hint and (not probe_voices or hint in probe_voices or engine == "piper"):
        return hint
    if probe_voices:
        prefix = {"zh": "zh_", "en": "en_", "ja": "ja_"}.get(lang, "")
        for v in probe_voices:
            if v.startswith(prefix):
                return v
        return probe_voices[0]
    return ""


def _synth_piper(text: str, voice: str, rate: float, out: Path, lang: str) -> None:
    import subprocess
    piper = which("piper") or "piper"
    voice_path = voice if voice != "auto" else os.environ.get("PIPER_VOICE", "")
    if not voice_path:
        raise AudioWorkError(
            "piper needs a voice model path. Set env PIPER_VOICE=/path/to/zh_CN-yunyang-medium.onnx "
            "or pass voice=<path.to.onnx> in the segment."
        )
    if not Path(voice_path).exists():
        raise AudioWorkError(f"piper voice model not found: {voice_path}")
    speed = 1.0 / max(0.3, min(3.0, rate))
    with open(out, "wb") as f:
        proc = subprocess.run(
            [piper, "-m", voice_path, "-f", str(out), "--length-scale", str(speed)],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if proc.returncode != 0:
        with open(out, "wb") as f:
            subprocess.run(
                [piper, "-m", voice_path, "-f", str(out)],
                input=text.encode("utf-8"),
                check=True,
            )


def _synth_say(text: str, voice: str, rate: float, out: Path, lang: str) -> None:
    voice = _resolve_voice(voice, "macos_say", lang, [])
    aiff = out.with_suffix(".aiff")
    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    cmd += ["-r", str(int(175 * rate))]
    cmd += ["-o", str(aiff), text]
    run(cmd)
    ffmpeg = which("ffmpeg")
    if ffmpeg:
        run([ffmpeg, "-y", "-i", str(aiff), "-ar", "44100", "-ac", "1", str(out)])
        aiff.unlink(missing_ok=True)
    else:
        aiff.rename(out)


def _synth_espeak(text: str, voice: str, rate: float, out: Path, lang: str) -> None:
    voice = _resolve_voice(voice, "espeak_ng", lang, [])
    wpm = int(160 * rate)
    cmd = ["espeak-ng", "-w", str(out), "-s", str(wpm)]
    if voice:
        cmd += ["-v", voice]
    cmd.append(text)
    run(cmd)


def _synth_sapi5(text: str, voice: str, rate: float, out: Path, lang: str) -> None:
    ps = which("powershell") or which("pwsh")
    if not ps:
        raise AudioWorkError("powershell not found for SAPI5 TTS")
    voice = _resolve_voice(voice, "sapi5", lang, [])
    sapi_rate = max(-1, min(1, int(rate - 1.0)))
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {sapi_rate}; "
    )
    if voice:
        script += f"$s.SelectVoice('{voice}'); "
    script += f"$s.SetOutputToWaveFile('{out}'); $s.Speak(@'\n{text}\n'@); $s.Dispose();"
    run([ps, "-NoProfile", "-Command", script])
