#!/usr/bin/env python3
"""Validate final diarization turns and write matching RTTM, ASS, and report JSON."""
import json
import math
import os
import re
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

EPSILON = 0.001


def require_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("%s must be a finite number" % field)
    return float(value)


def as_string_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("%s must be a list of nonempty strings" % field)
    # Preserve user order while avoiding redundant provenance entries.
    return list(dict.fromkeys(value))


def ass_time(seconds):
    if seconds < 0:
        raise ValueError("negative ASS timestamp")
    hundredths = int((Decimal(str(seconds)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    hours, remainder = divmod(hundredths, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centis = divmod(remainder, 100)
    return "%d:%02d:%02d.%02d" % (hours, minutes, whole_seconds, centis)


def ass_text(text):
    # Avoid turning recognized literal text into ASS override tags; preserve line breaks as ASS breaks.
    value = str(text).replace("\\", "\\\\")
    value = value.replace("{", "\\{").replace("}", "\\}")
    return re.sub(r"\r?\n", r"\\N", value).strip()


def atomic_write(path, content):
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tmp-", dir=str(parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def normalize_turns(raw_turns, duration):
    if not isinstance(raw_turns, list):
        raise ValueError("turns must be a list")
    turns = []
    for index, raw in enumerate(raw_turns):
        if not isinstance(raw, dict):
            raise ValueError("turn %d must be an object" % index)
        start = require_number(raw.get("start"), "turn[%d].start" % index)
        has_end = "end" in raw
        has_duration = "duration" in raw
        if has_end == has_duration:
            raise ValueError("turn %d must contain exactly one of end or duration" % index)
        end = require_number(raw["end"], "turn[%d].end" % index) if has_end else start + require_number(raw["duration"], "turn[%d].duration" % index)
        speaker = raw.get("speaker")
        if not isinstance(speaker, str) or not speaker.strip():
            raise ValueError("turn %d speaker must be a nonempty string" % index)
        text = raw.get("text")
        if not isinstance(text, str):
            raise ValueError("turn %d text must be a string" % index)
        if start < -EPSILON or end > duration + EPSILON or end <= start:
            raise ValueError("turn %d is outside duration or has nonpositive duration" % index)
        # Correct only negligible decoder/float boundary error; do not silently alter real timing.
        start = max(0.0, start)
        end = min(duration, end)
        if end <= start:
            raise ValueError("turn %d collapses after boundary normalization" % index)
        turns.append({"start": start, "end": end, "speaker": speaker.strip(), "text": text})
    turns.sort(key=lambda t: (t["start"], t["end"], t["speaker"]))
    labels = {}
    for turn in turns:
        if turn["speaker"] not in labels:
            labels[turn["speaker"]] = "SPEAKER_%02d" % len(labels)
        turn["label"] = labels[turn["speaker"]]
    return turns


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        duration = require_number(data.get("audio_duration_sec"), "audio_duration_sec")
        if duration < 0:
            raise ValueError("audio_duration_sec must be nonnegative")
        turns = normalize_turns(data.get("turns"), duration)
        output_dir = data.get("output_dir", "/root")
        file_id = data.get("file_id", "input")
        if not isinstance(output_dir, str) or not output_dir:
            raise ValueError("output_dir must be a nonempty string")
        if not isinstance(file_id, str) or not file_id or any(ch.isspace() for ch in file_id):
            raise ValueError("file_id must be a nonempty whitespace-free string")
        steps = as_string_list(data.get("steps_completed"), "steps_completed")
        commands = as_string_list(data.get("commands_used"), "commands_used")
        libraries = as_string_list(data.get("libraries_used"), "libraries_used")
        tools = data.get("tools_used", {})
        if not isinstance(tools, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in tools.items()):
            raise ValueError("tools_used must be an object with string keys and values")
        notes = data.get("notes", "")
        if not isinstance(notes, str):
            raise ValueError("notes must be a string")

        rttm_lines = []
        cues = []
        for turn in turns:
            start, end = turn["start"], turn["end"]
            rttm_lines.append("SPEAKER %s 1 %.6f %.6f <NA> <NA> %s <NA> <NA>" % (file_id, start, end - start, turn["label"]))
            # ASS centisecond quantization must retain a positive visual cue.
            shown_end = end if ass_time(end) != ass_time(start) else min(duration, start + 0.01)
            if shown_end <= start:
                shown_end = end
            transcript = ass_text(turn["text"]) or "[unintelligible]"
            cues.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s: %s" % (ass_time(start), ass_time(shown_end), turn["label"], transcript))

        ass_header = """[Script Info]\nScriptType: v4.00+\nCollisions: Normal\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,20,20,30,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
        total = sum(t["end"] - t["start"] for t in turns)
        report = {
            "num_speakers_pred": len({t["label"] for t in turns}),
            "total_speech_time_sec": round(total, 6),
            "audio_duration_sec": duration,
            "steps_completed": steps,
            "commands_used": commands,
            "libraries_used": libraries,
            "tools_used": tools,
            "notes": notes,
        }
        base = Path(output_dir)
        paths = {
            "rttm": str(base / "diarization.rttm"),
            "subtitles": str(base / "subtitles.ass"),
            "report": str(base / "report.json"),
        }
        atomic_write(paths["rttm"], "\n".join(rttm_lines) + ("\n" if rttm_lines else ""))
        atomic_write(paths["subtitles"], ass_header + "\n".join(cues) + ("\n" if cues else ""))
        atomic_write(paths["report"], json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"ok": True, "outputs": paths, "num_speakers_pred": report["num_speakers_pred"], "total_speech_time_sec": report["total_speech_time_sec"]}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
