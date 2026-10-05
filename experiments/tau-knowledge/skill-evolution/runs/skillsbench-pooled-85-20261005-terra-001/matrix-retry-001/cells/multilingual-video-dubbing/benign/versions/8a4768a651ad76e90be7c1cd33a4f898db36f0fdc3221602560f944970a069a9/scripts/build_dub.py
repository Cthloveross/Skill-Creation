#!/usr/bin/env python3
"""Fit, normalize, mux, measure, and report dubbing media. JSON stdin -> JSON stdout."""
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


def sec(groups):
    h, m, s, ms = map(int, groups)
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt(path, text_required):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(path))
    result = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if index is None:
            raise ValueError("SRT cue has no timing range")
        match = TIME.match(lines[index])
        if not match:
            raise ValueError("invalid SRT range: " + lines[index])
        start, end = sec(match.groups()[:4]), sec(match.groups()[4:])
        text = " ".join(line for line in lines[index + 1:] if line).strip()
        if end <= start or (text_required and not text):
            raise ValueError("invalid or empty SRT cue in " + str(path))
        result.append({"start": start, "end": end, "text": text})
    return result


def media_duration(path):
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]).stdout)
    value = float(probe["format"]["duration"])
    if value <= 0:
        raise ValueError("invalid duration for " + str(path))
    return value


def measure_lufs(path):
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    readings = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", p.stderr)
    if not readings or readings[-1].lower() in {"inf", "-inf"}:
        raise RuntimeError("no finite BS.1770 integrated loudness from " + str(path))
    return float(readings[-1])


def atempo(factor):
    if factor <= 0:
        raise ValueError("nonpositive tempo")
    parts = []
    while factor > 2.0:
        parts.append("atempo=2")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append("atempo=%.9f" % factor)
    return ",".join(parts)


def normalize(source, destination):
    """Two-pass BS.1770 normalization and explicit professional WAV format."""
    first = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-af",
                 "loudnorm=I=-23:LRA=7:TP=-2:print_format=json", "-f", "null", "-"])
    blocks = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", first.stderr, re.S)
    filt = "loudnorm=I=-23:LRA=7:TP=-2"
    if blocks:
        values = json.loads(blocks[-1])
        try:
            if float(values["input_i"]) > -100:
                filt = "loudnorm=I=-23:LRA=7:TP=-2:linear=true:measured_I=%s:measured_LRA=%s:measured_TP=%s:measured_thresh=%s:offset=%s" % (
                    values["input_i"], values["input_lra"], values["input_tp"], values["input_thresh"], values["target_offset"])
        except (KeyError, ValueError):
            pass
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", filt,
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
    source = parse_srt(config["source_srt"], True)
    target = parse_srt(config["target_srt"], True)
    raws = [Path(p) for p in config["raw_wavs"]]
    if not (len(windows) == len(source) == len(target) == len(raws)):
        raise ValueError("placement, source, target, and raw-audio cue counts must match")
    if any(not p.is_file() for p in raws):
        raise ValueError("a raw WAV is missing")
    original = media_duration(video)
    if any(item["end"] > original + .05 for item in windows):
        raise ValueError("placement window exceeds input video duration")

    out = Path(config["output_dir"])
    seg_dir = out / "tts_segments"
    out.mkdir(parents=True, exist_ok=True)
    seg_dir.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        delivered, entries = [], []
        for i, (window, src, tgt, raw) in enumerate(zip(windows, source, target, raws)):
            length = window["end"] - window["start"]
            raw_length = media_duration(raw)
            fitted = temp / ("fitted_%d.wav" % i)
            filters = atempo(raw_length / length) + ",aresample=48000,apad,atrim=duration=%.9f" % length
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", filters,
                 "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(fitted)])
            wav = seg_dir / ("seg_%d.wav" % i)
            normalize(fitted, wav)
            delivered.append(wav)
            entries.append({"window_start_sec": window["start"], "window_end_sec": window["end"],
                            "placed_start_sec": window["start"], "placed_end_sec": window["end"],
                            "source_text": src["text"], "target_text": tgt["text"],
                            "window_duration_sec": length, "tts_duration_sec": raw_length,
                            "drift_sec": 0.0, "duration_control": "rate_adjust"})

        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for wav in delivered:
            cmd += ["-i", str(wav)]
        graph, labels = [], []
        for i, window in enumerate(windows):
            label = "d%d" % i
            labels.append("[%s]" % label)
            graph.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" % (i, round(window["start"] * 1000), original, label))
        graph.append("%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f,aresample=48000[mix]" % ("".join(labels), len(labels), original))
        premix, finalmix = temp / "premix.wav", temp / "finalmix.wav"
        cmd += ["-filter_complex", ";".join(graph), "-map", "[mix]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(premix)]
        run(cmd)
        normalize(premix, finalmix)

        dubbed = out / "dubbed.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(finalmix),
             "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac",
             "-ar", "48000", "-ac", "1", "-movflags", "+faststart", str(dubbed)])
        measured = measure_lufs(dubbed)
        report = {"source_language": str(config["source_language"]).strip(),
                  "target_language": str(config["target_language"]).strip(),
                  "audio_sample_rate_hz": 48000, "audio_channels": 1,
                  "original_duration_sec": original, "new_duration_sec": media_duration(dubbed),
                  "measured_lufs": measured, "speech_segments": entries}
        report_path = out / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"dubbed": str(dubbed), "report": str(report_path), "segment_dir": str(seg_dir), "measured_lufs": measured}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
