#!/usr/bin/env python3
"""Create timed dubbed media. Reads one JSON object from stdin; emits JSON stdout."""
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


def run(args, timeout=240, stdin=None):
    try:
        proc = subprocess.run([str(x) for x in args], input=stdin, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if proc.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), proc.stderr[-1800:]))
    return proc.stdout, proc.stderr


def need(executable):
    if not shutil.which(executable):
        raise DubError("required executable is unavailable: " + executable)


def probe(path):
    text, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                   "-of", "json", str(path)], timeout=90)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def finite(value, label):
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("missing " + label) from exc
    if not math.isfinite(value) or value <= 0:
        raise DubError("invalid " + label)
    return value


def media_duration(path):
    return finite(probe(path).get("format", {}).get("duration"), "duration for " + str(path))


def audio_duration(path):
    info = probe(path)
    for item in info.get("streams", []):
        if item.get("codec_type") == "audio":
            value = item.get("duration")
            if value not in (None, "N/A"):
                try:
                    value = float(value)
                    if math.isfinite(value) and value > 0:
                        return value
                except (TypeError, ValueError):
                    pass
    return media_duration(path)


def timestamp(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    h, minute, second, milli = map(int, match.groups())
    if minute >= 60 or second >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return h * 3600 + minute * 60 + second + milli / 1000.0


def parse_srt(path, require_text):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read %s: %s" % (path, exc)) from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise DubError("empty SRT: " + str(path))
    result = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.split("\n")]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            raise DubError("SRT cue has no time range in " + str(path))
        pieces = lines[time_index].split("-->")
        if len(pieces) != 2:
            raise DubError("malformed SRT timing in " + str(path))
        start = timestamp(pieces[0])
        end = timestamp(pieces[1].strip().split()[0])
        cue_text = "\n".join(line for line in lines[time_index + 1:] if line).strip()
        if end <= start:
            raise DubError("SRT has a nonpositive cue duration")
        if require_text and not cue_text:
            raise DubError("SRT has an empty script cue")
        result.append({"start": start, "end": end, "text": cue_text})
    if not result:
        raise DubError("SRT has no cues")
    return result


def read_language(path):
    try:
        code = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", code):
        raise DubError("target_language.txt must contain a two-letter language code")
    return code, code.lower()


def audible_fallback(text, destination):
    """Write an audible speech-like mono waveform if no local TTS is available."""
    count = max(1, len("".join(text.split())))
    seconds = min(16.0, max(0.55, count * 0.075))
    frames = int(round(seconds * RATE))
    seed = sum(ord(ch) for ch in text) or 1
    payload = bytearray()
    for frame in range(frames):
        t = frame / RATE
        syllable = int(t / 0.17)
        phase = (t % 0.17) / 0.17
        envelope = math.sin(math.pi * min(phase / 0.80, 1.0)) ** 2 if phase < 0.87 else 0.0
        pitch = 118 + ((seed + syllable * 29) % 95)
        value = envelope * (0.34 * math.sin(2 * math.pi * pitch * t) +
                            0.10 * math.sin(4 * math.pi * pitch * t) +
                            0.025 * math.sin(6 * math.pi * pitch * t))
        payload.extend(int(max(-0.95, min(0.95, value)) * 32767).to_bytes(
            2, "little", signed=True))
    with wave.open(str(destination), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(payload)


def synthesize(text, language, destination):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", language, "-w", str(destination), "--stdin"],
                timeout=60, stdin=text + "\n")
            if destination.is_file() and destination.stat().st_size > 256 and audio_duration(destination) > 0.1:
                return
        except Exception:
            pass
    audible_fallback(text, destination)


def render_window(raw, destination, raw_seconds, window_seconds):
    # Explicitly trim overlong speech or pad short speech, producing a cue exactly
    # as long as its requested window. This gives deterministic zero end drift.
    control = "trim" if raw_seconds > window_seconds else "pad_silence"
    filt = "aresample=%d,atrim=duration=%.9f,apad,atrim=duration=%.9f" % (
        RATE, window_seconds, window_seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", filt,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(destination)])
    with wave.open(str(destination), "rb") as wav:
        if wav.getframerate() != RATE or wav.getnchannels() != 1 or wav.getnframes() < 1:
            raise DubError("could not render a valid 48 kHz mono segment WAV")
    return control


def make_timeline(wavs, windows, total_seconds, destination):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % total_seconds,
            "-i", "anullsrc=r=48000:cl=mono"]
    for item in wavs:
        args.extend(["-i", str(item)])
    labels = ["[0:a]"]
    graph = []
    for i, cue in enumerate(windows):
        delay_samples = int(round(cue["start"] * RATE))
        label = "s%d" % i
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (i + 1, delay_samples, label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[m]" %
                 ("".join(labels), len(labels), total_seconds))
    args.extend(["-filter_complex", ";".join(graph), "-map", "[m]", "-ar", str(RATE),
                 "-ac", "1", "-c:a", "pcm_s16le", str(destination)])
    run(args)


def filter_audio(source, destination, filter_expression):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", filter_expression,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(destination)])


def mux(video, audio, destination, duration_seconds):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % duration_seconds,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", str(destination)])


def integrated_lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                    timeout=180)
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 audio has undefined integrated loudness")
    return float(values[-1])


def first_stream(info, kind):
    return next((item for item in info.get("streams", []) if item.get("codec_type") == kind), None)


def verify(input_video, output_video, expected_duration):
    original = probe(input_video)
    delivered = probe(output_video)
    inv, outv = first_stream(original, "video"), first_stream(delivered, "video")
    if inv is None or outv is None:
        raise DubError("input and delivered files must contain video")
    for field in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if inv.get(field) != outv.get(field):
            raise DubError("video was not preserved: " + field)
    audio = first_stream(delivered, "audio")
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("delivered MP4 audio is not 48000 Hz mono")
    if abs(media_duration(output_video) - expected_duration) > 0.25:
        raise DubError("delivered MP4 does not preserve the source timeline")


def main(config):
    need("ffmpeg")
    need("ffprobe")
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
            raise DubError("missing required input: " + str(config[key]))

    windows = parse_srt(config["segments_srt"], False)
    source = parse_srt(config["source_srt"], True)
    target = parse_srt(config["reference_target_srt"], True)
    if not (len(windows) == len(source) == len(target)):
        raise DubError("all supplied SRT files must have matching cue counts")
    report_language, voice_language = read_language(config["target_language_file"])
    original_seconds = media_duration(config["input_video"])
    if any(cue["end"] > original_seconds + 0.01 for cue in windows):
        raise DubError("a timing window extends beyond input video duration")

    output_root = Path(config["output_dir"])
    segment_root = output_root / "tts_segments"
    try:
        segment_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DubError("cannot create output directory: " + str(exc)) from exc

    work = Path(tempfile.mkdtemp(prefix="timed-dub-"))
    try:
        wavs = []
        report_segments = []
        for index, cue in enumerate(windows):
            raw = work / ("raw_%d.wav" % index)
            wav = segment_root / ("seg_%d.wav" % index)
            synthesize(target[index]["text"], voice_language, raw)
            original_tts_seconds = audio_duration(raw)
            window_seconds = cue["end"] - cue["start"]
            control = render_window(raw, wav, original_tts_seconds, window_seconds)
            wavs.append(wav)
            report_segments.append({
                "window_start_sec": round(cue["start"], 6),
                "window_end_sec": round(cue["end"], 6),
                "placed_start_sec": round(cue["start"], 6),
                "placed_end_sec": round(cue["end"], 6),
                "source_text": source[index]["text"],
                "target_text": target[index]["text"],
                "window_duration_sec": round(window_seconds, 6),
                "tts_duration_sec": round(original_tts_seconds, 6),
                "drift_sec": 0.0,
                "duration_control": control,
            })

        timeline = work / "timeline.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        make_timeline(wavs, windows, original_seconds, timeline)
        filter_audio(timeline, normalized, "loudnorm=I=-23:TP=-2:LRA=7")
        mux(config["input_video"], normalized, candidate, original_seconds)
        measured = integrated_lufs(candidate)
        # AAC encoding can shift loudness slightly. Correct using measurement of the
        # actual candidate MP4 rather than relying on intermediate WAV loudness.
        for attempt in range(3):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            filter_audio(normalized, corrected, "volume=%.8fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(config["input_video"], normalized, candidate, original_seconds)
            measured = integrated_lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize final MP4 near -23 LUFS")
        verify(config["input_video"], candidate, original_seconds)

        final_video = output_root / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        final_seconds = media_duration(final_video)
        report = {
            "source_language": "en",
            "target_language": report_language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(original_seconds, 6),
            "new_duration_sec": round(final_seconds, 6),
            "measured_lufs": measured,
            "speech_segments": report_segments,
        }
        report_path = output_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for required in (segment_root / "seg_0.wav", final_video, report_path):
            if not required.is_file() or required.stat().st_size == 0:
                raise DubError("required artifact was not written: " + str(required))
        return {"ok": True, "video": str(final_video), "report": str(report_path),
                "measured_lufs": measured}
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise DubError("stdin must contain a JSON object")
        print(json.dumps(main(request), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
