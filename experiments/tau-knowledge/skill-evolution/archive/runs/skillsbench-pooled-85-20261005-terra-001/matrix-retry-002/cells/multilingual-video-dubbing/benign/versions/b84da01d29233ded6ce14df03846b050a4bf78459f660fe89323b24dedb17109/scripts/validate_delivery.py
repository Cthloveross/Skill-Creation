#!/usr/bin/env python3
"""Delivery validator. Reads a JSON object from stdin and emits JSON."""
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path

RATE = 48000


class ValidationError(RuntimeError):
    pass


def run(args):
    try:
        proc = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise ValidationError("inspection command timed out") from exc
    if proc.returncode:
        raise ValidationError(proc.stderr[-1600:])
    return proc.stdout, proc.stderr


def probe(path):
    output, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
    return json.loads(output)


def number(mapping, field):
    value = mapping.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValidationError("invalid numeric field " + field)
    return float(value)


def lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", video,
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise ValidationError("no finite integrated loudness")
    return float(values[-1])


def video_stream(info):
    return next((x for x in info.get("streams", []) if x.get("codec_type") == "video"), None)


def main(config):
    video = Path(config.get("video", "/outputs/dubbed.mp4"))
    report_path = Path(config.get("report", "/outputs/report.json"))
    segment = Path(config.get("segment", "/outputs/tts_segments/seg_0.wav"))
    input_video = Path(config.get("input_video", "/root/input.mp4"))
    for path in (video, report_path, segment, input_video):
        if not path.is_file():
            raise ValidationError("missing required file: " + str(path))
    try:
        with wave.open(str(segment), "rb") as wav:
            if wav.getframerate() != RATE or wav.getnchannels() != 1 or wav.getnframes() <= 4800:
                raise ValidationError("seg_0 WAV is not nontrivial 48000 Hz mono audio")
    except wave.Error as exc:
        raise ValidationError("seg_0 is not a readable WAV: " + str(exc)) from exc
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError("invalid report JSON: " + str(exc)) from exc
    required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    if not isinstance(report, dict) or not required.issubset(report):
        raise ValidationError("report lacks required global fields")
    if report["source_language"] != "en" or report["audio_sample_rate_hz"] != RATE or report["audio_channels"] != 1:
        raise ValidationError("report global language or audio declarations are invalid")
    entries = report["speech_segments"]
    if not isinstance(entries, list) or not entries:
        raise ValidationError("report has no speech segments")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValidationError("segment %d is not an object" % index)
        for field in ("window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec",
                      "window_duration_sec", "tts_duration_sec", "drift_sec"):
            number(entry, field)
        if abs(number(entry, "placed_start_sec") - number(entry, "window_start_sec")) > 0.010001:
            raise ValidationError("segment %d start is misaligned" % index)
        drift = number(entry, "placed_end_sec") - number(entry, "window_end_sec")
        if abs(drift - number(entry, "drift_sec")) > 0.003 or abs(drift) > 0.200001:
            raise ValidationError("segment %d drift is invalid" % index)
        if entry.get("duration_control") not in {"rate_adjust", "pad_silence", "trim"}:
            raise ValidationError("segment %d has invalid duration control" % index)
    source_info, delivered_info = probe(input_video), probe(video)
    source_duration = float(source_info.get("format", {}).get("duration", 0))
    delivered_duration = float(delivered_info.get("format", {}).get("duration", 0))
    if not all(math.isfinite(x) and x > 0 for x in (source_duration, delivered_duration)):
        raise ValidationError("invalid source or delivered duration")
    if abs(number(report, "original_duration_sec") - source_duration) > 0.15:
        raise ValidationError("report source duration differs from input")
    if abs(number(report, "new_duration_sec") - delivered_duration) > 0.15:
        raise ValidationError("report new duration differs from MP4")
    if abs(delivered_duration - source_duration) > 0.25:
        raise ValidationError("dubbed MP4 does not preserve source timeline")
    audio = next((x for x in delivered_info.get("streams", []) if x.get("codec_type") == "audio"), None)
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise ValidationError("MP4 audio is not 48000 Hz mono")
    inv, outv = video_stream(source_info), video_stream(delivered_info)
    if inv is None or outv is None:
        raise ValidationError("input or delivery has no video stream")
    for field in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if inv.get(field) != outv.get(field):
            raise ValidationError("video stream changed: " + field)
    measured = lufs(video)
    if not -25.0 <= measured <= -21.0:
        raise ValidationError("final loudness is outside the -23 LUFS delivery range")
    if abs(measured - number(report, "measured_lufs")) > 1.0:
        raise ValidationError("report loudness differs from final MP4")
    return {"ok": True, "segments": len(entries), "measured_lufs": measured}


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValidationError("stdin must be a JSON object")
        print(json.dumps(main(incoming)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
