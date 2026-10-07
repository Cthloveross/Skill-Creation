#!/usr/bin/env python3
"""Validate the three produced artifacts and their cross-consistency.

Stdin : JSON {"rttm":path,"ass":path,"report":path} (defaults to task paths).
Stdout: JSON {"ok":bool,"errors":[...],"warnings":[...],"summary":{...}}

Checks are derived from the public request & RTTM/ASS/report format rules, not
from any hidden grader.
"""
from __future__ import annotations

import json
import re
import sys

ASS_TIME = re.compile(r"^\d:\d{2}:\d{2}\.\d{2}$")


def main():
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""
    cfg = json.loads(raw) if raw.strip() else {}
    rttm = cfg.get("rttm", "/root/diarization.rttm")
    ass = cfg.get("ass", "/root/subtitles.ass")
    report = cfg.get("report", "/root/report.json")

    errors = []
    warnings = []

    # ---- RTTM ----
    rttm_speakers = set()
    rttm_total = 0.0
    rttm_lines = 0
    try:
        with open(rttm, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                parts = ln.split()
                rttm_lines += 1
                if len(parts) != 10:
                    errors.append(f"RTTM line not 10 fields: {ln!r}")
                    continue
                if parts[0] != "SPEAKER":
                    errors.append(f"RTTM type != SPEAKER: {ln!r}")
                try:
                    start = float(parts[3])
                    dur = float(parts[4])
                except ValueError:
                    errors.append(f"RTTM non-numeric start/dur: {ln!r}")
                    continue
                if start < 0:
                    errors.append(f"RTTM negative start: {ln!r}")
                if dur <= 0:
                    errors.append(f"RTTM non-positive duration: {ln!r}")
                rttm_speakers.add(parts[7])
                rttm_total += dur
        if rttm_lines == 0:
            warnings.append("RTTM has no SPEAKER lines (no speech detected?).")
    except FileNotFoundError:
        errors.append(f"RTTM file missing: {rttm}")

    # ---- ASS ----
    ass_dialogues = 0
    try:
        with open(ass, encoding="utf-8") as fh:
            content = fh.read()
        if "[Events]" not in content:
            errors.append("ASS missing [Events] section.")
        if "Format:" not in content:
            errors.append("ASS missing Format line.")
        for ln in content.splitlines():
            if ln.startswith("Dialogue:"):
                ass_dialogues += 1
                fields = ln[len("Dialogue:"):].split(",", 9)
                if len(fields) < 10:
                    errors.append(f"ASS dialogue too few fields: {ln!r}")
                    continue
                start, end = fields[1].strip(), fields[2].strip()
                if not ASS_TIME.match(start) or not ASS_TIME.match(end):
                    errors.append(f"ASS bad centisecond timestamp: {ln!r}")
                text = fields[9]
                if "SPEAKER_" not in text:
                    errors.append(f"ASS cue missing SPEAKER_ label: {ln!r}")
        if ass_dialogues == 0:
            warnings.append("ASS has no Dialogue cues (ASR produced no text?).")
    except FileNotFoundError:
        errors.append(f"ASS file missing: {ass}")

    # ---- report ----
    rep = {}
    try:
        with open(report, encoding="utf-8") as fh:
            rep = json.load(fh)
        required = ["num_speakers_pred", "total_speech_time_sec",
                    "audio_duration_sec", "steps_completed",
                    "commands_used", "libraries_used", "tools_used", "notes"]
        for k in required:
            if k not in rep:
                errors.append(f"report missing key: {k}")
        if not isinstance(rep.get("tools_used", {}), dict):
            errors.append("report tools_used must be an object.")
        # consistency
        if "num_speakers_pred" in rep and rttm_lines > 0:
            if rep["num_speakers_pred"] != len(rttm_speakers):
                errors.append(
                    f"num_speakers_pred ({rep['num_speakers_pred']}) != "
                    f"unique RTTM speakers ({len(rttm_speakers)}).")
        if "total_speech_time_sec" in rep and rttm_lines > 0:
            if abs(rep["total_speech_time_sec"] - rttm_total) > 0.5:
                errors.append(
                    f"total_speech_time_sec ({rep['total_speech_time_sec']}) "
                    f"!= sum of RTTM durations ({round(rttm_total, 3)}).")
        if rep.get("audio_duration_sec", 0) <= 0:
            warnings.append("audio_duration_sec is not positive.")
    except FileNotFoundError:
        errors.append(f"report file missing: {report}")
    except json.JSONDecodeError as exc:
        errors.append(f"report is not valid JSON: {exc}")

    out = {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "rttm_lines": rttm_lines,
            "rttm_speakers": sorted(rttm_speakers),
            "rttm_total_speech": round(rttm_total, 3),
            "ass_dialogues": ass_dialogues,
        },
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
