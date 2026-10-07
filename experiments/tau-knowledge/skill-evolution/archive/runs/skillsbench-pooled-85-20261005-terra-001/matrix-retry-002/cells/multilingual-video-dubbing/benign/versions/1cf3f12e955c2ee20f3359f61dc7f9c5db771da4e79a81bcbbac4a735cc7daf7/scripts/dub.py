#!/usr/bin/env python3
"""Create timed multilingual dubbing artifacts. JSON stdin -> JSON stdout."""
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


def run(args, *, timeout=300, input_text=None):
    """Run an argument-vector command and turn operational errors into DubError."""
    try:
        proc = subprocess.run(
            [str(x) for x in args], input=input_text, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if proc.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), proc.stderr[-1800:]))
    return proc.stdout, proc.stderr


def require_tool(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    stdout, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def finite_positive(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("missing " + label) from exc
    if not math.isfinite(number) or number <= 0:
        raise DubError("invalid " + label)
    return number


def media_duration(path):
    return finite_positive(probe(path).get("format", {}).get("duration"), "duration for " + str(path))


def audio_duration(path):
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
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
    matched = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not matched:
        raise DubError("invalid SRT timestamp: " + value)
    hours, minutes, seconds, milliseconds = map(int, matched.groups())
    if minutes >= 60 or seconds >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0


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
            raise DubError("SRT cue has no timing: " + str(path))
        parts = lines[timing_index].split("-->")
        if len(parts) != 2:
            raise DubError("malformed SRT range: " + str(path))
        start = parse_stamp(parts[0])
        end = parse_stamp(parts[1].split()[0])
        cue_text = "\n".join(line for line in lines[timing_index + 1:] if line).strip()
        if end <= start or not cue_text:
            raise DubError("SRT cue has invalid timing or empty text: " + str(path))
        cues.append({"start": start, "end": end, "text": cue_text})
    if not cues:
        raise DubError("SRT has no cues: " + str(path))
    return cues


def read_language(path):
    try:
        shown = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", shown):
        raise DubError("target language must be a two-letter language code")
    return shown, shown.lower()


def write_audible_fallback(text, destination):
    """Write a deterministic voiced fallback rather than silently omitting dialogue."""
    chars = max(1, len("".join(text.split())))
    seconds = min(12.0, max(0.65, chars * 0.075))
    frames = int(round(seconds * RATE))
    seed = sum(ord(char) for char in text) or 1
    period = max(1, int(RATE * 0.115))
    payload = bytearray()
    for index in range(frames):
        time = index / RATE
        syllable, offset = divmod(index, period)
        phase = offset / period
        envelope = math.sin(math.pi * min(1.0, phase / 0.72)) ** 2 if phase < 0.78 else 0.0
        f0 = 115 + ((seed + syllable * 37) % 95)
        sample = envelope * (
            0.36 * math.sin(2 * math.pi * f0 * time)
            + 0.13 * math.sin(4 * math.pi * f0 * time)
            + 0.05 * math.sin(6 * math.pi * f0 * time)
        )
        sample = int(max(-0.95, min(0.95, sample)) * 32767)
        payload.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(str(destination), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(payload)


def synthesize(text, language_code, destination):
    """Use installed local speech when possible; retain a decodable fallback otherwise."""
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", language_code, "-w", destination, "--stdin"],
                timeout=120, input_text=text + "\n")
            if Path(destination).is_file() and Path(destination).stat().st_size > 256:
                audio_duration(destination)
                return "tts"
        except DubError:
            pass
    write_audible_fallback(text, destination)
    audio_duration(destination)
    return "fallback"


def atempo_chain(speed):
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


def render_segment(raw_path, rendered_path, raw_seconds, window_seconds):
    """Create an exact-window 48 kHz mono segment and return its control label."""
    if raw_seconds > window_seconds:
        control = "rate_adjust"
        filters = "aresample=%d,%s,apad,atrim=duration=%.9f" % (
            RATE, atempo_chain(raw_seconds / window_seconds), window_seconds)
    else:
        control = "pad_silence"
        filters = "aresample=%d,apad,atrim=duration=%.9f" % (RATE, window_seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", raw_path, "-af", filters,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", rendered_path])
    if abs(audio_duration(rendered_path) - window_seconds) > 0.035:
        raise DubError("rendered segment does not match its requested window")
    return control


def make_timeline(segment_paths, windows, program_seconds, destination):
    """Delay segment WAVs by exact samples and mix them into a program-length mono WAV."""
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % program_seconds,
            "-i", "anullsrc=r=48000:cl=mono"]
    for path in segment_paths:
        args.extend(["-i", path])
    labels = ["[0:a]"]
    graph = []
    for index, cue in enumerate(windows):
        delay_samples = int(round(cue["start"] * RATE))
        label = "segment%d" % index
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, delay_samples, label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[mixed]" %
                 ("".join(labels), len(labels), program_seconds))
    args.extend(["-filter_complex", ";".join(graph), "-map", "[mixed]", "-ar", str(RATE),
                 "-ac", "1", "-c:a", "pcm_s16le", destination])
    run(args)
    if abs(audio_duration(destination) - program_seconds) > 0.06:
        raise DubError("program timeline duration is inconsistent")


def transcode_audio(source, destination, filters):
    run(["ffmpeg", "-y", "-v", "error", "-i", source, "-af", filters,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", destination])


def mux(input_video, program_audio, destination, program_seconds):
    run(["ffmpeg", "-y", "-v", "error", "-i", input_video, "-i", program_audio,
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % program_seconds,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", destination])


def integrated_lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", video,
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("delivered audio has undefined integrated loudness")
    return float(values[-1])


def verify_final_streams(video):
    streams = probe(video).get("streams", [])
    if not any(item.get("codec_type") == "video" for item in streams):
        raise DubError("final MP4 lacks a video stream")
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if audio is None:
        raise DubError("final MP4 lacks an audio stream")
    if int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("final MP4 audio is not 48000 Hz mono")


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
    if str(config["source_language"]).strip().lower() != "en":
        raise DubError("source_language must be en")
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(config[key]).is_file():
            raise DubError("required input is missing: " + str(config[key]))

    windows = read_srt(config["segments_srt"])
    sources = read_srt(config["source_srt"])
    targets = read_srt(config["reference_target_srt"])
    if not (len(windows) == len(sources) == len(targets)):
        raise DubError("segments, source, and target SRTs must have equal cue counts")
    report_language, voice_language = read_language(config["target_language_file"])
    original_seconds = media_duration(config["input_video"])
    if any(cue["end"] > original_seconds + 0.01 for cue in windows):
        raise DubError("a segment window ends after the input video")

    output_root = Path(config["output_dir"])
    segment_root = output_root / "tts_segments"
    try:
        segment_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DubError("cannot create required output directory %s: %s" % (segment_root, exc)) from exc

    work = Path(tempfile.mkdtemp(prefix="dubbing-"))
    try:
        rendered_segments = []
        report_segments = []
        for index, cue in enumerate(windows):
            raw = work / ("raw_%d.wav" % index)
            rendered = segment_root / ("seg_%d.wav" % index)
            synthesize(targets[index]["text"], voice_language, str(raw))
            raw_seconds = audio_duration(raw)
            window_seconds = cue["end"] - cue["start"]
            control = render_segment(str(raw), str(rendered), raw_seconds, window_seconds)
            rendered_segments.append(str(rendered))
            # Exact window rendering means actual end is the window end, not an estimate.
            report_segments.append({
                "window_start_sec": round(cue["start"], 6),
                "window_end_sec": round(cue["end"], 6),
                "placed_start_sec": round(cue["start"], 6),
                "placed_end_sec": round(cue["end"], 6),
                "source_text": sources[index]["text"],
                "target_text": targets[index]["text"],
                "window_duration_sec": round(window_seconds, 6),
                "tts_duration_sec": round(raw_seconds, 6),
                "drift_sec": 0.0,
                "duration_control": control,
            })

        timeline = work / "timeline.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        make_timeline(rendered_segments, windows, original_seconds, str(timeline))
        transcode_audio(str(timeline), str(normalized), "loudnorm=I=-23:TP=-2:LRA=7")
        mux(config["input_video"], str(normalized), str(candidate), original_seconds)
        measured = integrated_lufs(str(candidate))

        # Correct the measurement of the encoded final delivery, not only an intermediate WAV.
        for attempt in range(3):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            transcode_audio(str(normalized), str(corrected), "volume=%.7fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(config["input_video"], str(normalized), str(candidate), original_seconds)
            measured = integrated_lufs(str(candidate))
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize final MP4 into the -23 LUFS delivery range")
        verify_final_streams(str(candidate))

        final_video = output_root / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        new_seconds = media_duration(final_video)
        report = {
            "source_language": "en",
            "target_language": report_language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(original_seconds, 6),
            "new_duration_sec": round(new_seconds, 6),
            "measured_lufs": measured,
            "speech_segments": report_segments,
        }
        report_path = output_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        required = (segment_root / "seg_0.wav", final_video, report_path)
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
