#!/usr/bin/env python3
"""JSON stdin {video, report} -> validation JSON stdout."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path


class ValidationError(ValueError):
    pass


def run(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    if p.returncode:
        raise ValidationError(p.stderr[-1600:])
    return p.stdout, p.stderr


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    return json.loads(out)


def number(obj, key):
    value = obj.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValidationError("invalid numeric field " + key)
    return float(value)


def loudness(video):
    _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video), "-map", "0:a:0",
                  "-af", "ebur128=peak=true", "-f", "null", "-"])
    found = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", err)
    if not found or found[-1].lower() in {"inf", "-inf"}:
        raise ValidationError("no finite integrated loudness")
    return float(found[-1])


def main(cfg):
    video, report_file = Path(cfg["video"]), Path(cfg["report"])
    if not video.is_file() or not report_file.is_file():
        raise ValidationError("video or report is missing")
    data = json.loads(report_file.read_text(encoding="utf-8"))
    required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    if not isinstance(data, dict) or not required.issubset(data):
        raise ValidationError("missing report fields")
    if data["audio_sample_rate_hz"] != 48000 or data["audio_channels"] != 1:
        raise ValidationError("report does not declare 48 kHz mono")
    if not isinstance(data["speech_segments"], list) or not data["speech_segments"]:
        raise ValidationError("report has no speech segments")
    for i, item in enumerate(data["speech_segments"]):
        for key in ("window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec",
                    "window_duration_sec", "tts_duration_sec", "drift_sec"):
            number(item, key)
        if abs(number(item, "placed_start_sec") - number(item, "window_start_sec")) > .010001:
            raise ValidationError("segment %d start is not aligned" % i)
        drift = number(item, "placed_end_sec") - number(item, "window_end_sec")
        if abs(drift - number(item, "drift_sec")) > .003 or abs(drift) > .200001:
            raise ValidationError("segment %d drift is invalid" % i)
        if item.get("duration_control") not in {"rate_adjust", "pad_silence", "trim"}:
            raise ValidationError("segment %d has invalid duration control" % i)
    info = probe(video)
    streams = info.get("streams", [])
    audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
    if audio is None or int(audio.get("sample_rate", 0)) != 48000 or int(audio.get("channels", 0)) != 1:
        raise ValidationError("delivered audio is not 48 kHz mono")
    media_duration = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(media_duration) or media_duration <= 0:
        raise ValidationError("invalid delivered duration")
    if abs(number(data, "new_duration_sec") - media_duration) > .15:
        raise ValidationError("report duration differs from media")
    measured = loudness(video)
    if not -25 <= measured <= -21 or abs(measured - number(data, "measured_lufs")) > 1:
        raise ValidationError("final loudness is inconsistent")
    return {"ok": True, "segments": len(data["speech_segments"]), "measured_lufs": measured}


if __name__ == "__main__":
    try:
        cfg = json.load(sys.stdin)
        if not isinstance(cfg, dict):
            raise ValidationError("stdin must contain a JSON object")
        print(json.dumps(main(cfg)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
