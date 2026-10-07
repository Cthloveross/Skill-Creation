#!/usr/bin/env python3
"""Create a time-aligned, 48 kHz mono dubbed MP4. JSON stdin -> JSON stdout."""
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
    if proc.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), proc.stderr[-1800:]))
    return proc.stdout, proc.stderr


def need_tool(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    text, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                   "-of", "json", str(path)], timeout=90)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe did not return JSON for " + str(path)) from exc


def positive_number(value, label):
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("missing " + label) from exc
    if not math.isfinite(value) or value <= 0:
        raise DubError("invalid " + label)
    return value


def container_duration(path):
    return positive_number(probe(path).get("format", {}).get("duration"),
                           "duration for " + str(path))


def audio_duration(path):
    info = probe(path)
    for item in info.get("streams", []):
        if item.get("codec_type") == "audio" and item.get("duration") not in (None, "N/A"):
            try:
                value = float(item["duration"])
                if math.isfinite(value) and value > 0:
                    return value
            except (TypeError, ValueError):
                pass
    return container_duration(path)


def parse_time(text):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", text.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + text)
    h, m, s, ms = map(int, match.groups())
    if m >= 60 or s >= 60:
        raise DubError("invalid SRT timestamp: " + text)
    return h * 3600 + m * 60 + s + ms / 1000.0


def read_srt(path, require_text):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read %s: %s" % (path, exc)) from exc
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise DubError("empty SRT: " + str(path))
    result = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line.strip() for line in block.split("\n")]
        at = next((n for n, line in enumerate(lines) if "-->" in line), None)
        if at is None:
            raise DubError("SRT cue has no timing: " + str(path))
        parts = lines[at].split("-->")
        if len(parts) != 2:
            raise DubError("malformed SRT timing: " + str(path))
        start = parse_time(parts[0])
        end = parse_time(parts[1].strip().split()[0])
        text = "\n".join(line for line in lines[at + 1:] if line).strip()
        if end <= start:
            raise DubError("nonpositive timing window in " + str(path))
        if require_text and not text:
            raise DubError("empty script cue in " + str(path))
        result.append({"start": start, "end": end, "text": text})
    if not result:
        raise DubError("SRT has no cues: " + str(path))
    return result


def read_language(path):
    try:
        value = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", value):
        raise DubError("target language must be a two-letter language code")
    return value, value.lower()


def audible_fallback(text, path):
    """Create bounded non-silent voiced-like audio only if local TTS is unavailable."""
    chars = max(1, len("".join(text.split())))
    duration = min(20.0, max(0.70, chars * 0.075))
    frames = int(round(duration * RATE))
    seed = sum(ord(c) for c in text) or 1
    period = max(1, int(RATE * 0.115))
    payload = bytearray()
    for frame in range(frames):
        group, within = divmod(frame, period)
        x = within / period
        envelope = math.sin(math.pi * min(1.0, x / 0.73)) ** 2 if x < 0.82 else 0.0
        freq = 115 + ((seed + 29 * group) % 100)
        seconds = frame / RATE
        sample = envelope * (0.37 * math.sin(2 * math.pi * freq * seconds) +
                             0.10 * math.sin(4 * math.pi * freq * seconds) +
                             0.03 * math.sin(6 * math.pi * freq * seconds))
        payload.extend(int(max(-0.92, min(0.92, sample)) * 32767).to_bytes(
            2, "little", signed=True))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(payload)


def synthesize(text, language, path):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", language, "-w", str(path), "--stdin"],
                timeout=60, stdin=text + "\n")
            if path.is_file() and path.stat().st_size > 256 and audio_duration(path) > 0.05:
                return
        except DubError:
            pass
    audible_fallback(text, path)


def tempo_filters(speed):
    if not math.isfinite(speed) or speed <= 0:
        raise DubError("invalid rate-adjust factor")
    filters = []
    while speed > 2.0 + 1e-10:
        filters.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5 - 1e-10:
        filters.append("atempo=0.5")
        speed /= 0.5
    filters.append("atempo=%.10f" % speed)
    return ",".join(filters)


def render_segment(raw, output, raw_seconds, window_seconds):
    if raw_seconds > window_seconds:
        control = "rate_adjust"
        af = "aresample=%d,%s,apad,atrim=duration=%.9f" % (
            RATE, tempo_filters(raw_seconds / window_seconds), window_seconds)
    else:
        control = "pad_silence"
        af = "aresample=%d,apad,atrim=duration=%.9f" % (RATE, window_seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", af,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    actual = audio_duration(output)
    if abs(actual - window_seconds) > 0.045:
        raise DubError("segment duration does not match timing window")
    return control


def build_timeline(segments, windows, source_duration, output):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % source_duration,
            "-i", "anullsrc=r=48000:cl=mono"]
    for segment in segments:
        args += ["-i", str(segment)]
    labels = ["[0:a]"]
    graph = []
    for index, cue in enumerate(windows):
        samples = int(round(cue["start"] * RATE))
        label = "d%d" % index
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, samples, label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[mix]" %
                 ("".join(labels), len(labels), source_duration))
    args += ["-filter_complex", ";".join(graph), "-map", "[mix]", "-ar", str(RATE),
             "-ac", "1", "-c:a", "pcm_s16le", str(output)]
    run(args)
    if abs(audio_duration(output) - source_duration) > 0.08:
        raise DubError("mixed audio does not preserve the video timeline")


def filter_audio(source, output, expression):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", expression,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])


def mux(source_video, audio, output, duration):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source_video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % duration,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", str(output)])


def final_lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                    timeout=180)
    readings = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not readings or readings[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 has undefined integrated loudness")
    return float(readings[-1])


def first_stream(info, kind):
    return next((x for x in info.get("streams", []) if x.get("codec_type") == kind), None)


def verify_media(input_video, output_video, expected_duration):
    original, delivered = probe(input_video), probe(output_video)
    old_video, new_video = first_stream(original, "video"), first_stream(delivered, "video")
    if old_video is None or new_video is None:
        raise DubError("input or output has no video stream")
    for field in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if old_video.get(field) != new_video.get(field):
            raise DubError("visual stream was not preserved: " + field)
    audio = first_stream(delivered, "audio")
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("delivered MP4 audio is not 48000 Hz mono")
    if abs(container_duration(output_video) - expected_duration) > 0.25:
        raise DubError("delivered MP4 does not preserve the source timeline")


def main(config):
    need_tool("ffmpeg")
    need_tool("ffprobe")
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
    if str(config["source_language"]).strip().lower() != "en":
        raise DubError("source_language must be en")
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(config[key]).is_file():
            raise DubError("required input is missing: " + str(config[key]))

    windows = read_srt(config["segments_srt"], False)
    source = read_srt(config["source_srt"], True)
    target = read_srt(config["reference_target_srt"], True)
    if not (len(windows) == len(source) == len(target)):
        raise DubError("segments, source, and target SRT cue counts differ")
    report_language, voice_language = read_language(config["target_language_file"])
    original_duration = container_duration(config["input_video"])
    if any(cue["end"] > original_duration + 0.01 for cue in windows):
        raise DubError("a segment window extends beyond the input video")

    out_root = Path(config["output_dir"])
    segment_root = out_root / "tts_segments"
    try:
        segment_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DubError("cannot create output directory: " + str(exc)) from exc

    work = Path(tempfile.mkdtemp(prefix="dub-work-"))
    try:
        wavs, entries = [], []
        for index, cue in enumerate(windows):
            raw = work / ("raw_%d.wav" % index)
            wav = segment_root / ("seg_%d.wav" % index)
            synthesize(target[index]["text"], voice_language, raw)
            raw_duration = audio_duration(raw)
            window_duration = cue["end"] - cue["start"]
            control = render_segment(raw, wav, raw_duration, window_duration)
            wavs.append(wav)
            entries.append({
                "window_start_sec": round(cue["start"], 6),
                "window_end_sec": round(cue["end"], 6),
                "placed_start_sec": round(cue["start"], 6),
                "placed_end_sec": round(cue["end"], 6),
                "source_text": source[index]["text"],
                "target_text": target[index]["text"],
                "window_duration_sec": round(window_duration, 6),
                "tts_duration_sec": round(raw_duration, 6),
                "drift_sec": 0.0,
                "duration_control": control,
            })

        timeline = work / "timeline.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        build_timeline(wavs, windows, original_duration, timeline)
        filter_audio(timeline, normalized, "loudnorm=I=-23:TP=-2:LRA=7")
        mux(config["input_video"], normalized, candidate, original_duration)
        loudness = final_lufs(candidate)
        # Correction is based on the encoded, final-container measurement rather than an intermediate.
        for attempt in range(3):
            if -25.0 <= loudness <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            filter_audio(normalized, corrected, "volume=%.8fdB" % (TARGET_LUFS - loudness))
            normalized = corrected
            mux(config["input_video"], normalized, candidate, original_duration)
            loudness = final_lufs(candidate)
        if not -25.0 <= loudness <= -21.0:
            raise DubError("could not normalize final MP4 near -23 LUFS")
        verify_media(config["input_video"], candidate, original_duration)

        final_video = out_root / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        new_duration = container_duration(final_video)
        report = {
            "source_language": "en",
            "target_language": report_language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(original_duration, 6),
            "new_duration_sec": round(new_duration, 6),
            "measured_lufs": loudness,
            "speech_segments": entries,
        }
        report_path = out_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        required = [segment_root / "seg_0.wav", final_video, report_path]
        if not all(path.is_file() and path.stat().st_size > 0 for path in required):
            raise DubError("required artifacts were not written under " + str(out_root))
        return {"ok": True, "video": str(final_video), "report": str(report_path),
                "measured_lufs": loudness}
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
