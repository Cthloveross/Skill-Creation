#!/usr/bin/env python3
"""Validate delivered dubbing media. JSON stdin -> JSON stdout."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

RATE = 48000


class ValidationError(RuntimeError):
    pass


def run(args):
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise ValidationError("inspection timed out") from exc
    if proc.returncode:
        raise ValidationError(proc.stderr[-1600:])
    return proc.stdout, proc.stderr


def probe(path):
    stdout, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    return json.loads(stdout)


def number(mapping, key):
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValidationError("invalid numeric field " + key)
    return float(value)


def loudness(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    found = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not found or found[-1].lower() in {"inf", "-inf"}:
        raise ValidationError("no finite integrated loudness")
    return float(found[-1])


def main(config):
    video = Path(config.get("video", "/outputs/dubbed.mp4"))
    report_file = Path(config.get("report", "/outputs/report.json"))
    wav = Path(config.get("segment", "/outputs/tts_segments/seg_0.wav"))
    if not video.is_file() or not report_file.is_file() or not wav.is_file():
        raise ValidationError("required delivered video, report, or seg_0 WAV is missing")
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError("invalid report JSON: " + str(exc)) from exc
    required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    if not isinstance(report, dict) or not required.issubset(report):
        raise ValidationError("report is missing required global fields")
    if report["source_language"] != "en" or report["audio_sample_rate_hz"] != RATE or report["audio_channels"] != 1:
        raise ValidationError("report language or audio format declarations are invalid")
    segments = report["speech_segments"]
    if not isinstance(segments, list) or not segments:
        raise ValidationError("report has no speech segments")
    for index, entry in enumerate(segments):
        if not isinstance(entry, dict):
            raise ValidationError("segment %d is not an object" % index)
        for field in ("window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec",
                      "window_duration_sec", "tts_duration_sec", "drift_sec"):
            number(entry, field)
        if abs(number(entry, "placed_start_sec") - number(entry, "window_start_sec")) > 0.010001:
            raise ValidationError("segment %d start is not aligned" % index)
        drift = number(entry, "placed_end_sec") - number(entry, "window_end_sec")
        if abs(drift - number(entry, "drift_sec")) > 0.003 or abs(drift) > 0.200001:
            raise ValidationError("segment %d drift is invalid" % index)
        if entry.get("duration_control") not in {"rate_adjust", "pad_silence", "trim"}:
            raise ValidationError("segment %d duration control is invalid" % index)
    info = probe(video)
    streams = info.get("streams", [])
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise ValidationError("final MP4 is not 48 kHz mono")
    duration = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValidationError("final MP4 has invalid duration")
    if abs(number(report, "new_duration_sec") - duration) > 0.15:
        raise ValidationError("report new_duration_sec differs from final MP4")
    measured = loudness(video)
    if not -25 <= measured <= -21:
        raise ValidationError("final MP4 loudness is outside delivery range")
    if abs(measured - number(report, "measured_lufs")) > 1.0:
        raise ValidationError("report loudness does not describe final MP4")
    return {"ok": True, "segments": len(segments), "measured_lufs": measured}


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValidationError("stdin must contain a JSON object")
        print(json.dumps(main(incoming)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
