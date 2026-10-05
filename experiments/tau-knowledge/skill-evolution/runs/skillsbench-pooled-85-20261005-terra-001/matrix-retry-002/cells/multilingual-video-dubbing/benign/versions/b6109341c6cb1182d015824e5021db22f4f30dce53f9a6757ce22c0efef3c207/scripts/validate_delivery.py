#!/usr/bin/env python3
"""Lightweight delivery validator. Reads JSON stdin and emits JSON stdout."""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path


class ValidationError(RuntimeError):
    pass


def probe(path):
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
    if proc.returncode:
        raise ValidationError(proc.stderr[-1000:])
    return json.loads(proc.stdout)


def finite(obj, field):
    value = obj.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValidationError("non-finite or absent field: " + field)
    return float(value)


def main(config):
    video = Path(config.get("video", "/outputs/dubbed.mp4"))
    report_path = Path(config.get("report", "/outputs/report.json"))
    wav_path = Path(config.get("segment", "/outputs/tts_segments/seg_0.wav"))
    for path in (video, report_path, wav_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValidationError("missing or empty required output: " + str(path))
    try:
        with wave.open(str(wav_path), "rb") as wav:
            if wav.getframerate() != 48000 or wav.getnchannels() != 1 or wav.getnframes() <= 4800:
                raise ValidationError("segment WAV must be nontrivial 48000 Hz mono")
    except wave.Error as exc:
        raise ValidationError("invalid segment WAV: " + str(exc)) from exc
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError("invalid report JSON: " + str(exc)) from exc
    required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels",
                "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    if not isinstance(report, dict) or not required.issubset(report):
        raise ValidationError("report lacks required global fields")
    if report["source_language"] != "en" or report["audio_sample_rate_hz"] != 48000 or report["audio_channels"] != 1:
        raise ValidationError("invalid report audio or source language declaration")
    finite(report, "original_duration_sec")
    finite(report, "new_duration_sec")
    finite(report, "measured_lufs")
    if not isinstance(report["speech_segments"], list) or not report["speech_segments"]:
        raise ValidationError("report lacks speech segments")
    for index, entry in enumerate(report["speech_segments"]):
        if not isinstance(entry, dict):
            raise ValidationError("non-object speech segment")
        for field in ("window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec",
                      "window_duration_sec", "tts_duration_sec", "drift_sec"):
            finite(entry, field)
        if abs(entry["placed_start_sec"] - entry["window_start_sec"]) > 0.010001:
            raise ValidationError("segment %d start misalignment" % index)
        if abs(entry["drift_sec"] - (entry["placed_end_sec"] - entry["window_end_sec"])) > 0.003:
            raise ValidationError("segment %d drift arithmetic" % index)
        if abs(entry["drift_sec"]) > 0.200001:
            raise ValidationError("segment %d excessive drift" % index)
        if entry.get("duration_control") not in {"rate_adjust", "pad_silence", "trim"}:
            raise ValidationError("invalid duration control")
    info = probe(video)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None or int(audio.get("sample_rate", 0)) != 48000 or int(audio.get("channels", 0)) != 1:
        raise ValidationError("MP4 audio is not 48000 Hz mono")
    return {"ok": True, "segments": len(report["speech_segments"])}


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValidationError("stdin must be a JSON object")
        print(json.dumps(main(incoming)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
