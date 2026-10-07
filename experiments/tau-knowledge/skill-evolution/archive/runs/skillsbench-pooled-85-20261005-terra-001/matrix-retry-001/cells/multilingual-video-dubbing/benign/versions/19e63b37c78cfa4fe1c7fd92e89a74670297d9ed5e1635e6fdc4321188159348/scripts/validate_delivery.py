#!/usr/bin/env python3
"""Validate dubbing deliverables. JSON stdin -> JSON stdout."""
import json
import re
import subprocess
import sys
from pathlib import Path


def run(args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def probe_audio(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=sample_rate,channels", "-of", "json", str(path)]).stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError("no audio stream in " + str(path))
    return int(streams[0].get("sample_rate", 0)), int(streams[0].get("channels", 0))


def lufs(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af",
                  "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise ValueError("no finite BS.1770 integrated loudness")
    return float(values[-1])


def main(cfg):
    errors = []
    video = Path(cfg["video"])
    report_file = Path(cfg["report"])
    segment_dir = Path(cfg.get("segment_dir", report_file.parent / "tts_segments"))
    if not video.is_file():
        errors.append("missing dubbed video")
    if not report_file.is_file():
        errors.append("missing report")
    if errors:
        return {"ok": False, "errors": errors}
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": ["invalid report JSON: " + str(exc)]}
    global_fields = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                     "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    errors.extend("report missing " + x for x in sorted(global_fields - set(report)))
    try:
        if probe_audio(video) != (48000, 1):
            errors.append("MP4 audio is not 48 kHz mono")
    except Exception as exc:
        errors.append(str(exc))
    required = {"window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec", "source_text",
                "target_text", "window_duration_sec", "tts_duration_sec", "drift_sec", "duration_control"}
    for i, entry in enumerate(report.get("speech_segments", [])):
        if not isinstance(entry, dict):
            errors.append("segment %d is not an object" % i)
            continue
        missing = required - set(entry)
        if missing:
            errors.append("segment %d missing %s" % (i, ", ".join(sorted(missing))))
            continue
        try:
            drift = float(entry["placed_end_sec"]) - float(entry["window_end_sec"])
            if abs(float(entry["placed_start_sec"]) - float(entry["window_start_sec"])) > 0.010:
                errors.append("segment %d start is unanchored" % i)
            if abs(drift - float(entry["drift_sec"])) > 0.005 or abs(drift) > 0.2:
                errors.append("segment %d drift is invalid" % i)
        except (TypeError, ValueError):
            errors.append("segment %d has invalid timing values" % i)
        if entry["duration_control"] not in {"rate_adjust", "pad_silence", "trim"}:
            errors.append("segment %d has invalid duration_control" % i)
        wav = segment_dir / ("seg_%d.wav" % i)
        try:
            if probe_audio(wav) != (48000, 1):
                errors.append("segment %d WAV is not 48 kHz mono" % i)
        except Exception as exc:
            errors.append("segment %d: %s" % (i, exc))
    measured = None
    if not errors:
        try:
            measured = lufs(video)
            if abs(measured + 23.0) > float(cfg.get("lufs_tolerance", 1.0)):
                errors.append("final video loudness is not near -23 LUFS")
            if abs(measured - float(report["measured_lufs"])) > 0.75:
                errors.append("report loudness differs from delivered-file measurement")
        except Exception as exc:
            errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "measured_lufs": measured}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}))
        sys.exit(1)
