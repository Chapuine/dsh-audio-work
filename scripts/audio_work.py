#!/usr/bin/env python3
"""dsh-audio-work: run an audio production plan produced by the DeepSeek model."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import editor
import transcribe as transcribe_mod
import tts_engine
from device_probe import probe
from utils import AudioWorkError, dump_json, ensure_dir, load_json, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", nargs="?", help="path to plan JSON")
    ap.add_argument("--workdir", help="working directory for intermediates")
    ap.add_argument("--probe", action="store_true", help="only print device capability probe and exit")
    ap.add_argument("--dry-run", action="store_true", help="validate plan and print steps, no rendering")
    ap.add_argument("--out-report", help="write a machine-readable run report to this path")
    args = ap.parse_args()

    if args.probe:
        from device_probe import main as probe_main
        probe_main()
        return 0

    if not args.plan:
        ap.print_usage()
        return 2

    plan_path = Path(args.plan).expanduser().resolve()
    if not plan_path.exists():
        log(f"plan not found: {plan_path}", "error")
        return 2

    plan = load_json(plan_path)
    workdir = Path(args.workdir).expanduser().resolve() if args.workdir else Path("/tmp/dsh-audio-work")
    ensure_dir(workdir)
    log(f"project: {plan.get('project_name', plan_path.stem)}")
    log(f"workdir: {workdir}")

    probe_result = probe()
    log(f"tts engine = {probe_result.tts_engine}; encoder = {probe_result.aac_encoder}; "
        f"whisper = {probe_result.whisper_impl}")
    for n in probe_result.notes:
        log(n, "warn")

    report: dict = {"steps": [], "artifacts": {}}

    try:
        if plan.get("transcribe"):
            log("== transcribe ==")
            if args.dry_run:
                log("(dry-run) would transcribe: " + plan["transcribe"].get("input", ""))
            else:
                txt = transcribe_mod.transcribe(plan["transcribe"], workdir, probe_result)
                report["artifacts"]["transcript"] = str(txt)
            report["steps"].append("transcribe")

        tts_segments = plan.get("tts") or []
        if tts_segments:
            log(f"== tts: {len(tts_segments)} segments ==")
            rendered: list[str] = []
            for seg in tts_segments:
                if args.dry_run:
                    log(f"(dry-run) would synth [{seg.get('id')}] len={len(seg.get('text',''))}")
                    rendered.append(seg.get("output") or f"{seg.get('id','seg')}.wav")
                else:
                    p = tts_engine.synthesize(seg, workdir, probe_result)
                    rendered.append(p.name)
            report["artifacts"]["tts_segments"] = rendered
            report["steps"].append("tts")

        tracks = plan.get("tracks") or []
        output = plan.get("output")
        if tracks and output:
            if not any(t.get("type") == "voice" for t in tracks) and tts_segments:
                tracks.insert(0, {
                    "type": "voice",
                    "files": [s.get("output") or f"{s.get('id','seg')}.wav" for s in tts_segments],
                    "crossfade": float(plan.get("voice_crossfade", 0.15)),
                })
            log("== render ==")
            if args.dry_run:
                log(f"(dry-run) would render {len(tracks)} tracks -> {output.get('path')}")
            else:
                out = editor.render(tracks, output, workdir, probe_result)
                report["artifacts"]["final"] = str(out)
            report["steps"].append("render")
        elif output and not tracks:
            log("output requested but no tracks; nothing to render", "warn")

    except AudioWorkError as e:
        log(f"pipeline failed: {e}", "error")
        report["error"] = str(e)
        if args.out_report:
            dump_json(report, args.out_report)
        return 1

    report["ok"] = True
    report["workdir"] = str(workdir)
    if args.out_report:
        dump_json(report, args.out_report)

    log("== done ==")
    for k, v in report["artifacts"].items():
        log(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
