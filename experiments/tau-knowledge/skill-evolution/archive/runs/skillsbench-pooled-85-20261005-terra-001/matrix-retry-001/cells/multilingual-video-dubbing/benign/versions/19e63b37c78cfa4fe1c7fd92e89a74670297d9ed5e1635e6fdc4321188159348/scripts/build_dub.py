#!/usr/bin/env python3
"""Build normalized 48 kHz mono dubbing assets. JSON stdin -> JSON stdout."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIME_RANGE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def command(args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def seconds(parts):
    h, m, s, ms = map(int, parts)
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt(filename, text_required):
    raw = Path(filename).read_text(encoding="utf-8-sig").strip()
    if not raw:
        raise ValueError("empty SRT: " + str(filename))
    entries = []
    for block in re.split(r"\r?\n\s*\r?\n", raw):
        lines = [x.strip() for x in block.splitlines()]
        at = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if at is None:
            raise ValueError("SRT cue has no time range: " + str(filename))
        match = TIME_RANGE.match(lines[at])
        if not match:
            raise ValueError("invalid SRT time range: " + lines[at])
        start, end = seconds(match.groups()[:4]), seconds(match.groups()[4:])
        if end <= start:
            raise ValueError("SRT window is not positive")
        text = " ".join(x for x in lines[at + 1:] if x).strip()
        if text_required and not text:
            raise ValueError("dialogue SRT has an empty cue: " + str(filename))
        entries.append({"start": start, "end": end, "text": text})
    return entries


def duration(filename):
    data = json.loads(command(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(filename)]).stdout)
    value = float(data["format"]["duration"])
    if value <= 0:
        raise ValueError("non-positive media duration: " + str(filename))
    return value


def tempo_filters(factor):
    """atempo supports 0.5..2; compose filters for arbitrary positive factors."""
    if factor <= 0:
        raise ValueError("invalid tempo factor")
    factors = []
    while factor > 2.0:
        factors.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        factors.append(0.5)
        factor /= 0.5
    factors.append(factor)
    return ",".join("atempo=%.10f" % f for f in factors)


def loudnorm_stats(source):
    result = command(["ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-af",
                      "loudnorm=I=-23:LRA=7:TP=-2:print_format=json", "-f", "null", "-"])
    matches = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", result.stderr, flags=re.S)
    if not matches:
        return None
    values = json.loads(matches[-1])
    try:
        if float(values["input_i"]) > -100.0:
            return values
    except (KeyError, ValueError):
        pass
    return None


def normalize(source, destination):
    """Normalize a 48 kHz mono WAV using BS.1770 loudnorm; preserve WAV duration."""
    stats = loudnorm_stats(source)
    if stats:
        opts = ["I=-23", "LRA=7", "TP=-2", "measured_I=" + stats["input_i"],
                "measured_LRA=" + stats["input_lra"], "measured_TP=" + stats["input_tp"],
                "measured_thresh=" + stats["input_thresh"], "offset=" + stats["target_offset"],
                "linear=true", "print_format=summary"]
        audio_filter = "loudnorm=" + ":".join(opts)
    else:
        # This path is only for unusually short programs where a first-pass gated value is absent.
        audio_filter = "loudnorm=I=-23:LRA=7:TP=-2"
    command(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-af", audio_filter,
             "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(destination)])


def integrated_lufs(media):
    result = command(["ffmpeg", "-hide_banner", "-nostats", "-i", str(media), "-map", "0:a:0", "-af",
                      "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"(?m)^\s*I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", result.stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise RuntimeError("could not obtain finite integrated LUFS from " + str(media))
    return float(values[-1])


def raw_paths(cfg, count):
    if cfg.get("raw_wavs") is not None:
        paths = [Path(x) for x in cfg["raw_wavs"]]
    elif cfg.get("raw_wav_dir"):
        paths = [Path(cfg["raw_wav_dir"]) / ("raw_%d.wav" % i) for i in range(count)]
    else:
        raise ValueError("supply raw_wavs or raw_wav_dir")
    if len(paths) != count or any(not x.is_file() for x in paths):
        raise ValueError("raw WAV list must contain one existing file for every cue")
    return paths


def main(cfg):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")
    required = ("video", "segments_srt", "source_srt", "target_srt", "source_language", "target_language", "output_dir")
    for field in required:
        if not cfg.get(field):
            raise ValueError("missing " + field)
    windows = parse_srt(cfg["segments_srt"], False)
    source = parse_srt(cfg["source_srt"], True)
    target = parse_srt(cfg["target_srt"], True)
    if not (len(windows) == len(source) == len(target)):
        raise ValueError("all SRT files must contain matching ordered cue counts")
    raws = raw_paths(cfg, len(windows))
    original_duration = duration(cfg["video"])
    if any(w["end"] > original_duration + 0.05 for w in windows):
        raise ValueError("a placement window exceeds the input video duration")

    output = Path(cfg["output_dir"])
    segment_dir = output / "tts_segments"
    output.mkdir(parents=True, exist_ok=True)
    segment_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        delivered = []
        report_segments = []
        for i, (window, src, tgt, raw) in enumerate(zip(windows, source, target, raws)):
            wanted = window["end"] - window["start"]
            raw_duration = duration(raw)
            fitted = temporary / ("fitted_%d.wav" % i)
            # aresample/downmix is explicit; atrim/apad fixes the precise SRT-window duration.
            fit_filter = tempo_filters(raw_duration / wanted) + ",aresample=48000,apad,atrim=duration=%.9f" % wanted
            command(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", fit_filter,
                     "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(fitted)])
            segment = segment_dir / ("seg_%d.wav" % i)
            normalize(fitted, segment)
            delivered.append(segment)
            report_segments.append({
                "window_start_sec": window["start"], "window_end_sec": window["end"],
                "placed_start_sec": window["start"], "placed_end_sec": window["end"],
                "source_text": src["text"], "target_text": tgt["text"],
                "window_duration_sec": wanted, "tts_duration_sec": raw_duration,
                "drift_sec": 0.0, "duration_control": "rate_adjust",
            })

        # Make an input-duration mono timeline. Delays derive from millisecond SRT positions.
        mix_command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        for segment in delivered:
            mix_command.extend(["-i", str(segment)])
        graph, labels = [], []
        for i, window in enumerate(windows):
            label = "s%d" % i
            labels.append("[%s]" % label)
            delay_ms = int(round(window["start"] * 1000.0))
            graph.append("[%d:a]adelay=%d:all=1,apad,atrim=duration=%.9f[%s]" %
                         (i, delay_ms, original_duration, label))
        graph.append("%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f,aresample=48000[m]" %
                     ("".join(labels), len(labels), original_duration))
        premix = temporary / "premix.wav"
        mix_command.extend(["-filter_complex", ";".join(graph), "-map", "[m]", "-ar", "48000", "-ac", "1",
                            "-c:a", "pcm_s24le", str(premix)])
        command(mix_command)
        final_mix = temporary / "final_mix.wav"
        normalize(premix, final_mix)

        dubbed = output / "dubbed.mp4"
        # Copying the video stream exactly preserves decoded visual frames and the visual timeline.
        command(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(cfg["video"]), "-i", str(final_mix),
                 "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac",
                 "-ar", "48000", "-ac", "1", "-movflags", "+faststart", str(dubbed)])
        measured = integrated_lufs(dubbed)
        report = {
            "source_language": str(cfg["source_language"]).strip(),
            "target_language": str(cfg["target_language"]).strip(),
            "audio_sample_rate_hz": 48000, "audio_channels": 1,
            "original_duration_sec": original_duration, "new_duration_sec": duration(dubbed),
            "measured_lufs": measured, "speech_segments": report_segments,
        }
        report_path = output / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"dubbed": str(dubbed), "report": str(report_path), "segment_dir": str(segment_dir),
                "measured_lufs": measured}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
