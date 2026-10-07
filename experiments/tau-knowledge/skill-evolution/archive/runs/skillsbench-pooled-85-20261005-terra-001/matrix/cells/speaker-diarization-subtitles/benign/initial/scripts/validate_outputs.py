#!/usr/bin/env python3
"""Validate RTTM, ASS, and report artifacts. JSON stdin -> JSON stdout."""
import json, re, sys
from pathlib import Path

RTTM_LABEL = re.compile(r"^spk(\d+)$")
ASS_LABEL = re.compile(r"^SPEAKER_(\d+):")
ASS_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$")

def ass_seconds(value):
    m = ASS_TIME.match(value)
    if not m:
        raise ValueError("not an ASS H:MM:SS.cc timestamp: " + value)
    h, minute, sec, cs = map(int, m.groups())
    if minute >= 60 or sec >= 60:
        raise ValueError("invalid ASS timestamp: " + value)
    return h * 3600 + minute * 60 + sec + cs / 100.0

def validate(rttm_path, subtitles_path, report_path):
    errors, turns, cues = [], [], []
    try:
        for line_no, raw in enumerate(Path(rttm_path).read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            f = raw.split()
            if len(f) != 10 or f[0] != "SPEAKER" or f[5:7] != ["<NA>", "<NA>"] or f[8:] != ["<NA>", "<NA>"]:
                errors.append(f"RTTM line {line_no} is not a 10-field SPEAKER record")
                continue
            try:
                start, duration = float(f[3]), float(f[4])
                if start < 0 or duration <= 0:
                    raise ValueError
                if not RTTM_LABEL.match(f[7]):
                    errors.append(f"RTTM line {line_no} label must be spkNN")
                turns.append((start, start + duration, f[7]))
            except ValueError:
                errors.append(f"RTTM line {line_no} has invalid start or duration")
    except Exception as exc:
        errors.append("cannot read RTTM: " + str(exc))

    try:
        lines = Path(subtitles_path).read_text(encoding="utf-8-sig").splitlines()
        expected = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        if "[Events]" not in lines or expected not in lines:
            errors.append("ASS lacks required [Events] header or declared dialogue format")
        for line_no, raw in enumerate(lines, 1):
            if not raw.startswith("Dialogue: "):
                continue
            f = raw[len("Dialogue: "):].split(",", 9)
            if len(f) != 10:
                errors.append(f"ASS dialogue {line_no} does not have 10 declared fields")
                continue
            try:
                start, end = ass_seconds(f[1]), ass_seconds(f[2])
                if end <= start:
                    errors.append(f"ASS dialogue {line_no} has nonpositive duration")
                label = ASS_LABEL.match(f[9])
                if not label:
                    errors.append(f"ASS dialogue {line_no} lacks SPEAKER_XX: prefix")
                else:
                    cues.append((start, end, "spk" + label.group(1).zfill(2)))
            except ValueError as exc:
                errors.append(f"ASS dialogue {line_no}: {exc}")
    except Exception as exc:
        errors.append("cannot read ASS: " + str(exc))

    report = None
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
        required = {"num_speakers_pred", "total_speech_time_sec", "audio_duration_sec", "steps_completed", "commands_used", "libraries_used", "tools_used", "notes"}
        missing = sorted(required - set(report))
        if missing:
            errors.append("report missing keys: " + ", ".join(missing))
        elif not isinstance(report["steps_completed"], list) or not isinstance(report["tools_used"], dict):
            errors.append("report steps_completed/tools_used have wrong types")
        else:
            labels = {x[2] for x in turns}
            speech = sum(end - start for start, end, _ in turns)
            if report["num_speakers_pred"] != len(labels):
                errors.append("report num_speakers_pred disagrees with RTTM")
            if abs(float(report["total_speech_time_sec"]) - speech) > 0.02:
                errors.append("report total_speech_time_sec disagrees with RTTM")
            if float(report["audio_duration_sec"]) < max((x[1] for x in turns), default=0):
                errors.append("report audio_duration_sec is before final RTTM end")
    except Exception as exc:
        errors.append("cannot validate report: " + str(exc))

    if len(cues) != len(turns):
        errors.append("ASS cue count must equal RTTM turn count")
    else:
        # ASS is centisecond encoded, so allow half a centisecond formatting error.
        for index, (turn, cue) in enumerate(zip(turns, cues), 1):
            if turn[2] != cue[2] or abs(turn[0] - cue[0]) > 0.011 or abs(turn[1] - cue[1]) > 0.011:
                errors.append(f"cue {index} does not correspond to RTTM turn {index}")
    return {"valid": not errors, "errors": errors, "rttm_turns": len(turns), "ass_cues": len(cues)}

def main():
    try:
        obj = json.load(sys.stdin)
        result = validate(obj["rttm_path"], obj["subtitles_path"], obj["report_path"])
    except Exception as exc:
        result = {"valid": False, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
