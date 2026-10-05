#!/usr/bin/env python3
"""Validate delivered dubbed media. JSON stdin {video, report} -> JSON stdout."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_GLOBAL = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                   "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
REQUIRED_SEGMENT = {"window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec",
                    "source_text", "target_text", "window_duration_sec", "tts_duration_sec",
                    "drift_sec", "duration_control"}

def run(args):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode:
        raise ValueError(proc.stderr[-1200:])
    return proc.stdout, proc.stderr

def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    return json.loads(out)

def final_lufs(path):
    _, err = run(["ffmpeg", "-hide_banner", "-v", "info", "-i", str(path), "-map", "0:a:0",
                  "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", err)
    if not values:
        raise ValueError("ebur128 returned no integrated loudness")
    return float(values[-1])

def number(obj, field):
    value = obj.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("non-finite numeric field: " + field)
    return float(value)

def main(config):
    video = Path(config["video"])
    report_path = Path(config["report"])
    if not video.is_file() or video.stat().st_size == 0:
        raise ValueError("missing or empty video")
    if not report_path.is_file():
        raise ValueError("missing report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    missing = REQUIRED_GLOBAL - set(report)
    if missing:
        raise ValueError("missing report fields: " + ", ".join(sorted(missing)))
    if report["audio_sample_rate_hz"] != 48000 or report["audio_channels"] != 1:
        raise ValueError("report does not declare 48 kHz mono")
    if not isinstance(report["speech_segments"], list) or not report["speech_segments"]:
        raise ValueError("speech_segments must be nonempty")
    for index, segment in enumerate(report["speech_segments"]):
        missing = REQUIRED_SEGMENT - set(segment)
        if missing:
            raise ValueError("segment %d missing fields" % index)
        start, window_start = number(segment, "placed_start_sec"), number(segment, "window_start_sec")
        end, window_end = number(segment, "placed_end_sec"), number(segment, "window_end_sec")
        drift = number(segment, "drift_sec")
        if abs(start - window_start) > 0.010001:
            raise ValueError("segment %d start misaligned" % index)
        if abs(drift - (end - window_end)) > 0.003:
            raise ValueError("segment %d has inconsistent drift" % index)
        if abs(drift) > 0.200001:
            raise ValueError("segment %d exceeds drift limit" % index)
        if segment["duration_control"] not in ("rate_adjust", "pad_silence", "trim"):
            raise ValueError("invalid duration control")
    info = probe(video)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not audio or not video_stream:
        raise ValueError("delivered MP4 needs audio and video")
    if int(audio.get("sample_rate", 0)) != 48000 or int(audio.get("channels", 0)) != 1:
        raise ValueError("delivered audio is not 48 kHz mono")
    measured = final_lufs(video)
    if not math.isfinite(measured) or not -25.0 <= measured <= -21.0:
        raise ValueError("final integrated loudness is outside -23 +/- 2 LU")
    if abs(measured - number(report, "measured_lufs")) > 1.0:
        raise ValueError("report loudness does not match final MP4")
    return {"ok": True, "measured_lufs": measured, "segments": len(report["speech_segments"])}

if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
