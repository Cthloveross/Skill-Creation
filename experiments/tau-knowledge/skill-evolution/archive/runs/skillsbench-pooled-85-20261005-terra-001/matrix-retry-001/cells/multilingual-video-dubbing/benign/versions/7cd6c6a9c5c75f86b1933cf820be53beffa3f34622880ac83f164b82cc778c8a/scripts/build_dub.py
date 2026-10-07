#!/usr/bin/env python3
"""Fit, normalize, mux, measure, and report dubbed media. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RANGE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def run(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def seconds(groups):
    hour, minute, second, millis = map(int, groups)
    return hour * 3600 + minute * 60 + second + millis / 1000.0


def parse_srt(path, require_text):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            raise ValueError("SRT cue has no timing range")
        match = RANGE.match(lines[time_index])
        if not match:
            raise ValueError("invalid SRT range: " + lines[time_index])
        start, end = seconds(match.groups()[:4]), seconds(match.groups()[4:])
        text = " ".join(line for line in lines[time_index + 1:] if line).strip()
        if end <= start or (require_text and not text):
            raise ValueError("invalid or empty SRT cue in " + str(path))
        cues.append({"start": start, "end": end, "text": text})
    return cues


def duration(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]).stdout)
    value = float(data["format"]["duration"])
    if value <= 0:
        raise ValueError("invalid media duration: " + str(path))
    return value


def lufs(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise RuntimeError("no finite integrated loudness for " + str(path))
    return float(values[-1])


def tempo_filter(factor):
    if factor <= 0:
        raise ValueError("nonpositive rate-adjust factor")
    filters = []
    while factor > 2.0:
        filters.append("atempo=2")
        factor /= 2.0
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append("atempo=%.9f" % factor)
    return ",".join(filters)


def normalize(source, destination):
    """Two-pass loudnorm where possible, always emitting 48 kHz mono PCM WAV."""
    first = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-af",
                 "loudnorm=I=-23:LRA=7:TP=-2:print_format=json", "-f", "null", "-"])
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", first.stderr, re.S)
    audio_filter = "loudnorm=I=-23:LRA=7:TP=-2"
    if blocks:
        stats = json.loads(blocks[-1])
        try:
            if float(stats["input_i"]) > -99:
                audio_filter = (
                    "loudnorm=I=-23:LRA=7:TP=-2:linear=true:"
                    "measured_I={input_i}:measured_LRA={input_lra}:measured_TP={input_tp}:"
                    "measured_thresh={input_thresh}:offset={target_offset}"
                ).format(**stats)
        except (ValueError, KeyError):
            pass
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", audio_filter,
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(destination)])


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
    raws = [Path(path) for path in config["raw_wavs"]]
    if not (len(windows) == len(sources) == len(targets) == len(raws)):
        raise ValueError("window, source, target, and synthesized cue counts must match")
    if any(not path.is_file() for path in raws):
        raise ValueError("a synthesized raw WAV is missing")
    original_duration = duration(video)
    if any(cue["end"] > original_duration + 0.05 for cue in windows):
        raise ValueError("placement window extends beyond input video")

    output = Path(config["output_dir"])
    segment_dir = output / "tts_segments"
    output.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        delivered, report_segments = [], []
        for index, (window, source, target, raw) in enumerate(zip(windows, sources, targets, raws)):
            window_duration = window["end"] - window["start"]
            tts_duration = duration(raw)
            fitted = temp / ("fitted_%d.wav" % index)
            fitting_filter = tempo_filter(tts_duration / window_duration) + ",aresample=48000,apad,atrim=duration=%.9f" % window_duration
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", fitting_filter,
                 "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(fitted)])
            delivered_wav = segment_dir / ("seg_%d.wav" % index)
            normalize(fitted, delivered_wav)
            delivered.append(delivered_wav)
            report_segments.append({
                "window_start_sec": window["start"], "window_end_sec": window["end"],
                "placed_start_sec": window["start"], "placed_end_sec": window["end"],
                "source_text": source["text"], "target_text": target["text"],
                "window_duration_sec": window_duration, "tts_duration_sec": tts_duration,
                "drift_sec": 0.0, "duration_control": "rate_adjust",
            })

        mix_command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for wav in delivered:
            mix_command.extend(["-i", str(wav)])
        graph, labels = [], []
        for index, window in enumerate(windows):
            label = "cue%d" % index
            labels.append("[%s]" % label)
            delay_ms = round(window["start"] * 1000)
            graph.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" % (index, delay_ms, original_duration, label))
        graph.append("%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f,aresample=48000[mix]" % ("".join(labels), len(labels), original_duration))
        premix, final_mix = temp / "premix.wav", temp / "finalmix.wav"
        mix_command.extend(["-filter_complex", ";".join(graph), "-map", "[mix]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(premix)])
        run(mix_command)
        normalize(premix, final_mix)

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
