#!/usr/bin/env python3
"""Validate final dubbing artifacts. JSON stdin {video, report} -> JSON stdout."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path


class ValidationError(ValueError):
    pass


def run(argv):
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise ValidationError("validation command timed out") from exc
    if result.returncode:
        raise ValidationError(result.stderr[-1600:])
    return result.stdout, result.stderr


def probe(path):
    stdout, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                     "-of", "json", str(path)])
    return json.loads(stdout)


def number(data, field):
    value = data.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValidationError("invalid finite numeric field " + field)
    return float(value)


def lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise ValidationError("final audio has no finite integrated loudness")
    return float(values[-1])


def main(config):
    video = Path(config["video"])
    report_file = Path(config["report"])
    if not video.is_file() or not report_file.is_file():
        raise ValidationError("video or report is missing")
    report = json.loads(report_file.read_text(encoding="utf-8"))
    required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    if not isinstance(report, dict) or not required.issubset(report):
        raise ValidationError("report is missing required global fields")
    if report["audio_sample_rate_hz"] != 48000 or report["audio_channels"] != 1:
        raise ValidationError("report does not declare 48 kHz mono")
    if not isinstance(report["speech_segments"], list) or not report["speech_segments"]:
        raise ValidationError("report has no speech segments")
    for index, segment in enumerate(report["speech_segments"]):
        if not isinstance(segment, dict):
            raise ValidationError("segment %d is not an object" % index)
        for field in ("window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec",
                      "window_duration_sec", "tts_duration_sec", "drift_sec"):
            number(segment, field)
        if abs(number(segment, "placed_start_sec") - number(segment, "window_start_sec")) > 0.010001:
            raise ValidationError("segment %d start alignment failed" % index)
        if abs(number(segment, "window_duration_sec") -
               (number(segment, "window_end_sec") - number(segment, "window_start_sec"))) > 0.003:
            raise ValidationError("segment %d window arithmetic failed" % index)
        expected_drift = number(segment, "placed_end_sec") - number(segment, "window_end_sec")
        if abs(number(segment, "drift_sec") - expected_drift) > 0.003 or abs(expected_drift) > 0.200001:
            raise ValidationError("segment %d end drift failed" % index)
        if segment.get("duration_control") not in {"rate_adjust", "pad_silence", "trim"}:
            raise ValidationError("segment %d duration control is invalid" % index)

    info = probe(video)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    visual = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if audio is None or visual is None:
        raise ValidationError("delivered MP4 lacks audio or video")
    if int(audio.get("sample_rate", 0)) != 48000 or int(audio.get("channels", 0)) != 1:
        raise ValidationError("delivered media is not 48 kHz mono")
    duration = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValidationError("delivered media has invalid duration")
    if abs(number(report, "new_duration_sec") - duration) > 0.15:
        raise ValidationError("report duration disagrees with delivered MP4")
    measured = lufs(video)
    if not -25.0 <= measured <= -21.0:
        raise ValidationError("delivered loudness is outside -23 LUFS tolerance")
    if abs(number(report, "measured_lufs") - measured) > 1.0:
        raise ValidationError("report loudness disagrees with final MP4")
    return {"ok": True, "segments": len(report["speech_segments"]), "measured_lufs": measured}


if __name__ == "__main__":
    try:
        configuration = json.load(sys.stdin)
        if not isinstance(configuration, dict):
            raise ValidationError("stdin must contain a JSON object")
        print(json.dumps(main(configuration)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
