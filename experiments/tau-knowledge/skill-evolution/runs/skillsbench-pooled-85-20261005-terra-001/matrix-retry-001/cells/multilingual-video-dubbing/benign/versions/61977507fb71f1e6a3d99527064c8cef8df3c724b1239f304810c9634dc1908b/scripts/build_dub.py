#!/usr/bin/env python3
"""Create timing-locked, normalized dubbing deliverables from raw neural-TTS WAVs."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TC = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def run(args):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def require_binaries():
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            raise RuntimeError(name + " is not on PATH")


def time_seconds(groups):
    h, m, s, ms = map(int, groups)
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt(path, require_text):
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(path))
    result = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [line.strip() for line in block.splitlines()]
        time_i = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_i is None:
            raise ValueError("SRT cue lacks a time range: " + str(path))
        match = TC.match(lines[time_i])
        if not match:
            raise ValueError("invalid SRT time range: " + lines[time_i])
        start, end = time_seconds(match.groups()[:4]), time_seconds(match.groups()[4:])
        if end <= start:
            raise ValueError("SRT contains a nonpositive window")
        text = " ".join(line for line in lines[time_i + 1:] if line).strip()
        if require_text and not text:
            raise ValueError("dialogue SRT contains an empty cue: " + str(path))
        result.append({"start": start, "end": end, "text": text})
    return result


def probe_duration(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]).stdout)
    value = float(data["format"]["duration"])
    if value <= 0:
        raise ValueError("nonpositive media duration: " + str(path))
    return value


def atempo_chain(speed):
    if speed <= 0:
        raise ValueError("invalid tempo")
    factors = []
    while speed > 2.0:
        factors.append(2.0)
        speed /= 2.0
    while speed < 0.5:
        factors.append(0.5)
        speed /= 0.5
    factors.append(speed)
    return ",".join("atempo=%.12f" % value for value in factors)


def loudnorm_measure(path):
    proc = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                "loudnorm=I=-23:LRA=7:TP=-2:print_format=json", "-f", "null", "-"])
    chunks = re.findall(r"\{\s*\"input_i\".*?\}", proc.stderr, flags=re.S)
    if not chunks:
        raise RuntimeError("could not parse loudnorm measurement for " + str(path))
    measurement = json.loads(chunks[-1])
    for field in ("input_i", "input_lra", "input_tp", "input_thresh", "target_offset"):
        if field not in measurement:
            raise RuntimeError("incomplete loudnorm measurement")
    return measurement


def normalize_lufs(source, destination):
    """Two-pass BS.1770 loudness normalization, retaining 48 kHz mono PCM."""
    measured = loudnorm_measure(source)
    opts = [
        "I=-23", "LRA=7", "TP=-2",
        "measured_I=" + measured["input_i"],
        "measured_LRA=" + measured["input_lra"],
        "measured_TP=" + measured["input_tp"],
        "measured_thresh=" + measured["input_thresh"],
        "offset=" + measured["target_offset"],
        "linear=true", "print_format=summary",
    ]
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af",
         "loudnorm=" + ":".join(opts), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(destination)])


def ebur128(path):
    proc = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af",
                "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d*)?|inf))\s*LUFS", proc.stderr, flags=re.I)
    if not values or values[-1].lower() in ("inf", "-inf"):
        raise RuntimeError("could not measure finite integrated LUFS for " + str(path))
    return float(values[-1])


def find_raws(cfg, count):
    if cfg.get("raw_wavs"):
        paths = [Path(value) for value in cfg["raw_wavs"]]
    else:
        if not cfg.get("raw_wav_dir"):
            raise ValueError("supply raw_wavs or raw_wav_dir")
        root = Path(cfg["raw_wav_dir"])
        paths = [root / ("raw_%d.wav" % i) for i in range(count)]
    if len(paths) != count or any(not path.is_file() for path in paths):
        raise ValueError("raw WAV files must exist and match the dialogue cue count exactly")
    return paths


def main(cfg):
    require_binaries()
    needed = ("video", "segments_srt", "source_srt", "target_srt", "source_language", "target_language", "output_dir")
    for key in needed:
        if not cfg.get(key):
            raise ValueError("missing " + key)

    # Placement cues intentionally permit no dialogue text.
    windows = parse_srt(cfg["segments_srt"], require_text=False)
    source = parse_srt(cfg["source_srt"], require_text=True)
    target = parse_srt(cfg["target_srt"], require_text=True)
    if not (len(windows) == len(source) == len(target)):
        raise ValueError("segments, source, and reference target SRT cue counts must match")
    raws = find_raws(cfg, len(windows))
    video_duration = probe_duration(cfg["video"])

    output = Path(cfg["output_dir"])
    segment_dir = output / "tts_segments"
    output.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dub-build-"))
    try:
        delivered_segments, report_segments = [], []
        for index, (window, src, tgt, raw) in enumerate(zip(windows, source, target, raws)):
            if window["end"] > video_duration + 0.05:
                raise ValueError("placement window exceeds input video duration")
            raw_duration = probe_duration(raw)
            desired = window["end"] - window["start"]
            adjusted = temp / ("adjusted_%d.wav" % index)
            filters = atempo_chain(raw_duration / desired) + ",aresample=48000,apad,atrim=duration=%.9f" % desired
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", filters,
                 "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(adjusted)])

            # Each externally delivered segment has its own BS.1770-compliant loudness.
            segment = segment_dir / ("seg_%d.wav" % index)
            normalize_lufs(adjusted, segment)
            delivered_segments.append(segment)
            report_segments.append({
                "window_start_sec": window["start"], "window_end_sec": window["end"],
                "placed_start_sec": window["start"], "placed_end_sec": window["end"],
                "source_text": src["text"], "target_text": tgt["text"],
                "window_duration_sec": desired, "tts_duration_sec": raw_duration,
                "drift_sec": 0.0, "duration_control": "rate_adjust",
            })

        # Place clips on the original timeline. Millisecond SRT precision makes adelay exact here.
        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for segment in delivered_segments:
            command += ["-i", str(segment)]
        chains, labels = [], []
        for index, window in enumerate(windows):
            label = "seg%d" % index
            labels.append("[%s]" % label)
            delay_ms = int(round(window["start"] * 1000.0))
            chains.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" %
                          (index, delay_ms, video_duration, label))
        chains.append("%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f,aresample=48000[mix]" %
                      ("".join(labels), len(labels), video_duration))
        premix = temp / "premix.wav"
        command += ["-filter_complex", ";".join(chains), "-map", "[mix]", "-ar", "48000", "-ac", "1",
                    "-c:a", "pcm_s24le", str(premix)]
        run(command)

        final_mix = temp / "final_mix.wav"
        normalize_lufs(premix, final_mix)
        dubbed = output / "dubbed.mp4"
        # No duration cap is applied: copying all input video packets preserves every visual frame.
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(cfg["video"]), "-i", str(final_mix),
             "-map", "0:v?", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac",
             "-ar", "48000", "-ac", "1", str(dubbed)])

        final_lufs = ebur128(dubbed)
        report = {
            "source_language": str(cfg["source_language"]).strip(),
            "target_language": str(cfg["target_language"]).strip(),
            "audio_sample_rate_hz": 48000, "audio_channels": 1,
            "original_duration_sec": video_duration, "new_duration_sec": probe_duration(dubbed),
            "measured_lufs": final_lufs, "speech_segments": report_segments,
        }
        report_path = output / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"dubbed": str(dubbed), "report": str(report_path), "segment_dir": str(segment_dir),
                "measured_lufs": final_lufs}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
