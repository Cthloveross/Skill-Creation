#!/usr/bin/env python3
"""Fit, normalize, mux, probe, and report dubbed media. JSON stdin -> JSON stdout."""
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RANGE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def run(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def timestamp(parts):
    h, m, s, ms = map(int, parts)
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt(path, text_required):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if at is None:
            raise ValueError("SRT cue has no time range")
        match = RANGE.match(lines[at])
        if not match:
            raise ValueError("invalid SRT range: " + lines[at])
        start, end = timestamp(match.groups()[:4]), timestamp(match.groups()[4:])
        text = " ".join(line for line in lines[at + 1:] if line).strip()
        if end <= start or (text_required and not text):
            raise ValueError("invalid or empty SRT cue in " + str(path))
        cues.append({"start": start, "end": end, "text": text})
    return cues


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout)


def duration(path):
    value = float(probe(path)["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid media duration: " + str(path))
    return value


def lufs(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    found = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not found or found[-1].lower() in {"inf", "-inf"}:
        raise RuntimeError("no finite integrated loudness for " + str(path))
    return float(found[-1])


def tempo_chain(factor):
    if factor <= 0:
        raise ValueError("nonpositive tempo factor")
    parts = []
    while factor > 2.0:
        parts.append("atempo=2")
        factor /= 2.0
    while factor < .5:
        parts.append("atempo=0.5")
        factor /= .5
    parts.append("atempo=%.9f" % factor)
    return ",".join(parts)


def ffmpeg_audio(source, destination, audio_filter, fixed_duration=None):
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", audio_filter,
               "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le"]
    if fixed_duration is not None:
        command += ["-t", "%.9f" % fixed_duration]
    command.append(str(destination))
    run(command)


def normalize(source, destination, fixed_duration=None):
    """Create a 48 kHz mono PCM file and correct its measured integrated loudness."""
    first = destination.with_name(destination.stem + "_first.wav")
    try:
        base = "loudnorm=I=-23:LRA=7:TP=-2,aresample=48000"
        if fixed_duration is not None:
            base += ",apad,atrim=duration=%.9f" % fixed_duration
        ffmpeg_audio(source, first, base, fixed_duration)
        measured = lufs(first)
        correction = max(-12.0, min(12.0, -23.0 - measured))
        final_filter = "volume=%.5fdB,aresample=48000" % correction
        if fixed_duration is not None:
            final_filter += ",apad,atrim=duration=%.9f" % fixed_duration
        ffmpeg_audio(first, destination, final_filter, fixed_duration)
    finally:
        if first.exists():
            first.unlink()


def main(config):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")
    required = ("video", "segments_srt", "source_srt", "target_srt", "source_language", "target_language", "output_dir", "raw_wavs")
    for field in required:
        if not config.get(field):
            raise ValueError("missing " + field)
    video = Path(config["video"])
    if not video.is_file():
        raise ValueError("missing input video")
    windows = parse_srt(config["segments_srt"], False)
    sources = parse_srt(config["source_srt"], True)
    targets = parse_srt(config["target_srt"], True)
    raws = [Path(item) for item in config["raw_wavs"]]
    if not (len(windows) == len(sources) == len(targets) == len(raws)):
        raise ValueError("window, source, target, and synthesized cue counts must match")
    if any(not item.is_file() for item in raws):
        raise ValueError("a synthesized cue WAV is missing")
    original_duration = duration(video)
    if any(cue["end"] > original_duration + .05 for cue in windows):
        raise ValueError("placement window extends beyond input video")

    output = Path(config["output_dir"])
    segment_dir = output / "tts_segments"
    output.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        wavs, report_segments = [], []
        for i, (window, source, target, raw) in enumerate(zip(windows, sources, targets, raws)):
            target_duration = window["end"] - window["start"]
            raw_duration = duration(raw)
            fitted = temp / ("fitted_%d.wav" % i)
            fit_filter = tempo_chain(raw_duration / target_duration) + ",aresample=48000,apad,atrim=duration=%.9f" % target_duration
            ffmpeg_audio(raw, fitted, fit_filter, target_duration)
            delivered = segment_dir / ("seg_%d.wav" % i)
            normalize(fitted, delivered, target_duration)
            wavs.append(delivered)
            report_segments.append({
                "window_start_sec": window["start"], "window_end_sec": window["end"],
                "placed_start_sec": window["start"], "placed_end_sec": window["end"],
                "source_text": source["text"], "target_text": target["text"],
                "window_duration_sec": target_duration, "tts_duration_sec": raw_duration,
                "drift_sec": 0.0, "duration_control": "rate_adjust",
            })

        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for item in wavs:
            command += ["-i", str(item)]
        filters, labels = [], []
        for i, window in enumerate(windows):
            label = "cue%d" % i
            labels.append("[%s]" % label)
            filters.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" %
                           (i, round(window["start"] * 1000), original_duration, label))
        filters.append("%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f,aresample=48000[mix]" %
                       ("".join(labels), len(labels), original_duration))
        premix, final_mix = temp / "premix.wav", temp / "finalmix.wav"
        command += ["-filter_complex", ";".join(filters), "-map", "[mix]", "-ar", "48000", "-ac", "1",
                    "-c:a", "pcm_s16le", "-t", "%.9f" % original_duration, str(premix)]
        run(command)
        normalize(premix, final_mix, original_duration)

        dubbed = output / "dubbed.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(final_mix),
             "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac",
             "-ar", "48000", "-ac", "1", "-movflags", "+faststart", str(dubbed)])
        measured = lufs(dubbed)
        report = {
            "source_language": str(config["source_language"]).strip(),
            "target_language": str(config["target_language"]).strip(),
            "audio_sample_rate_hz": 48000, "audio_channels": 1,
            "original_duration_sec": original_duration, "new_duration_sec": duration(dubbed),
            "measured_lufs": measured, "speech_segments": report_segments,
        }
        report_path = output / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"dubbed": str(dubbed), "report": str(report_path), "segment_dir": str(segment_dir), "measured_lufs": measured}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
