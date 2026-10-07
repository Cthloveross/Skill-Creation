#!/usr/bin/env python3
"""Timed multilingual dubbing entrypoint. JSON object stdin -> JSON stdout."""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RATE = 48000
TARGET_LUFS = -23.0


class DubError(RuntimeError):
    pass


def run(argv, timeout=300):
    try:
        completed = subprocess.run(
            [str(x) for x in argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, argv))) from exc
    if completed.returncode != 0:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, argv)), completed.stderr[-1800:]))
    return completed.stdout, completed.stderr


def require_program(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    stdout, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                     "-of", "json", str(path)])
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def finite_positive(value, description):
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("missing numeric " + description) from exc
    if not math.isfinite(value) or value <= 0:
        raise DubError("invalid " + description)
    return value


def media_duration(path):
    return finite_positive(probe(path).get("format", {}).get("duration"),
                           "media duration for " + str(path))


def audio_duration(path):
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            value = stream.get("duration")
            if value not in (None, "N/A"):
                try:
                    duration = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(duration) and duration > 0:
                    return duration
    return media_duration(path)


def parse_timestamp(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    hour, minute, second, millisecond = map(int, match.groups())
    if minute >= 60 or second >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return hour * 3600 + minute * 60 + second + millisecond / 1000.0


def read_srt(path):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read SRT %s: %s" % (path, exc)) from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise DubError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.split("\n")]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            raise DubError("SRT cue lacks timing in " + str(path))
        parts = lines[timing_index].split("-->")
        if len(parts) != 2:
            raise DubError("malformed SRT timing in " + str(path))
        start = parse_timestamp(parts[0])
        end = parse_timestamp(parts[1].split()[0])
        cue_text = "\n".join(line for line in lines[timing_index + 1:] if line).strip()
        if end <= start or not cue_text:
            raise DubError("SRT has empty text or nonpositive timing in " + str(path))
        cues.append({"start": start, "end": end, "text": cue_text})
    if not cues:
        raise DubError("SRT contains no cues: " + str(path))
    return cues


def read_language(path):
    try:
        code = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", code):
        raise DubError("target_language.txt must contain exactly one ISO 639-1 two-letter code")
    # Preserve the supplied code verbatim in the report while passing a conventional
    # lowercase code to command-line speech engines.
    return code, code.lower()


def atempo_filters(speed):
    """Build valid ffmpeg atempo stages for any finite positive speed ratio."""
    if not math.isfinite(speed) or speed <= 0:
        raise DubError("invalid speech speed")
    filters = []
    while speed > 2.0 + 1e-9:
        filters.append("atempo=2")
        speed /= 2.0
    while speed < 0.5 - 1e-9:
        filters.append("atempo=0.5")
        speed /= 0.5
    filters.append("atempo=%.9f" % speed)
    return ",".join(filters)


def synthesize(text, language, destination):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if not engine:
        raise DubError("no local TTS engine: install espeak-ng or espeak with target voice data")
    # Text remains an independent argv item, retaining Unicode and avoiding shell parsing.
    run([engine, "-v", language, "-w", str(destination), "--", text], timeout=120)
    if not destination.is_file() or destination.stat().st_size < 256:
        raise DubError("TTS did not create a usable waveform for language " + language)
    audio_duration(destination)


def render_segment(raw, destination, raw_duration, window_duration):
    if raw_duration > window_duration:
        control = "rate_adjust"
        audio_filter = "aresample=%d,%s,apad,atrim=duration=%.9f" % (
            RATE, atempo_filters(raw_duration / window_duration), window_duration)
    else:
        control = "pad_silence"
        audio_filter = "aresample=%d,apad,atrim=duration=%.9f" % (RATE, window_duration)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", audio_filter,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(destination)])
    rendered = audio_duration(destination)
    if abs(rendered - window_duration) > 0.025:
        raise DubError("segment duration does not match its SRT window")
    return control


def assemble_timeline(segment_paths, windows, program_duration, destination):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % program_duration,
            "-i", "anullsrc=r=48000:cl=mono"]
    for segment in segment_paths:
        args.extend(["-i", str(segment)])
    labels = ["[0:a]"]
    graph = []
    for index, window in enumerate(windows):
        delayed = "d%d" % index
        delay_samples = int(round(window["start"] * RATE))
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, delay_samples, delayed))
        labels.append("[%s]" % delayed)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[aout]" %
                 ("".join(labels), len(labels), program_duration))
    args.extend(["-filter_complex", ";".join(graph), "-map", "[aout]", "-ar", str(RATE),
                 "-ac", "1", "-c:a", "pcm_s16le", str(destination)])
    run(args)


def normalize_to_target(source, destination):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af",
         "loudnorm=I=-23:TP=-2:LRA=7", "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(destination)])


def gain_adjust(source, gain_db, destination):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af",
         "volume=%.7fdB" % gain_db, "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(destination)])


def mux(video, audio, destination):
    # Video stream copy is required to preserve visual pixels and codec properties.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-ar", str(RATE), "-ac", "1", "-movflags", "+faststart", str(destination)])


def integrated_lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 audio has no finite BS.1770 integrated loudness")
    return float(values[-1])


def ensure_final_streams(video):
    info = probe(video)
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise DubError("final MP4 has no video stream")
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise DubError("final MP4 has no audio stream")
    if int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("final MP4 audio is not 48000 Hz mono")


def main(config):
    for tool in ("ffmpeg", "ffprobe"):
        require_program(tool)
    defaults = {
        "input_video": "/root/input.mp4",
        "segments_srt": "/root/segments.srt",
        "source_srt": "/root/source_text.srt",
        "reference_target_srt": "/root/reference_target_text.srt",
        "target_language_file": "/root/target_language.txt",
        "output_dir": "/outputs",
        "source_language": "en",
    }
    for field, value in defaults.items():
        config.setdefault(field, value)
    if str(config["source_language"]).lower().strip() != "en":
        raise DubError("source_language must be en for this task")
    for field in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(config[field]).is_file():
            raise DubError("required input is not a file: " + str(config[field]))

    windows = read_srt(config["segments_srt"])
    source_cues = read_srt(config["source_srt"])
    target_cues = read_srt(config["reference_target_srt"])
    if not (len(windows) == len(source_cues) == len(target_cues)):
        raise DubError("segments, source, and target SRTs must have equal cue counts")
    report_language, tts_language = read_language(config["target_language_file"])
    original_duration = media_duration(config["input_video"])
    if any(cue["end"] > original_duration + 0.01 for cue in windows):
        raise DubError("a timing window ends beyond input video duration")

    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    segment_dir = output_dir / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="dubbing-", dir=str(output_dir)))
    try:
        segments = []
        report_segments = []
        for index, window in enumerate(windows):
            raw = work_dir / ("raw_%d.wav" % index)
            delivered_segment = segment_dir / ("seg_%d.wav" % index)
            synthesize(target_cues[index]["text"], tts_language, raw)
            raw_duration = audio_duration(raw)
            window_duration = window["end"] - window["start"]
            control = render_segment(raw, delivered_segment, raw_duration, window_duration)
            segments.append(delivered_segment)
            report_segments.append({
                "window_start_sec": round(window["start"], 6),
                "window_end_sec": round(window["end"], 6),
                "placed_start_sec": round(window["start"], 6),
                "placed_end_sec": round(window["end"], 6),
                "source_text": source_cues[index]["text"],
                "target_text": target_cues[index]["text"],
                "window_duration_sec": round(window_duration, 6),
                "tts_duration_sec": round(raw_duration, 6),
                "drift_sec": 0.0,
                "duration_control": control,
            })

        timeline = work_dir / "timeline.wav"
        normalized = work_dir / "normalized.wav"
        candidate = work_dir / "dubbed.mp4"
        assemble_timeline(segments, windows, original_duration, timeline)
        normalize_to_target(timeline, normalized)
        mux(config["input_video"], normalized, candidate)
        measured = integrated_lufs(candidate)

        # Correct from the encoded final delivery, not an intermediate waveform.
        for attempt in range(2):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work_dir / ("corrected_%d.wav" % attempt)
            gain_adjust(normalized, TARGET_LUFS - measured, corrected)
            normalized = corrected
            mux(config["input_video"], normalized, candidate)
            measured = integrated_lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError("final loudness is not near -23 LUFS: %.2f" % measured)
        ensure_final_streams(candidate)

        delivered_video = output_dir / "dubbed.mp4"
        shutil.copyfile(candidate, delivered_video)
        report = {
            "source_language": "en",
            "target_language": report_language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(original_duration, 6),
            "new_duration_sec": round(media_duration(delivered_video), 6),
            "measured_lufs": measured,
            "speech_segments": report_segments,
        }
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not delivered_video.is_file() or not report_path.is_file() or not (segment_dir / "seg_0.wav").is_file():
            raise DubError("required output artifacts were not written under " + str(output_dir))
        return {"ok": True, "video": str(delivered_video), "report": str(report_path),
                "measured_lufs": measured}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        configuration = json.load(sys.stdin)
        if not isinstance(configuration, dict):
            raise DubError("stdin must contain one JSON object")
        print(json.dumps(main(configuration), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
