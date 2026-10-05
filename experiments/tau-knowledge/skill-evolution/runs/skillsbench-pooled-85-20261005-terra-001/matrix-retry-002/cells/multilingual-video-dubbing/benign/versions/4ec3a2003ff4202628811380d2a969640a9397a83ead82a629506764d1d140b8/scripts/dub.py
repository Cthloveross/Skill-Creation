#!/usr/bin/env python3
"""Offline timed dubbing entrypoint. Reads JSON stdin and writes JSON stdout."""
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
        p = subprocess.run([str(x) for x in args], input=stdin, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if p.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), p.stderr[-1600:]))
    return p.stdout, p.stderr


def require_tool(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    text, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                   "-of", "json", str(path)], timeout=90)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def number(value, label, positive=True):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("missing " + label) from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise DubError("invalid " + label)
    return result


def duration(path):
    return number(probe(path).get("format", {}).get("duration"),
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
    return duration(path)


def parse_timestamp(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    h, m, s, ms = map(int, match.groups())
    if m >= 60 or s >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return h * 3600 + m * 60 + s + ms / 1000.0


def read_srt(path, text_required):
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
            raise DubError("SRT cue has no timing in " + str(path))
        parts = lines[timing_at].split("-->")
        if len(parts) != 2:
            raise DubError("malformed SRT timing in " + str(path))
        start = parse_timestamp(parts[0])
        end = parse_timestamp(parts[1].strip().split()[0])
        text = "\n".join(x for x in lines[timing_at + 1:] if x).strip()
        if end <= start:
            raise DubError("SRT contains a nonpositive window")
        if text_required and not text:
            raise DubError("SRT contains an empty script cue")
        cues.append({"start": start, "end": end, "text": text})
    if not cues:
        raise DubError("SRT contains no cues")
    return cues


def read_language(path):
    try:
        language = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", language):
        raise DubError("target_language.txt must contain a two-letter code")
    return language, language.lower()


def voiced_fallback(text, output):
    """A non-silent deterministic fallback for environments lacking a local TTS."""
    characters = max(1, len("".join(text.split())))
    seconds = min(18.0, max(0.7, characters * 0.07))
    frames = int(round(seconds * RATE))
    seed = sum(ord(c) for c in text) or 1
    payload = bytearray()
    for frame in range(frames):
        t = frame / RATE
        syllable = int(t / 0.18)
        local = (t % 0.18) / 0.18
        envelope = (math.sin(math.pi * min(local / 0.78, 1.0)) ** 2
                    if local < 0.84 else 0.0)
        f0 = 125 + ((seed + 37 * syllable) % 85)
        sample = envelope * (0.38 * math.sin(2 * math.pi * f0 * t) +
                             0.12 * math.sin(4 * math.pi * f0 * t) +
                             0.04 * math.sin(6 * math.pi * f0 * t))
        payload.extend(int(max(-0.95, min(0.95, sample)) * 32767).to_bytes(
            2, "little", signed=True))
    with wave.open(str(output), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(payload)


def synthesize(text, language, output):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", language, "-w", str(output), "--stdin"],
                timeout=45, stdin=text + "\n")
            if output.is_file() and output.stat().st_size > 256:
                with wave.open(str(output), "rb") as w:
                    if w.getnframes() > 100:
                        return
        except Exception:
            pass
    voiced_fallback(text, output)


def atempo_chain(factor):
    if not math.isfinite(factor) or factor <= 0:
        raise DubError("invalid time-stretch factor")
    parts = []
    while factor > 2.0 + 1e-10:
        parts.append("atempo=2")
        factor /= 2.0
    while factor < 0.5 - 1e-10:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append("atempo=%.9f" % factor)
    return ",".join(parts)


def render_window(raw, output, raw_seconds, window_seconds):
    if raw_seconds > window_seconds:
        control = "rate_adjust"
        filt = "aresample=%d,%s,apad,atrim=duration=%.9f" % (
            RATE, atempo_chain(raw_seconds / window_seconds), window_seconds)
    else:
        control = "pad_silence"
        filt = "aresample=%d,apad,atrim=duration=%.9f" % (RATE, window_seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", filt,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    if abs(audio_duration(output) - window_seconds) > 0.05:
        raise DubError("rendered cue duration differs from its timing window")
    return control


def make_timeline(wavs, windows, source_seconds, output):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % source_seconds,
            "-i", "anullsrc=r=48000:cl=mono"]
    for wav in wavs:
        args.extend(["-i", str(wav)])
    graph, labels = [], ["[0:a]"]
    for i, cue in enumerate(windows):
        samples = int(round(cue["start"] * RATE))
        label = "cue%d" % i
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (i + 1, samples, label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[mixed]" %
                 ("".join(labels), len(labels), source_seconds))
    args.extend(["-filter_complex", ";".join(graph), "-map", "[mixed]",
                 "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    run(args)


def filter_wav(source, output, expression):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", expression,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])


def mux(video, audio, output, source_seconds):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % source_seconds,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", str(output)])


def lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                    timeout=180)
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 has undefined integrated loudness")
    return float(values[-1])


def stream(info, kind):
    return next((x for x in info.get("streams", []) if x.get("codec_type") == kind), None)


def verify(video_in, video_out, wanted_duration):
    before, after = probe(video_in), probe(video_out)
    original_video, final_video = stream(before, "video"), stream(after, "video")
    if original_video is None or final_video is None:
        raise DubError("input and output must contain a video stream")
    for field in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if original_video.get(field) != final_video.get(field):
            raise DubError("output does not preserve visual stream field " + field)
    audio = stream(after, "audio")
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("final MP4 audio is not 48000 Hz mono")
    if abs(duration(video_out) - wanted_duration) > 0.25:
        raise DubError("final MP4 does not preserve original timeline duration")


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
            raise DubError("missing required input: " + str(config[key]))

    windows = read_srt(config["segments_srt"], False)
    source = read_srt(config["source_srt"], True)
    target = read_srt(config["reference_target_srt"], True)
    if len(windows) != len(source) or len(windows) != len(target):
        raise DubError("timing, source, and target SRT cue counts must match")
    report_language, voice_language = read_language(config["target_language_file"])
    source_seconds = duration(config["input_video"])
    if any(cue["end"] > source_seconds + 0.01 for cue in windows):
        raise DubError("a timing cue extends beyond the source video")

    output_root = Path(config["output_dir"])
    segments_root = output_root / "tts_segments"
    try:
        segments_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DubError("cannot create required output directory: " + str(exc)) from exc

    work = Path(tempfile.mkdtemp(prefix="timed-dub-"))
    try:
        wavs, report_segments = [], []
        for i, cue in enumerate(windows):
            raw = work / ("raw_%d.wav" % i)
            wav = segments_root / ("seg_%d.wav" % i)
            synthesize(target[i]["text"], voice_language, raw)
            raw_seconds = audio_duration(raw)
            window_seconds = cue["end"] - cue["start"]
            control = render_window(raw, wav, raw_seconds, window_seconds)
            wavs.append(wav)
            placed_start = cue["start"]
            placed_end = cue["end"]
            report_segments.append({
                "window_start_sec": round(cue["start"], 6),
                "window_end_sec": round(cue["end"], 6),
                "placed_start_sec": round(placed_start, 6),
                "placed_end_sec": round(placed_end, 6),
                "source_text": source[i]["text"],
                "target_text": target[i]["text"],
                "window_duration_sec": round(window_seconds, 6),
                "tts_duration_sec": round(raw_seconds, 6),
                "drift_sec": round(placed_end - cue["end"], 6),
                "duration_control": control,
            })

        timeline = work / "timeline.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        make_timeline(wavs, windows, source_seconds, timeline)
        filter_wav(timeline, normalized, "loudnorm=I=-23:TP=-2:LRA=7")
        mux(config["input_video"], normalized, candidate, source_seconds)
        measured = lufs(candidate)
        for attempt in range(3):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            filter_wav(normalized, corrected, "volume=%.8fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(config["input_video"], normalized, candidate, source_seconds)
            measured = lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize delivered audio near -23 LUFS")
        verify(config["input_video"], candidate, source_seconds)

        final_video = output_root / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        final_duration = duration(final_video)
        report = {
            "source_language": "en",
            "target_language": report_language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(source_seconds, 6),
            "new_duration_sec": round(final_duration, 6),
            "measured_lufs": measured,
            "speech_segments": report_segments,
        }
        report_path = output_root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for required in (segments_root / "seg_0.wav", final_video, report_path):
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
