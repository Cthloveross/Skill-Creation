#!/usr/bin/env python3
"""Validate delivered dubbing artifacts. JSON stdin -> JSON stdout."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path


def run(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout)


def duration(metadata):
    value = float(metadata["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid media duration")
    return value


def audio_format(metadata):
    stream = next((stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "audio"), None)
    if stream is None:
        raise ValueError("no audio stream")
    return int(stream["sample_rate"]), int(stream["channels"])


def loudness(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not values:
        raise ValueError("no integrated loudness reading")
    value = float(values[-1])
    if not math.isfinite(value):
        raise ValueError("non-finite integrated loudness")
    return value


def frame_hashes(path):
    result = run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "framemd5", "-"])
    return [line.split(",")[-1].strip() for line in result.stdout.splitlines() if line and not line.startswith("#")]


def main(config):
    output = Path(config.get("output_dir", "/outputs"))
    source_video = Path(config.get("input_video", "/root/input.mp4"))
    errors, value = [], None
    try:
        report_path = output / "report.json"
        wav_path = output / "tts_segments" / "seg_0.wav"
        video_path = output / "dubbed.mp4"
        for path in (report_path, wav_path, video_path):
            if not path.is_file():
                raise ValueError("missing required output: " + str(path))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if audio_format(probe(wav_path)) != (48000, 1):
            errors.append("segment WAV is not 48 kHz mono")
        video_meta, input_meta = probe(video_path), probe(source_video)
        if audio_format(video_meta) != (48000, 1):
            errors.append("dubbed MP4 is not 48 kHz mono")
        if abs(duration(video_meta) - duration(input_meta)) > 0.2:
            errors.append("dubbed duration differs from source")
        if frame_hashes(video_path) != frame_hashes(source_video):
            errors.append("dubbed video frames differ from source")
        value = loudness(video_path)
        if not -25.0 <= value <= -21.0:
            errors.append("dubbed MP4 is not near -23 LUFS")
        if not -25.0 <= loudness(wav_path) <= -21.0:
            errors.append("segment WAV is not near -23 LUFS")
        if abs(float(report["measured_lufs"]) - value) > 0.75:
            errors.append("report loudness does not match delivered MP4")
        for index, segment in enumerate(report["speech_segments"]):
            placed_start = float(segment["placed_start_sec"])
            placed_end = float(segment["placed_end_sec"])
            window_start = float(segment["window_start_sec"])
            window_end = float(segment["window_end_sec"])
            if abs(placed_start - window_start) > 0.01:
                errors.append("segment %d is not start anchored" % index)
            if abs(float(segment["drift_sec"]) - (placed_end - window_end)) > 0.011 or abs(placed_end - window_end) > 0.2:
                errors.append("segment %d has invalid drift" % index)
    except Exception as exc:
        errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "measured_lufs": value}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        sys.exit(1)
