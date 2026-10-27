"""FFmpeg-based audio editing: concat, crossfade, BGM mix, hardware-accelerated export."""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from device_probe import ProbeResult, probe
from utils import AudioWorkError, ensure_dir, file_duration, log, run, which


def render(tracks: list[dict[str, Any]], output: dict[str, Any], workdir: Path,
           probe_result: ProbeResult | None = None) -> Path:
    probe_result = probe_result or probe()
    if not probe_result.ffmpeg:
        raise AudioWorkError("ffmpeg not found; install ffmpeg to render output.")

    ensure_dir(workdir)
    out_path = workdir / output.get("path", "final.mp3")
    ensure_dir(out_path.parent)

    voice_tracks = [t for t in tracks if t.get("type") == "voice"]
    bgm_tracks = [t for t in tracks if t.get("type") == "bgm"]
    raw_tracks = [t for t in tracks if t.get("type") == "raw"]

    voice_bed = workdir / "_voice_bed.wav"
    if voice_tracks:
        _concat_voice(voice_tracks[0], voice_bed, probe_result)
    else:
        voice_bed = None

    inputs: list[str] = []
    filt_parts: list[str] = []
    mix_labels: list[str] = []
    idx = 0

    if voice_bed and voice_bed.exists():
        inputs += ["-i", str(voice_bed)]
        filt_parts.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo[v{idx}]")
        mix_labels.append(f"[v{idx}]")
        idx += 1

    for t in bgm_tracks:
        bgm_file = Path(t["file"])
        if not bgm_file.is_absolute():
            bgm_file = (workdir / bgm_file).resolve()
        if not bgm_file.exists():
            raise AudioWorkError(f"bgm file not found: {bgm_file}")
        inputs += ["-stream_loop", "-1" if t.get("loop", True) else "0", "-i", str(bgm_file)]
        vol = float(t.get("volume_db", -12))
        fade_in = float(t.get("fade_in", 0.0))
        fade_out = float(t.get("fade_out", 0.0))
        dur = file_duration(bgm_file)
        chain = f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={vol}dB"
        if fade_in > 0:
            chain += f",afade=t=in:st=0:d={fade_in}"
        if fade_out > 0:
            chain += f",afade=t=out:st={max(0, dur - fade_out)}:d={fade_out}"
        chain += f"[b{idx}]"
        filt_parts.append(chain)
        mix_labels.append(f"[b{idx}]")
        idx += 1

    for t in raw_tracks:
        f = Path(t["file"])
        if not f.is_absolute():
            f = (workdir / f).resolve()
        if not f.exists():
            raise AudioWorkError(f"raw track file not found: {f}")
        inputs += ["-i", str(f)]
        start = float(t.get("start", 0.0))
        end = t.get("end")
        vol = float(t.get("volume_db", 0.0))
        chain = f"[{idx}:a]"
        if start:
            chain += f"atrim=start={start}"
        if end is not None:
            chain += f":end={end}"
        chain += f",aresample=44100,aformat=channel_layouts=stereo,volume={vol}dB[r{idx}]"
        filt_parts.append(chain)
        mix_labels.append(f"[r{idx}]")
        idx += 1

    if not mix_labels:
        raise AudioWorkError("no tracks to render")

    mix_in = "".join(mix_labels)
    filt_parts.append(f"{mix_in}amix=inputs={len(mix_labels)}:normalize=0:duration=longest[mix]")
    filter_graph = ";".join(filt_parts)

    fmt = (output.get("format") or out_path.suffix.lstrip(".") or "mp3").lower()
    bitrate = output.get("bitrate", "192k")
    sample_rate = str(output.get("sample_rate", 44100))

    cmd = [probe_result.ffmpeg, "-y"] + inputs + ["-filter_complex", filter_graph, "-map", "[mix]"]
    if fmt == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif fmt in ("m4a", "aac", "mp4"):
        cmd += ["-c:a", probe_result.aac_encoder, "-b:a", bitrate]
    elif fmt == "wav":
        cmd += ["-c:a", "pcm_s16le"]
    elif fmt == "flac":
        cmd += ["-c:a", "flac"]
    else:
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
    cmd += ["-ar", sample_rate, str(out_path)]

    log("ffmpeg: " + " ".join(shlex.quote(c) for c in cmd))
    run(cmd)
    if not out_path.exists() or out_path.stat().st_size < 500:
        raise AudioWorkError(f"render output missing or too small: {out_path}")
    log(f"render -> {out_path} ({out_path.stat().st_size} bytes, {file_duration(out_path):.2f}s)")
    return out_path


def _concat_voice(voice_track: dict[str, Any], out: Path, probe_result: ProbeResult) -> None:
    files = voice_track.get("files") or []
    if not files:
        raise AudioWorkError("voice track has no files")
    resolved = []
    for f in files:
        p = Path(f)
        if not p.is_absolute():
            p = (out.parent / p).resolve()
        if not p.exists():
            raise AudioWorkError(f"voice segment not found: {p}")
        resolved.append(p)

    list_file = out.parent / "_concat_list.txt"
    list_file.write_text("".join(f"file '{p.resolve()}'\n" for p in resolved), encoding="utf-8")

    crossfade = float(voice_track.get("crossfade", 0.0))
    if crossfade > 0 and len(resolved) >= 2:
        inputs = []
        for p in resolved:
            inputs += ["-i", str(p)]
        filt: list[str] = []
        prev = "[0:a]"
        durations = [file_duration(p) for p in resolved]
        for i in range(1, len(resolved)):
            out_label = f"[xf{i}]"
            filt.append(f"{prev}[{i}:a]acrossfade=d={crossfade}:c1=tri:c2=tri{out_label}")
            prev = out_label
        run([probe_result.ffmpeg, "-y"] + inputs + ["-filter_complex", ";".join(filt), "-map", prev, str(out)])
    else:
        run([probe_result.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)])
