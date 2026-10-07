#!/usr/bin/env python3
"""Validate a completed dub delivery. Reads JSON stdin and writes JSON stdout."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path


def run(command):
    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout)


def media_duration(metadata):
    value = float(metadata["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid media duration")
    return value


def audio_format(metadata):
    stream = next((item for item in metadata.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not stream:
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
    input_video = Path(config.get("input_video", "/root/input.mp4"))
    report_path = output / "report.json"
    dubbed = output / "dubbed.mp4"
    errors = []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        wavs = sorted((output / "tts_segments").glob("seg_*.wav"))
        if not wavs:
            errors.append("no delivered segment WAVs")
        for wav in wavs:
            if audio_format(probe(wav)) != (48000, 1):
                errors.append(str(wav) + " is not 48 kHz mono")
            if not -25 <= loudness(wav) <= -21:
                errors.append(str(wav) + " is not near -23 LUFS")
        dub_meta, source_meta = probe(dubbed), probe(input_video)
        if audio_format(dub_meta) != (48000, 1):
            errors.append("dubbed MP4 is not 48 kHz mono")
        if abs(media_duration(dub_meta) - media_duration(source_meta)) > .2:
            errors.append("dubbed video duration differs from source")
        if frame_hashes(dubbed) != frame_hashes(input_video):
            errors.append("dubbed video frames differ from source")
        measured = loudness(dubbed)
        if not -25 <= measured <= -21:
            errors.append("dubbed MP4 is not near -23 LUFS")
        if abs(float(report["measured_lufs"]) - measured) > .75:
            errors.append("report loudness does not match delivered MP4")
        for index, segment in enumerate(report["speech_segments"]):
            if abs(float(segment["placed_start_sec"]) - float(segment["window_start_sec"])) > .01:
                errors.append("segment %d is not start anchored" % index)
            drift = float(segment["placed_end_sec"]) - float(segment["window_end_sec"])
            if abs(float(segment["drift_sec"]) - drift) > .011 or abs(drift) > .2:
                errors.append("segment %d has invalid drift" % index)
    except Exception as exc:
        measured = None
        errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "measured_lufs": measured}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        sys.exit(1)
