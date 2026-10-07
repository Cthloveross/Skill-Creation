#!/usr/bin/env python3
"""Validate delivered dubbing media and report. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(args):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def integrated_lufs(path):
    proc = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af",
                "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d*)?|inf))\s*LUFS", proc.stderr, re.I)
    if not values or values[-1].lower() in ("inf", "-inf"):
        raise ValueError("no finite integrated loudness")
    return float(values[-1])


def audio_format(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=sample_rate,channels", "-of", "json", str(path)]).stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError("no audio stream")
    return int(streams[0].get("sample_rate", 0)), int(streams[0].get("channels", 0))


def main(cfg):
    errors = []
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            errors.append(binary + " unavailable")
    video = Path(cfg["video"])
    report_path = Path(cfg["report"])
    if not video.is_file():
        errors.append("missing video")
    if not report_path.is_file():
        errors.append("missing report")
    if errors:
        return {"ok": False, "errors": errors}

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": ["invalid report JSON: " + str(exc)]}
    required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    errors.extend("report missing " + field for field in required - set(report))
    try:
        rate, channels = audio_format(video)
        if (rate, channels) != (48000, 1):
            errors.append("dubbed audio is not 48 kHz mono")
    except Exception as exc:
        errors.append(str(exc))

    segment_dir = Path(cfg.get("segment_dir", report_path.parent / "tts_segments"))
    fields = {"window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec", "source_text",
              "target_text", "window_duration_sec", "tts_duration_sec", "drift_sec", "duration_control"}
    for index, segment in enumerate(report.get("speech_segments", [])):
        if not isinstance(segment, dict):
            errors.append("segment %d is not an object" % index)
            continue
        missing = fields - set(segment)
        errors.extend("segment %d missing %s" % (index, item) for item in missing)
        if missing:
            continue
        if abs(float(segment["placed_start_sec"]) - float(segment["window_start_sec"])) > 0.010:
            errors.append("segment %d start is not anchored" % index)
        drift = float(segment["placed_end_sec"]) - float(segment["window_end_sec"])
        if abs(drift - float(segment["drift_sec"])) > 0.005:
            errors.append("segment %d drift is inconsistent" % index)
        if abs(drift) > 0.2:
            errors.append("segment %d drift exceeds limit" % index)
        if segment["duration_control"] not in ("rate_adjust", "pad_silence", "trim"):
            errors.append("segment %d has invalid duration control" % index)
        wav = segment_dir / ("seg_%d.wav" % index)
        if not wav.is_file():
            errors.append("missing " + str(wav))
            continue
        try:
            if audio_format(wav) != (48000, 1):
                errors.append("segment %d is not 48 kHz mono" % index)
        except Exception as exc:
            errors.append("unreadable segment %d: %s" % (index, exc))

    measured = None
    if not errors:
        try:
            measured = integrated_lufs(video)
            if abs(measured - float(report["measured_lufs"])) > 0.75:
                errors.append("report loudness is not the delivered-video measurement")
            if abs(measured + 23.0) > float(cfg.get("lufs_tolerance", 1.0)):
                errors.append("delivered video loudness is outside tolerance")
        except Exception as exc:
            errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "measured_lufs": measured}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}))
        sys.exit(1)
