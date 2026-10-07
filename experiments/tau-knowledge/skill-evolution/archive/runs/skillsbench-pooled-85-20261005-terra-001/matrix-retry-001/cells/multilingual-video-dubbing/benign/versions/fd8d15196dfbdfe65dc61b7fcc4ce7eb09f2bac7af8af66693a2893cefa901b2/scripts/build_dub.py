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

RANGE_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*$")


def command(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def seconds(parts):
    hour, minute, second, millisecond = map(int, parts)
    return hour * 3600 + minute * 60 + second + millisecond / 1000.0


def parse_srt(path, require_text):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if index is None:
            raise ValueError("SRT cue has no time range: " + str(path))
        match = RANGE_RE.match(lines[index])
        if not match:
            raise ValueError("invalid SRT range: " + lines[index])
        start = seconds(match.groups()[:4])
        end = seconds(match.groups()[4:])
        text = " ".join(line for line in lines[index + 1:] if line).strip()
        if end <= start or (require_text and not text):
            raise ValueError("invalid or empty SRT cue: " + str(path))
        cues.append({"start": start, "end": end, "text": text})
    return cues


def probe(path):
    return json.loads(command(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]).stdout)


def media_duration(path):
    value = float(probe(path)["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid media duration: " + str(path))
    return value


def measured_lufs(path):
    result = command(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                      "-af", "ebur128=peak=true", "-f", "null", "-"])
    readings = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not readings or readings[-1].lower() in {"inf", "-inf"}:
        raise RuntimeError("could not obtain finite integrated loudness for " + str(path))
    return float(readings[-1])


def atempo(factor):
    if factor <= 0 or not math.isfinite(factor):
        raise ValueError("invalid tempo factor")
    terms = []
    while factor > 2.0:
        terms.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        terms.append("atempo=0.5")
        factor /= 0.5
    terms.append("atempo=%.9f" % factor)
    return ",".join(terms)


def make_wav(source, destination, audio_filter, duration=None):
    args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", audio_filter,
            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le"]
    if duration is not None:
        args.extend(["-t", "%.9f" % duration])
    args.append(str(destination))
    command(args)


def normalize(source, destination, fixed_duration):
    """Make a PCM 48 kHz mono output close to -23 LUFS with an exact duration."""
    first = destination.with_name(destination.stem + ".first.wav")
    try:
        common = "aresample=48000,apad,atrim=duration=%.9f" % fixed_duration
        make_wav(source, first, "loudnorm=I=-23:LRA=7:TP=-2," + common, fixed_duration)
        first_lufs = measured_lufs(first)
        gain = max(-18.0, min(18.0, -23.0 - first_lufs))
        make_wav(first, destination, "volume=%.6fdB,%s" % (gain, common), fixed_duration)
    finally:
        first.unlink(missing_ok=True)


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
    raw_wavs = [Path(value) for value in config["raw_wavs"]]
    if not (len(windows) == len(sources) == len(targets) == len(raw_wavs)):
        raise ValueError("window, source, target, and synthesized cue counts must match")
    if any(not path.is_file() for path in raw_wavs):
        raise ValueError("a synthesized cue WAV is missing")

    original_duration = media_duration(video)
    if any(cue["end"] > original_duration + 0.05 for cue in windows):
        raise ValueError("a placement window extends beyond the input visual timeline")
    output = Path(config["output_dir"])
    segment_dir = output / "tts_segments"
    output.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        delivered_wavs = []
        report_segments = []
        for index, (window, source, target, raw) in enumerate(zip(windows, sources, targets, raw_wavs)):
            window_duration = window["end"] - window["start"]
            raw_duration = media_duration(raw)
            fitted = temporary / ("fitted_%d.wav" % index)
            fit_filter = atempo(raw_duration / window_duration) + ",aresample=48000,apad,atrim=duration=%.9f" % window_duration
            make_wav(raw, fitted, fit_filter, window_duration)
            delivered = segment_dir / ("seg_%d.wav" % index)
            normalize(fitted, delivered, window_duration)
            delivered_wavs.append(delivered)
            report_segments.append({
                "window_start_sec": window["start"],
                "window_end_sec": window["end"],
                "placed_start_sec": window["start"],
                "placed_end_sec": window["end"],
                "source_text": source["text"],
                "target_text": target["text"],
                "window_duration_sec": window_duration,
                "tts_duration_sec": raw_duration,
                "drift_sec": 0.0,
                "duration_control": "rate_adjust",
            })

        mix_command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for wav in delivered_wavs:
            mix_command.extend(["-i", str(wav)])
        filters, labels = [], []
        for index, window in enumerate(windows):
            label = "cue%d" % index
            labels.append("[%s]" % label)
            filters.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" %
                           (index, int(round(window["start"] * 1000)), original_duration, label))
        filters.append("%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f,aresample=48000[mix]" %
                       ("".join(labels), len(labels), original_duration))
        premix = temporary / "premix.wav"
        mix_command.extend(["-filter_complex", ";".join(filters), "-map", "[mix]", "-ar", "48000", "-ac", "1",
                            "-c:a", "pcm_s16le", "-t", "%.9f" % original_duration, str(premix)])
        command(mix_command)
        final_mix = temporary / "finalmix.wav"
        normalize(premix, final_mix, original_duration)

        dubbed = output / "dubbed.mp4"
        command(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(final_mix),
                 "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac",
                 "-ar", "48000", "-ac", "1", "-movflags", "+faststart", str(dubbed)])
        final_lufs = measured_lufs(dubbed)
        report = {
            "source_language": str(config["source_language"]).strip(),
            "target_language": str(config["target_language"]).strip(),
            "audio_sample_rate_hz": 48000,
            "audio_channels": 1,
            "original_duration_sec": original_duration,
            "new_duration_sec": media_duration(dubbed),
            "measured_lufs": final_lufs,
            "speech_segments": report_segments,
        }
        report_path = output / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"dubbed": str(dubbed), "report": str(report_path), "segment_dir": str(segment_dir), "measured_lufs": final_lufs}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
