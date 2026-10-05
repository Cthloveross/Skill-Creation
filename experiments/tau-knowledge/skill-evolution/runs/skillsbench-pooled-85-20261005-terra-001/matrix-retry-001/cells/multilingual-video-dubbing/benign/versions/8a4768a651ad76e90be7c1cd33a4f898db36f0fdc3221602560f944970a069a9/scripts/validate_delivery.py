#!/usr/bin/env python3
"""Inspect delivered dubbing files. JSON stdin -> JSON stdout."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def duration(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]).stdout)
    return float(data["format"]["duration"])


def audio(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels", "-of", "json", str(path)]).stdout)
    stream = data.get("streams", [None])[0]
    if not stream:
        raise ValueError("no audio stream in " + str(path))
    return int(stream["sample_rate"]), int(stream["channels"])


def lufs(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    found = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not found or found[-1].lower() in {"inf", "-inf"}:
        raise ValueError("no finite loudness measurement")
    return float(found[-1])


def main(config):
    out = Path(config.get("output_dir", "/outputs"))
    report_path = Path(config.get("report", out / "report.json"))
    video = Path(config.get("video", out / "dubbed.mp4"))
    errors = []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels", "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
        if not required <= set(report):
            errors.append("report is missing required fields")
        if audio(video) != (48000, 1):
            errors.append("dubbed MP4 audio is not 48 kHz mono")
        for i, item in enumerate(report.get("speech_segments", [])):
            wav = out / "tts_segments" / ("seg_%d.wav" % i)
            if audio(wav) != (48000, 1):
                errors.append("segment %d is not 48 kHz mono" % i)
            if abs(float(item["placed_start_sec"]) - float(item["window_start_sec"])) > .01:
                errors.append("segment %d is not start anchored" % i)
            if abs(float(item["drift_sec"]) - (float(item["placed_end_sec"]) - float(item["window_end_sec"]))) > .011:
                errors.append("segment %d drift is inconsistent" % i)
        actual = lufs(video)
        if not -25 <= actual <= -21:
            errors.append("final MP4 loudness is outside -23 LUFS tolerance")
        if abs(actual - float(report["measured_lufs"])) > .75:
            errors.append("report loudness differs from final MP4")
        if not math.isfinite(duration(video)):
            errors.append("invalid video duration")
    except Exception as exc:
        actual = None
        errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "measured_lufs": actual}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}))
        sys.exit(1)
