"""Local speech-to-text via faster-whisper (preferred) or openai-whisper."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from device_probe import ProbeResult, probe
from utils import AudioWorkError, ensure_dir, log


def transcribe(spec: dict[str, Any], workdir: Path, probe_result: ProbeResult | None = None) -> Path:
    probe_result = probe_result or probe()
    if not probe_result.whisper_available:
        raise AudioWorkError(
            "Whisper is not installed. Install offline transcription:\n"
            "  pip install faster-whisper\n"
            "Then re-run. First run downloads a model (~150MB for base)."
        )

    inp = Path(spec["input"]).expanduser().resolve()
    if not inp.exists():
        raise AudioWorkError(f"transcribe input not found: {inp}")

    lang = None if spec.get("language", "auto") in ("", "auto") else spec.get("language")
    model_size = spec.get("model", "base")
    out_txt = workdir / (spec.get("output_text") or "transcript.txt")
    ensure_dir(out_txt.parent)

    log(f"transcribe {inp.name} via {probe_result.whisper_impl} model={model_size} lang={lang or 'auto'}")

    if probe_result.whisper_impl == "faster_whisper":
        _run_faster_whisper(inp, model_size, lang, out_txt, spec.get("output_srt"))
    else:
        _run_openai_whisper(inp, model_size, lang, out_txt, spec.get("output_srt"))

    log(f"transcript -> {out_txt} ({out_txt.stat().st_size} bytes)")
    return out_txt


def _run_faster_whisper(inp: Path, model_size: str, lang: str | None, out_txt: Path, srt_rel: str | None) -> None:
    from faster_whisper import WhisperModel  # type: ignore

    device = "cuda" if os.environ.get("USE_CUDA", "0") == "1" else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(str(inp), language=lang, vad_filter=True)

    lines: list[str] = []
    srt_lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        lines.append(text)
        if srt_rel:
            srt_lines.append(f"{i}\n{_ts(seg.start)} --> {_ts(seg.end)}\n{text}\n")

    out_txt.write_text("\n".join(lines), encoding="utf-8")
    if srt_rel:
        srt_path = out_txt.parent / srt_rel
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        log(f"srt subtitle -> {srt_path}")


def _run_openai_whisper(inp: Path, model_size: str, lang: str | None, out_txt: Path, srt_rel: str | None) -> None:
    import whisper  # type: ignore

    model = whisper.load_model(model_size)
    result = model.transcribe(str(inp), language=lang)
    out_txt.write_text(result.get("text", "").strip(), encoding="utf-8")
    if srt_rel:
        from whisper.utils import get_writer  # type: ignore
        writer = get_writer("srt", str(out_txt.parent))
        writer(result, out_txt.parent / srt_rel)


def _ts(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
