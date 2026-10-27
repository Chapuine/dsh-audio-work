"""Common utilities for dsh-audio-work."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class AudioWorkError(Exception):
    """Raised when a step in the audio pipeline fails."""


def log(msg: str, level: str = "info") -> None:
    prefix = {"info": "[dsh-audio]", "warn": "[dsh-audio][!]", "error": "[dsh-audio][X]"}.get(level, "[dsh-audio]")
    print(f"{prefix} {msg}", file=sys.stderr)


def which(binary: str) -> str | None:
    return shutil.which(binary)


def run(cmd: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    log("run: " + " ".join(_quote(c) for c in cmd))
    proc = subprocess.run(
        cmd,
        check=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise AudioWorkError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{detail[-2000:]}")
    return proc


def _quote(s: str) -> str:
    if any(ch.isspace() for ch in s):
        return f'"{s}"'
    return s


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj: Any, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def file_duration(path: str | Path) -> float:
    """Return media duration in seconds via ffprobe."""
    ffprobe = which("ffprobe")
    if not ffprobe:
        raise AudioWorkError("ffprobe not found; please install ffmpeg")
    proc = run([
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    try:
        return float(proc.stdout.strip())
    except ValueError as e:
        raise AudioWorkError(f"cannot read duration of {path}: {e}") from e


def platform_tag() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("win"):
        return "windows"
    return sys.platform
