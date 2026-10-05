#!/usr/bin/env python3
"""Validate a dub delivery. JSON stdin -> JSON stdout."""
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


def duration(meta):
    value = float(meta["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid media duration")
    return value


def audio_format(meta):
    stream = next((x for x in meta.get("streams", []) if x.get("codec_type") == "audio"), None)
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
    errors, measured = [], None
    try:
        report_path = output / "report.json"
        wav = output / "tts_segments" / "seg_0.wav"
        dubbed = output / "dubbed.mp4"
        for item in (report_path, wav, dubbed):
            if not item.is_file():
                raise ValueError("missing required output: " + str(item))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if audio_format(probe(wav)) != (48000, 1):
            errors.append("segment WAV is not 48 kHz mono")
        dub_meta, source_meta = probe(dubbed), probe(input_video)
        if audio_format(dub_meta) != (48000, 1):
            errors.append("dubbed MP4 is not 48 kHz mono")
        if abs(duration(dub_meta) - duration(source_meta)) > .2:
            errors.append("dubbed duration differs from source")
        if frame_hashes(dubbed) != frame_hashes(input_video):
            errors.append("dubbed video frames differ from source")
        measured = loudness(dubbed)
        if not -25 <= measured <= -21:
            errors.append("dubbed MP4 is not near -23 LUFS")
        if not -25 <= loudness(wav) <= -21:
            errors.append("segment WAV is not near -23 LUFS")
        if abs(float(report["measured_lufs"]) - measured) > .75:
            errors.append("report loudness does not match delivered MP4")
        for i, segment in enumerate(report["speech_segments"]):
            start = float(segment["placed_start_sec"])
            end = float(segment["placed_end_sec"])
            window_start = float(segment["window_start_sec"])
            window_end = float(segment["window_end_sec"])
            if abs(start - window_start) > .01:
                errors.append("segment %d is not start anchored" % i)
            if abs(float(segment["drift_sec"]) - (end - window_end)) > .011 or abs(end - window_end) > .2:
                errors.append("segment %d has invalid drift" % i)
    except Exception as exc:
        errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "measured_lufs": measured}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        sys.exit(1)
