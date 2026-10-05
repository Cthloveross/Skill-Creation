#!/usr/bin/env python3
"""Create a timed target-language dub. JSON object stdin -> JSON stdout."""
import json
import math
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
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, argv))) from exc
    if result.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, argv)), result.stderr[-1800:]))
    return result.stdout, result.stderr


def require(executable):
    if not shutil.which(executable):
        raise DubError("required executable is unavailable: " + executable)


def probe(path):
    raw, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                  "-of", "json", str(path)])
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def media_duration(path):
    value = probe(path).get("format", {}).get("duration")
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("no readable duration in " + str(path)) from exc
    if not math.isfinite(duration) or duration <= 0:
        raise DubError("nonpositive duration in " + str(path))
    return duration


def audio_duration(path):
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            try:
                duration = float(stream.get("duration"))
            except (TypeError, ValueError):
                continue
            if math.isfinite(duration) and duration > 0:
                return duration
    return media_duration(path)


def parse_time(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    hour, minute, second, millisecond = map(int, match.groups())
    if minute >= 60 or second >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return hour * 3600 + minute * 60 + second + millisecond / 1000.0


def read_srt(path):
    try:
        content = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read %s: %s" % (path, exc)) from exc
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not content:
        raise DubError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip() for line in block.split("\n")]
        timing_at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_at is None:
            raise DubError("SRT cue lacks timing in " + str(path))
        fields = lines[timing_at].split("-->")
        if len(fields) != 2:
            raise DubError("malformed SRT timing in " + str(path))
        start = parse_time(fields[0])
        end = parse_time(fields[1].split()[0])
        text = "\n".join(line for line in lines[timing_at + 1:] if line).strip()
        if end <= start or not text:
            raise DubError("SRT has empty text or nonpositive timing in " + str(path))
        cues.append({"start": start, "end": end, "text": text})
    if not cues:
        raise DubError("no usable SRT cues in " + str(path))
    return cues


def target_language(path):
    try:
        code = Path(path).read_text(encoding="utf-8-sig").strip().lower()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[a-z]{2}", code):
        raise DubError("target_language.txt must contain a two-letter ISO 639-1 code")
    return code


def atempo_chain(factor):
    """Return ffmpeg atempo filters for an arbitrary positive speed factor."""
    filters = []
    while factor > 2.0 + 1e-9:
        filters.append("atempo=2")
        factor /= 2.0
    while factor < 0.5 - 1e-9:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append("atempo=%.9f" % factor)
    return ",".join(filters)


def synthesize_reference(text, language, destination):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if not engine:
        raise DubError("espeak-ng or espeak is required for local target-language TTS")
    # A separate argv element preserves Unicode reference text without shell quoting.
    run([engine, "-v", language, "-w", str(destination), text], timeout=120)
    if not destination.is_file() or destination.stat().st_size < 128:
        raise DubError("TTS did not create a usable waveform for language " + language)
    if audio_duration(destination) <= 0:
        raise DubError("TTS waveform has no positive duration")


def render_window(raw, wav, raw_duration, window_duration):
    if raw_duration > window_duration:
        control = "rate_adjust"
        filters = "aresample=48000," + atempo_chain(raw_duration / window_duration)
        filters += ",apad,atrim=duration=%.9f" % window_duration
    else:
        control = "pad_silence"
        filters = "aresample=48000,apad,atrim=duration=%.9f" % window_duration
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", filters,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
    rendered_duration = audio_duration(wav)
    if abs(rendered_duration - window_duration) > 0.025:
        raise DubError("rendered segment duration does not match its window")
    return control


def assemble_timeline(segment_paths, windows, program_duration, destination):
    # Input zero is finite silence and establishes the source-video-sized timeline.
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % program_duration,
            "-i", "anullsrc=r=48000:cl=mono"]
    for wav in segment_paths:
        args += ["-i", str(wav)]
    labels = ["[0:a]"]
    graph = []
    for index, window in enumerate(windows):
        label = "delay%d" % index
        delay_samples = int(round(window["start"] * RATE))
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, delay_samples, label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[aout]" %
                 ("".join(labels), len(labels), program_duration))
    args += ["-filter_complex", ";".join(graph), "-map", "[aout]", "-ar", str(RATE),
             "-ac", "1", "-c:a", "pcm_s16le", str(destination)]
    run(args)


def normalize_audio(source, destination):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af",
         "loudnorm=I=-23:TP=-2:LRA=7", "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(destination)])


def mux(video, audio, destination):
    # Do not use -shortest: the silent replacement track and copied video retain
    # the original program timeline even when AAC packet durations differ slightly.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-ar", str(RATE), "-ac", "1", "-movflags", "+faststart", str(destination)])


def integrated_lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 audio has no measurable integrated loudness")
    return float(values[-1])


def apply_gain(source, gain_db, destination):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af",
         "volume=%.7fdB" % gain_db, "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(destination)])


def final_audio_stream(video):
    info = probe(video)
    video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if video_stream is None or audio_stream is None:
        raise DubError("final MP4 lacks a required video or audio stream")
    if int(audio_stream.get("sample_rate", 0)) != RATE or int(audio_stream.get("channels", 0)) != 1:
        raise DubError("final MP4 is not 48 kHz mono")


def main(config):
    for tool in ("ffmpeg", "ffprobe"):
        require(tool)
    defaults = {
        "input_video": "/root/input.mp4",
        "segments_srt": "/root/segments.srt",
        "source_srt": "/root/source_text.srt",
        "reference_target_srt": "/root/reference_target_text.srt",
        "target_language_file": "/root/target_language.txt",
        "output_dir": "/outputs",
        "source_language": "en",
    }
    for key, value in defaults.items():
        config.setdefault(key, value)
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(config[key]).is_file():
            raise DubError("required input is not a file: " + str(config[key]))
    if str(config["source_language"]).strip().lower() != "en":
        raise DubError("this task requires source_language en")

    windows = read_srt(config["segments_srt"])
    source_cues = read_srt(config["source_srt"])
    target_cues = read_srt(config["reference_target_srt"])
    if not (len(windows) == len(source_cues) == len(target_cues)):
        raise DubError("segments, source, and reference SRTs must have equal cue counts")
    language = target_language(config["target_language_file"])
    original_duration = media_duration(config["input_video"])
    if any(cue["end"] > original_duration + 0.01 for cue in windows):
        raise DubError("a speech window exceeds the source video duration")

    output_dir = Path(config["output_dir"])
    segment_dir = output_dir / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="dubbing-", dir=str(output_dir)))
    try:
        segment_paths = []
        report_segments = []
        for index, window in enumerate(windows):
            raw_wav = work_dir / ("raw_%d.wav" % index)
            rendered_wav = segment_dir / ("seg_%d.wav" % index)
            synthesize_reference(target_cues[index]["text"], language, raw_wav)
            raw_duration = audio_duration(raw_wav)
            window_duration = window["end"] - window["start"]
            control = render_window(raw_wav, rendered_wav, raw_duration, window_duration)
            segment_paths.append(rendered_wav)
            # PCM frame placement is rounded to samples; report the specified SRT
            # boundaries, which are the intended and rendered placement boundaries.
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
        assemble_timeline(segment_paths, windows, original_duration, timeline)
        normalize_audio(timeline, normalized)
        mux(config["input_video"], normalized, candidate)
        measured = integrated_lufs(candidate)

        # Correct based on the encoded delivery rather than an intermediate WAV.
        # A second iteration handles codec rounding while keeping a bounded runtime.
        for attempt in range(2):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work_dir / ("corrected_%d.wav" % attempt)
            apply_gain(normalized, TARGET_LUFS - measured, corrected)
            normalized = corrected
            mux(config["input_video"], normalized, candidate)
            measured = integrated_lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize final MP4 near -23 LUFS; measured %.2f" % measured)
        final_audio_stream(candidate)

        delivered = output_dir / "dubbed.mp4"
        shutil.copyfile(candidate, delivered)
        report = {
            "source_language": "en",
            "target_language": language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(original_duration, 6),
            "new_duration_sec": round(media_duration(delivered), 6),
            "measured_lufs": measured,
            "speech_segments": report_segments,
        }
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "video": str(delivered), "report": str(report_path),
                "measured_lufs": measured}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        cfg = json.load(sys.stdin)
        if not isinstance(cfg, dict):
            raise DubError("stdin must be a JSON object")
        print(json.dumps(main(cfg), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
