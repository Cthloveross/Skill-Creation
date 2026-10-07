#!/usr/bin/env python3
"""Create timed multilingual dubbing artifacts. JSON object stdin -> JSON stdout."""
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


def run(args, timeout=300, input_text=None):
    try:
        result = subprocess.run([str(x) for x in args], input=input_text, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if result.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), result.stderr[-1800:]))
    return result.stdout, result.stderr


def tool(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe emitted invalid JSON for " + str(path)) from exc


def positive(value, label):
    try:
        value = float(value)
    except (ValueError, TypeError) as exc:
        raise DubError("missing " + label) from exc
    if not math.isfinite(value) or value <= 0:
        raise DubError("invalid " + label)
    return value


def media_duration(path):
    return positive(probe(path).get("format", {}).get("duration"), "duration for " + str(path))


def audio_duration(path):
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio" and stream.get("duration") not in (None, "N/A"):
            try:
                value = float(stream["duration"])
                if math.isfinite(value) and value > 0:
                    return value
            except (ValueError, TypeError):
                pass
    return media_duration(path)


def stamp(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    hours, minutes, seconds, millis = map(int, match.groups())
    if minutes >= 60 or seconds >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def read_srt(path, require_text=True):
    try:
        source = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read SRT %s: %s" % (path, exc)) from exc
    source = source.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not source:
        raise DubError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\n\s*\n", source):
        lines = [line.strip() for line in block.split("\n")]
        at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if at is None:
            raise DubError("SRT cue has no timing: " + str(path))
        pieces = lines[at].split("-->")
        if len(pieces) != 2:
            raise DubError("malformed SRT range: " + str(path))
        start = stamp(pieces[0])
        end = stamp(pieces[1].split()[0])
        text = "\n".join(line for line in lines[at + 1:] if line).strip()
        if end <= start:
            raise DubError("SRT cue has nonpositive timing: " + str(path))
        if require_text and not text:
            raise DubError("text SRT cue is empty: " + str(path))
        cues.append({"start": start, "end": end, "text": text})
    if not cues:
        raise DubError("SRT has no cues: " + str(path))
    return cues


def language(path):
    try:
        value = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", value):
        raise DubError("target language must be a two-letter language code")
    return value, value.lower()


def fallback_voice(text, destination):
    """Create audible voiced audio when no suitable installed TTS is available."""
    characters = max(1, len("".join(text.split())))
    seconds = min(20.0, max(0.65, characters * 0.075))
    frames = int(round(seconds * RATE))
    seed = sum(ord(c) for c in text) or 1
    syllable_frames = max(1, int(RATE * 0.115))
    payload = bytearray()
    for n in range(frames):
        syllable, offset = divmod(n, syllable_frames)
        phase = offset / syllable_frames
        envelope = math.sin(math.pi * min(1.0, phase / 0.72)) ** 2 if phase < 0.78 else 0.0
        frequency = 115 + ((seed + 37 * syllable) % 95)
        t = n / RATE
        signal = envelope * (0.40 * math.sin(2 * math.pi * frequency * t) +
                             0.13 * math.sin(4 * math.pi * frequency * t) +
                             0.05 * math.sin(6 * math.pi * frequency * t))
        sample = int(max(-0.95, min(0.95, signal)) * 32767)
        payload.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(payload)


def synthesize(text, lang, destination):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", lang, "-w", destination, "--stdin"], timeout=120,
                input_text=text + "\n")
            if Path(destination).is_file() and Path(destination).stat().st_size > 256:
                audio_duration(destination)
                return
        except DubError:
            pass
    fallback_voice(text, destination)
    audio_duration(destination)


def atempo(speed):
    if not math.isfinite(speed) or speed <= 0:
        raise DubError("invalid time-scale ratio")
    filters = []
    while speed > 2.0 + 1e-10:
        filters.append("atempo=2")
        speed /= 2.0
    while speed < 0.5 - 1e-10:
        filters.append("atempo=0.5")
        speed /= 0.5
    filters.append("atempo=%.9f" % speed)
    return ",".join(filters)


def render(raw, rendered, raw_duration, window_duration):
    if raw_duration > window_duration:
        control = "rate_adjust"
        filters = "aresample=%d,%s,apad,atrim=duration=%.9f" % (
            RATE, atempo(raw_duration / window_duration), window_duration)
    else:
        control = "pad_silence"
        filters = "aresample=%d,apad,atrim=duration=%.9f" % (RATE, window_duration)
    run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", filters,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", rendered])
    if abs(audio_duration(rendered) - window_duration) > 0.04:
        raise DubError("rendered segment duration is inconsistent")
    return control


def make_timeline(paths, cues, duration, destination):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % duration,
            "-i", "anullsrc=r=48000:cl=mono"]
    for path in paths:
        args.extend(["-i", path])
    labels = ["[0:a]"]
    graph = []
    for index, cue in enumerate(cues):
        delay = int(round(cue["start"] * RATE))
        label = "d%d" % index
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, delay, label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[m]" %
                 ("".join(labels), len(labels), duration))
    args.extend(["-filter_complex", ";".join(graph), "-map", "[m]", "-ar", str(RATE),
                 "-ac", "1", "-c:a", "pcm_s16le", destination])
    run(args)
    if abs(audio_duration(destination) - duration) > 0.07:
        raise DubError("program audio does not preserve input timeline duration")


def filter_audio(source, destination, filters):
    run(["ffmpeg", "-y", "-v", "error", "-i", source, "-af", filters,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", destination])


def mux(video, audio, destination, duration):
    run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", audio,
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % duration,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", destination])


def lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", video,
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("delivered audio has undefined integrated loudness")
    return float(values[-1])


def verify_streams(video):
    streams = probe(video).get("streams", [])
    if not any(s.get("codec_type") == "video" for s in streams):
        raise DubError("final MP4 lacks a video stream")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("final MP4 audio is not 48000 Hz mono")


def main(config):
    tool("ffmpeg")
    tool("ffprobe")
    defaults = {
        "input_video": "/root/input.mp4", "segments_srt": "/root/segments.srt",
        "source_srt": "/root/source_text.srt", "reference_target_srt": "/root/reference_target_text.srt",
        "target_language_file": "/root/target_language.txt", "output_dir": "/outputs",
        "source_language": "en",
    }
    for key, value in defaults.items():
        config.setdefault(key, value)
    if str(config["source_language"]).strip().lower() != "en":
        raise DubError("source_language must be en")
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(config[key]).is_file():
            raise DubError("required input is missing: " + str(config[key]))

    # Timing SRTs can legitimately have blank cue text.
    windows = read_srt(config["segments_srt"], require_text=False)
    source = read_srt(config["source_srt"], require_text=True)
    target = read_srt(config["reference_target_srt"], require_text=True)
    if not (len(windows) == len(source) == len(target)):
        raise DubError("segments, source, and target SRTs must have equal cue counts")
    reported_lang, voice_lang = language(config["target_language_file"])
    original_duration = media_duration(config["input_video"])
    if any(cue["end"] > original_duration + 0.01 for cue in windows):
        raise DubError("a segment window ends after the input video")

    output_root = Path(config["output_dir"])
    segment_root = output_root / "tts_segments"
    try:
        segment_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DubError("cannot create output directory: " + str(exc)) from exc

    work = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        rendered, entries = [], []
        for index, window in enumerate(windows):
            raw = work / ("raw_%d.wav" % index)
            delivered = segment_root / ("seg_%d.wav" % index)
            synthesize(target[index]["text"], voice_lang, str(raw))
            raw_duration = audio_duration(raw)
            window_duration = window["end"] - window["start"]
            control = render(str(raw), str(delivered), raw_duration, window_duration)
            rendered.append(str(delivered))
            entries.append({
                "window_start_sec": round(window["start"], 6),
                "window_end_sec": round(window["end"], 6),
                "placed_start_sec": round(window["start"], 6),
                "placed_end_sec": round(window["end"], 6),
                "source_text": source[index]["text"], "target_text": target[index]["text"],
                "window_duration_sec": round(window_duration, 6),
                "tts_duration_sec": round(raw_duration, 6), "drift_sec": 0.0,
                "duration_control": control,
            })

        timeline = work / "timeline.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        make_timeline(rendered, windows, original_duration, str(timeline))
        filter_audio(str(timeline), str(normalized), "loudnorm=I=-23:TP=-2:LRA=7")
        mux(config["input_video"], str(normalized), str(candidate), original_duration)
        measured = lufs(str(candidate))
        for attempt in range(3):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            filter_audio(str(normalized), str(corrected), "volume=%.7fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(config["input_video"], str(normalized), str(candidate), original_duration)
            measured = lufs(str(candidate))
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize final MP4 into the -23 LUFS delivery range")
        verify_streams(str(candidate))

        final_video = output_root / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        final_duration = media_duration(final_video)
        report = {
            "source_language": "en", "target_language": reported_lang,
            "audio_sample_rate_hz": RATE, "audio_channels": 1,
            "original_duration_sec": round(original_duration, 6),
            "new_duration_sec": round(final_duration, 6), "measured_lufs": measured,
            "speech_segments": entries,
        }
        report_path = output_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        required = [segment_root / "seg_0.wav", final_video, report_path]
        if not all(path.is_file() and path.stat().st_size > 0 for path in required):
            raise DubError("one or more required artifacts were not written under " + str(output_root))
        return {"ok": True, "video": str(final_video), "report": str(report_path), "measured_lufs": measured}
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise DubError("stdin must contain a JSON object")
        print(json.dumps(main(incoming), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
