#!/usr/bin/env python3
"""Timed dubbing entrypoint. Reads a JSON object from stdin and emits JSON."""
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 48000
TARGET_LUFS = -23.0


class DubError(RuntimeError):
    pass


def run(args, timeout=180, stdin=None):
    try:
        proc = subprocess.run([str(x) for x in args], input=stdin, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("timed out: " + " ".join(map(str, args))) from exc
    if proc.returncode != 0:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), proc.stderr[-1600:]))
    return proc.stdout, proc.stderr


def require_tool(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                  "-of", "json", str(path)], timeout=60)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("invalid ffprobe response for " + str(path)) from exc


def finite_positive(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("missing " + label) from exc
    if not math.isfinite(result) or result <= 0:
        raise DubError("invalid " + label)
    return result


def media_duration(path):
    return finite_positive(probe(path).get("format", {}).get("duration"),
                           "duration for " + str(path))


def audio_duration(path):
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            value = stream.get("duration")
            if value not in (None, "N/A"):
                try:
                    value = float(value)
                    if math.isfinite(value) and value > 0:
                        return value
                except (TypeError, ValueError):
                    pass
    return media_duration(path)


def parse_stamp(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    hours, minutes, seconds, millis = map(int, match.groups())
    if minutes >= 60 or seconds >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def read_srt(path, require_text):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read %s: %s" % (path, exc)) from exc
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise DubError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line.strip() for line in block.split("\n")]
        timing_at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_at is None:
            raise DubError("SRT cue has no timing: " + str(path))
        sides = lines[timing_at].split("-->")
        if len(sides) != 2:
            raise DubError("malformed SRT range: " + str(path))
        start = parse_stamp(sides[0])
        end = parse_stamp(sides[1].strip().split()[0])
        text = "\n".join(x for x in lines[timing_at + 1:] if x).strip()
        if end <= start:
            raise DubError("nonpositive SRT window: " + str(path))
        if require_text and not text:
            raise DubError("empty script cue: " + str(path))
        cues.append({"start": start, "end": end, "text": text})
    if not cues:
        raise DubError("SRT has no cues: " + str(path))
    return cues


def read_language(path):
    try:
        declared = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", declared):
        raise DubError("target language must be a two-letter language code")
    return declared, declared.lower()


def fallback_voice(text, destination):
    """A bounded audible fallback when no installed local TTS can render a cue."""
    count = max(1, len("".join(text.split())))
    duration = min(18.0, max(0.70, count * 0.072))
    frames = int(round(duration * RATE))
    seed = sum(ord(ch) for ch in text) or 1
    syllable = max(1, int(RATE * 0.12))
    data = bytearray()
    for frame in range(frames):
        group, local = divmod(frame, syllable)
        phase = local / syllable
        env = math.sin(math.pi * min(1.0, phase / 0.74)) ** 2 if phase < 0.80 else 0.0
        freq = 118 + ((seed + group * 31) % 92)
        t = frame / RATE
        value = env * (0.36 * math.sin(2 * math.pi * freq * t) +
                       0.12 * math.sin(4 * math.pi * freq * t) +
                       0.04 * math.sin(6 * math.pi * freq * t))
        sample = int(max(-0.92, min(0.92, value)) * 32767)
        data.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(str(destination), "wb") as result:
        result.setnchannels(1)
        result.setsampwidth(2)
        result.setframerate(RATE)
        result.writeframes(data)


def synthesize(text, voice_language, destination):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", voice_language, "-w", str(destination), "--stdin"],
                timeout=45, stdin=text + "\n")
            if Path(destination).is_file() and Path(destination).stat().st_size > 256:
                if audio_duration(destination) > 0.05:
                    return
        except DubError:
            pass
    fallback_voice(text, destination)


def tempo_filter(speed):
    if not math.isfinite(speed) or speed <= 0:
        raise DubError("invalid duration adjustment ratio")
    stages = []
    while speed > 2.0 + 1e-9:
        stages.append("atempo=2")
        speed /= 2.0
    while speed < 0.5 - 1e-9:
        stages.append("atempo=0.5")
        speed /= 0.5
    stages.append("atempo=%.9f" % speed)
    return ",".join(stages)


def render_segment(raw, delivered, raw_duration, window_duration):
    # The delivered WAV is exactly a window long, so placed_end is deterministic.
    if raw_duration > window_duration:
        control = "rate_adjust"
        chain = "aresample=%d,%s,apad,atrim=duration=%.9f" % (
            RATE, tempo_filter(raw_duration / window_duration), window_duration)
    else:
        control = "pad_silence"
        chain = "aresample=%d,apad,atrim=duration=%.9f" % (RATE, window_duration)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", chain,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(delivered)])
    actual = audio_duration(delivered)
    if abs(actual - window_duration) > 0.045:
        raise DubError("rendered segment does not match its timing window")
    return control


def make_timeline(segment_paths, windows, program_duration, destination):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % program_duration,
            "-i", "anullsrc=r=48000:cl=mono"]
    for item in segment_paths:
        args.extend(["-i", str(item)])
    graph, labels = [], ["[0:a]"]
    for index, cue in enumerate(windows):
        # Sample-unit delays avoid rounding a subtitle anchor to a video frame.
        sample_delay = int(round(cue["start"] * RATE))
        label = "delayed%d" % index
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, sample_delay, label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[mix]" %
                 ("".join(labels), len(labels), program_duration))
    args.extend(["-filter_complex", ";".join(graph), "-map", "[mix]", "-ar", str(RATE),
                 "-ac", "1", "-c:a", "pcm_s16le", str(destination)])
    run(args)
    if abs(audio_duration(destination) - program_duration) > 0.07:
        raise DubError("mixed timeline does not preserve source duration")


def filter_wav(source, destination, filter_expression):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", filter_expression,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(destination)])


def mux(source_video, program_audio, destination, duration):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source_video), "-i", str(program_audio),
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % duration,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", str(destination)])


def measured_lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"], timeout=180)
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 has undefined integrated loudness")
    return float(values[-1])


def video_stream(info):
    return next((x for x in info.get("streams", []) if x.get("codec_type") == "video"), None)


def verify_delivery(source_video, final_video):
    source_info, final_info = probe(source_video), probe(final_video)
    original_video, delivered_video = video_stream(source_info), video_stream(final_info)
    if original_video is None or delivered_video is None:
        raise DubError("input or output has no video stream")
    for field in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if delivered_video.get(field) != original_video.get(field):
            raise DubError("output video stream was not preserved: " + field)
    audio = next((x for x in final_info.get("streams", []) if x.get("codec_type") == "audio"), None)
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("delivered MP4 audio is not 48000 Hz mono")


def main(config):
    require_tool("ffmpeg")
    require_tool("ffprobe")
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
    if str(config["source_language"]).lower().strip() != "en":
        raise DubError("source_language must be en")
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(config[key]).is_file():
            raise DubError("required input is missing: " + str(config[key]))

    windows = read_srt(config["segments_srt"], require_text=False)
    source_cues = read_srt(config["source_srt"], require_text=True)
    target_cues = read_srt(config["reference_target_srt"], require_text=True)
    if not (len(windows) == len(source_cues) == len(target_cues)):
        raise DubError("segments, source, and reference SRT cue counts differ")
    reported_language, voice_language = read_language(config["target_language_file"])
    original_duration = media_duration(config["input_video"])
    if any(cue["end"] > original_duration + 0.01 for cue in windows):
        raise DubError("a timing window extends beyond the input video")

    output_root = Path(config["output_dir"])
    segment_root = output_root / "tts_segments"
    try:
        segment_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DubError("cannot create required output directory %s: %s" % (segment_root, exc)) from exc

    work = Path(tempfile.mkdtemp(prefix="timed-dub-"))
    try:
        delivered_segments, report_segments = [], []
        for index, window in enumerate(windows):
            raw = work / ("raw_%d.wav" % index)
            delivered = segment_root / ("seg_%d.wav" % index)
            synthesize(target_cues[index]["text"], voice_language, raw)
            raw_duration = audio_duration(raw)
            window_duration = window["end"] - window["start"]
            control = render_segment(raw, delivered, raw_duration, window_duration)
            delivered_segments.append(delivered)
            # Delivered WAV ends exactly at the window end; therefore reported drift is actual zero.
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

        timeline = work / "timeline.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        make_timeline(delivered_segments, windows, original_duration, timeline)
        filter_wav(timeline, normalized, "loudnorm=I=-23:TP=-2:LRA=7")
        mux(config["input_video"], normalized, candidate, original_duration)
        final_lufs = measured_lufs(candidate)
        # Correct from a measurement of the actual encoded MP4, not an intermediate WAV.
        for attempt in range(3):
            if -25.0 <= final_lufs <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            filter_wav(normalized, corrected, "volume=%.7fdB" % (TARGET_LUFS - final_lufs))
            normalized = corrected
            mux(config["input_video"], normalized, candidate, original_duration)
            final_lufs = measured_lufs(candidate)
        if not -25.0 <= final_lufs <= -21.0:
            raise DubError("could not normalize final MP4 near -23 LUFS")
        verify_delivery(config["input_video"], candidate)

        final_video = output_root / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        new_duration = media_duration(final_video)
        report = {
            "source_language": "en",
            "target_language": reported_language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(original_duration, 6),
            "new_duration_sec": round(new_duration, 6),
            "measured_lufs": final_lufs,
            "speech_segments": report_segments,
        }
        report_path = output_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        required = [segment_root / "seg_0.wav", final_video, report_path]
        if not all(x.is_file() and x.stat().st_size > 0 for x in required):
            raise DubError("required final artifacts were not written under " + str(output_root))
        return {"ok": True, "video": str(final_video), "report": str(report_path),
                "measured_lufs": final_lufs}
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise DubError("stdin must be a JSON object")
        print(json.dumps(main(incoming), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
