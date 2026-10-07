#!/usr/bin/env python3
"""Create delivered WAVs, muxed MP4, and report. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def run(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def as_seconds(parts):
    h, m, s, ms = map(int, parts)
    return h * 3600 + m * 60 + s + ms / 1000.0


def srt(path, require_text):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if at is None:
            raise ValueError("SRT cue has no timing range")
        match = TIME.match(lines[at])
        if not match:
            raise ValueError("invalid SRT timing range: " + lines[at])
        start, end = as_seconds(match.groups()[:4]), as_seconds(match.groups()[4:])
        text = " ".join(line for line in lines[at + 1:] if line).strip()
        if end <= start or (require_text and not text):
            raise ValueError("invalid or empty SRT cue in " + str(path))
        cues.append({"start": start, "end": end, "text": text})
    return cues


def duration(path):
    answer = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]).stdout)
    value = float(answer["format"]["duration"])
    if value <= 0:
        raise ValueError("nonpositive media duration: " + str(path))
    return value


def lufs(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise RuntimeError("unable to obtain finite integrated LUFS from " + str(path))
    return float(values[-1])


def tempo(factor):
    if factor <= 0:
        raise ValueError("invalid tempo factor")
    values = []
    while factor > 2:
        values.append(2.0)
        factor /= 2
    while factor < .5:
        values.append(.5)
        factor /= .5
    values.append(factor)
    return ",".join("atempo=%.9f" % value for value in values)


def normalize(source, destination):
    """Two-pass loudnorm where possible, always producing 48 kHz mono PCM."""
    first = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-af", "loudnorm=I=-23:LRA=7:TP=-2:print_format=json", "-f", "null", "-"])
    matches = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", first.stderr, re.S)
    filter_value = "loudnorm=I=-23:LRA=7:TP=-2"
    if matches:
        measured = json.loads(matches[-1])
        try:
            if float(measured["input_i"]) > -100:
                fields = ["I=-23", "LRA=7", "TP=-2", "linear=true", "measured_I=" + measured["input_i"],
                          "measured_LRA=" + measured["input_lra"], "measured_TP=" + measured["input_tp"],
                          "measured_thresh=" + measured["input_thresh"], "offset=" + measured["target_offset"]]
                filter_value = "loudnorm=" + ":".join(fields)
        except (KeyError, ValueError):
            pass
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", filter_value,
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(destination)])


def main(config):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")
    needed = ("video", "segments_srt", "source_srt", "target_srt", "source_language", "target_language", "output_dir", "raw_wavs")
    for name in needed:
        if not config.get(name):
            raise ValueError("missing " + name)
    windows, source, target = srt(config["segments_srt"], False), srt(config["source_srt"], True), srt(config["target_srt"], True)
    if not (len(windows) == len(source) == len(target)):
        raise ValueError("all SRT files must have matching ordered cue counts")
    raws = [Path(item) for item in config["raw_wavs"]]
    if len(raws) != len(windows) or any(not item.is_file() for item in raws):
        raise ValueError("one readable raw WAV is required for every cue")
    original = duration(config["video"])
    if any(cue["end"] > original + .05 for cue in windows):
        raise ValueError("placement window exceeds input video duration")

    output = Path(config["output_dir"])
    segments_dir = output / "tts_segments"
    output.mkdir(parents=True, exist_ok=True)
    segments_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        delivered, entries = [], []
        for index, (window, src, tgt, raw) in enumerate(zip(windows, source, target, raws)):
            window_duration = window["end"] - window["start"]
            raw_duration = duration(raw)
            fitted = temporary / ("fit_%d.wav" % index)
            audio_filter = tempo(raw_duration / window_duration) + ",aresample=48000,apad,atrim=duration=%.9f" % window_duration
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", audio_filter,
                 "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(fitted)])
            segment = segments_dir / ("seg_%d.wav" % index)
            normalize(fitted, segment)
            delivered.append(segment)
            entries.append({"window_start_sec": window["start"], "window_end_sec": window["end"],
                            "placed_start_sec": window["start"], "placed_end_sec": window["end"],
                            "source_text": src["text"], "target_text": tgt["text"],
                            "window_duration_sec": window_duration, "tts_duration_sec": raw_duration,
                            "drift_sec": 0.0, "duration_control": "rate_adjust"})

        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for item in delivered:
            command.extend(["-i", str(item)])
        graph, labels = [], []
        for index, window in enumerate(windows):
            label = "a%d" % index
            labels.append("[" + label + "]")
            graph.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" % (index, round(window["start"] * 1000), original, label))
        graph.append("%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f,aresample=48000[mix]" % ("".join(labels), len(labels), original))
        premix, final_mix = temporary / "premix.wav", temporary / "final_mix.wav"
        command.extend(["-filter_complex", ";".join(graph), "-map", "[mix]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(premix)])
        run(command)
        normalize(premix, final_mix)

        dubbed = output / "dubbed.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(config["video"]), "-i", str(final_mix),
             "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "1", "-movflags", "+faststart", str(dubbed)])
        measured = lufs(dubbed)
        report_path = output / "report.json"
        report_path.write_text(json.dumps({"source_language": str(config["source_language"]).strip(),
            "target_language": str(config["target_language"]).strip(), "audio_sample_rate_hz": 48000, "audio_channels": 1,
            "original_duration_sec": original, "new_duration_sec": duration(dubbed), "measured_lufs": measured,
            "speech_segments": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"dubbed": str(dubbed), "report": str(report_path), "segment_dir": str(segments_dir), "measured_lufs": measured}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
