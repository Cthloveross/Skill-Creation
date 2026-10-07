#!/usr/bin/env python3
"""Validate produced dubbing media. JSON stdin -> JSON stdout."""
import json
import re
import subprocess
import sys
from pathlib import Path


def run(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def probe_audio(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels", "-of", "json", str(path)]).stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError("no audio stream: " + str(path))
    return int(streams[0]["sample_rate"]), int(streams[0]["channels"])


def measure(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise ValueError("no finite integrated loudness")
    return float(values[-1])


def main(config):
    video, report_file = Path(config["video"]), Path(config["report"])
    segment_dir = Path(config.get("segment_dir", report_file.parent / "tts_segments"))
    errors = []
    if not video.is_file(): errors.append("missing dubbed video")
    if not report_file.is_file(): errors.append("missing report")
    if errors: return {"ok": False, "errors": errors}
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
        required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels", "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
        errors.extend("report missing " + field for field in sorted(required - set(report)))
        if probe_audio(video) != (48000, 1): errors.append("MP4 audio is not 48 kHz mono")
        for number, entry in enumerate(report.get("speech_segments", [])):
            if probe_audio(segment_dir / ("seg_%d.wav" % number)) != (48000, 1): errors.append("segment is not 48 kHz mono")
            if abs(float(entry["placed_start_sec"]) - float(entry["window_start_sec"])) > .01: errors.append("unanchored segment")
            if abs(float(entry["drift_sec"]) - (float(entry["placed_end_sec"]) - float(entry["window_end_sec"]))) > .011: errors.append("incorrect drift")
        actual = measure(video)
        if abs(actual + 23) > float(config.get("lufs_tolerance", 2.0)): errors.append("final loudness not near -23 LUFS")
        if abs(actual - float(report["measured_lufs"])) > .75: errors.append("report loudness does not match delivered media")
    except Exception as exc:
        errors.append(str(exc))
        actual = None
    return {"ok": not errors, "errors": errors, "measured_lufs": actual}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}))
        sys.exit(1)
