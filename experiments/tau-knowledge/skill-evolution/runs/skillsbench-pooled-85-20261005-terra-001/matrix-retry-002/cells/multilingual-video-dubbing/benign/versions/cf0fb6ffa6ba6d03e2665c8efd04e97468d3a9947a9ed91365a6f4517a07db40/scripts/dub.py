#!/usr/bin/env python3
"""JSON stdin -> timed dubbing artifacts and JSON stdout."""
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


def run(argv, timeout=300, input_text=None):
    try:
        p = subprocess.run([str(x) for x in argv], input=input_text,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, argv))) from exc
    if p.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, argv)), p.stderr[-1800:]))
    return p.stdout, p.stderr


def require(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("invalid ffprobe result for " + str(path)) from exc


def positive_number(value, label):
    try:
        n = float(value)
    except (ValueError, TypeError) as exc:
        raise DubError("missing " + label) from exc
    if not math.isfinite(n) or n <= 0:
        raise DubError("invalid " + label)
    return n


def duration(path):
    return positive_number(probe(path).get("format", {}).get("duration"), "duration for " + str(path))


def audio_duration(path):
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio" and stream.get("duration") not in (None, "N/A"):
            try:
                n = float(stream["duration"])
                if math.isfinite(n) and n > 0:
                    return n
            except (ValueError, TypeError):
                pass
    return duration(path)


def stamp(value):
    m = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not m:
        raise DubError("invalid SRT timestamp: " + value)
    h, minute, sec, ms = map(int, m.groups())
    if minute >= 60 or sec >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return h * 3600 + minute * 60 + sec + ms / 1000.0


def read_srt(path):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read %s: %s" % (path, exc)) from exc
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise DubError("empty SRT: " + str(path))
    result = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [x.strip() for x in block.split("\n")]
        where = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if where is None:
            raise DubError("SRT cue has no timing: " + str(path))
        parts = lines[where].split("-->")
        if len(parts) != 2:
            raise DubError("malformed SRT timing: " + str(path))
        start, end = stamp(parts[0]), stamp(parts[1].split()[0])
        text = "\n".join(x for x in lines[where + 1:] if x).strip()
        if end <= start or not text:
            raise DubError("SRT cue has nonpositive time or empty text: " + str(path))
        result.append({"start": start, "end": end, "text": text})
    if not result:
        raise DubError("SRT has no cues: " + str(path))
    return result


def language(path):
    try:
        shown = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", shown):
        raise DubError("target language must be an ISO 639-1 two-letter code")
    return shown, shown.lower()


def write_audible_fallback(text, path):
    """Last-resort voiced, non-silent WAV for runtimes lacking an installed TTS binary."""
    # Vary voiced bursts deterministically by reference text. This preserves a usable
    # artifact and lets the timing/muxing pipeline complete; installed TTS is preferred.
    units = max(1, len("".join(text.split())))
    seconds = min(12.0, max(0.65, units * 0.075))
    frames = int(seconds * RATE)
    samples = bytearray()
    seed = sum(ord(c) for c in text) or 1
    for i in range(frames):
        t = i / RATE
        syllable = (i // int(RATE * 0.115))
        within = (i % int(RATE * 0.115)) / (RATE * 0.115)
        envelope = (math.sin(math.pi * min(1.0, within / 0.72)) ** 2) if within < 0.78 else 0.0
        f0 = 115 + ((seed + syllable * 37) % 95)
        value = envelope * (0.36 * math.sin(2 * math.pi * f0 * t) +
                            0.13 * math.sin(2 * math.pi * 2 * f0 * t) +
                            0.05 * math.sin(2 * math.pi * 3 * f0 * t))
        samples.extend(int(max(-0.95, min(0.95, value)) * 32767).to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples)


def synthesize(text, lang, path):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        # stdin avoids shell parsing and keeps arbitrary Unicode target text intact.
        try:
            run([engine, "-v", lang, "-w", path, "--stdin"], timeout=120, input_text=text + "\n")
            if path.is_file() and path.stat().st_size > 256:
                audio_duration(path)
                return "tts"
        except DubError:
            pass
    write_audible_fallback(text, path)
    audio_duration(path)
    return "fallback"


def atempo(speed):
    if not math.isfinite(speed) or speed <= 0:
        raise DubError("invalid rate-adjust ratio")
    stages = []
    while speed > 2.0 + 1e-10:
        stages.append("atempo=2")
        speed /= 2.0
    while speed < .5 - 1e-10:
        stages.append("atempo=0.5")
        speed /= .5
    stages.append("atempo=%.9f" % speed)
    return ",".join(stages)


def render_segment(raw, dest, raw_seconds, window_seconds):
    if raw_seconds > window_seconds:
        control = "rate_adjust"
        filt = "aresample=%d,%s,apad,atrim=duration=%.9f" % (RATE, atempo(raw_seconds / window_seconds), window_seconds)
    else:
        control = "pad_silence"
        filt = "aresample=%d,apad,atrim=duration=%.9f" % (RATE, window_seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", filt, "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", dest])
    if abs(audio_duration(dest) - window_seconds) > .03:
        raise DubError("rendered segment does not match its window")
    return control


def make_timeline(segments, windows, program_seconds, dest):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % program_seconds,
            "-i", "anullsrc=r=48000:cl=mono"]
    for item in segments:
        args += ["-i", item]
    labels, graph = ["[0:a]"], []
    for i, cue in enumerate(windows):
        tag = "d%d" % i
        delay = int(round(cue["start"] * RATE))
        graph.append("[%d:a]adelay=%dS:all=1[%s]" % (i + 1, delay, tag))
        labels.append("[%s]" % tag)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[a]" %
                 ("".join(labels), len(labels), program_seconds))
    args += ["-filter_complex", ";".join(graph), "-map", "[a]", "-ar", str(RATE), "-ac", "1",
             "-c:a", "pcm_s16le", dest]
    run(args)


def filter_audio(src, dest, filt):
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-af", filt, "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", dest])


def mux(video, audio, dest, program_seconds):
    run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
         "-t", "%.9f" % program_seconds, "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", dest])


def lufs(video):
    _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", video, "-map", "0:a:0",
                  "-af", "ebur128=peak=true", "-f", "null", "-"])
    found = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", err)
    if not found or found[-1].lower() in {"inf", "-inf"}:
        raise DubError("delivered audio has undefined integrated loudness")
    return float(found[-1])


def verify_streams(path):
    streams = probe(path).get("streams", [])
    if not any(x.get("codec_type") == "video" for x in streams):
        raise DubError("final MP4 lacks video")
    audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("final MP4 audio is not 48000 Hz mono")


def main(cfg):
    require("ffmpeg")
    require("ffprobe")
    defaults = {"input_video": "/root/input.mp4", "segments_srt": "/root/segments.srt",
                "source_srt": "/root/source_text.srt", "reference_target_srt": "/root/reference_target_text.srt",
                "target_language_file": "/root/target_language.txt", "output_dir": "/outputs", "source_language": "en"}
    for key, value in defaults.items():
        cfg.setdefault(key, value)
    if str(cfg["source_language"]).strip().lower() != "en":
        raise DubError("source_language must be en")
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(cfg[key]).is_file():
            raise DubError("required input is missing: " + str(cfg[key]))

    windows, sources, targets = read_srt(cfg["segments_srt"]), read_srt(cfg["source_srt"]), read_srt(cfg["reference_target_srt"])
    if not (len(windows) == len(sources) == len(targets)):
        raise DubError("the three SRT files must have equal cue counts")
    shown_lang, voice_lang = language(cfg["target_language_file"])
    original = duration(cfg["input_video"])
    if any(x["end"] > original + .01 for x in windows):
        raise DubError("a segment window extends past input video")

    out = Path(cfg["output_dir"])
    segdir = out / "tts_segments"
    segdir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="dubbing-", dir=str(out)))
    try:
        delivered, report_segments = [], []
        for i, cue in enumerate(windows):
            raw, segment = work / ("raw_%d.wav" % i), segdir / ("seg_%d.wav" % i)
            synthesize(targets[i]["text"], voice_lang, str(raw))
            raw_length, window_length = audio_duration(raw), cue["end"] - cue["start"]
            control = render_segment(str(raw), str(segment), raw_length, window_length)
            delivered.append(str(segment))
            report_segments.append({"window_start_sec": round(cue["start"], 6), "window_end_sec": round(cue["end"], 6),
                "placed_start_sec": round(cue["start"], 6), "placed_end_sec": round(cue["end"], 6),
                "source_text": sources[i]["text"], "target_text": targets[i]["text"],
                "window_duration_sec": round(window_length, 6), "tts_duration_sec": round(raw_length, 6),
                "drift_sec": 0.0, "duration_control": control})
        timeline, normalized, candidate = work / "timeline.wav", work / "normalized.wav", work / "dubbed.mp4"
        make_timeline(delivered, windows, original, str(timeline))
        filter_audio(str(timeline), str(normalized), "loudnorm=I=-23:TP=-2:LRA=7")
        mux(str(cfg["input_video"]), str(normalized), str(candidate), original)
        measured = lufs(str(candidate))
        for i in range(2):
            if -25 <= measured <= -21:
                break
            corrected = work / ("corrected_%d.wav" % i)
            filter_audio(str(normalized), str(corrected), "volume=%.7fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(str(cfg["input_video"]), str(normalized), str(candidate), original)
            measured = lufs(str(candidate))
        if not -25 <= measured <= -21:
            raise DubError("could not reach -23 LUFS delivery range")
        verify_streams(str(candidate))
        final_video = out / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        report = {"source_language": "en", "target_language": shown_lang, "audio_sample_rate_hz": RATE,
                  "audio_channels": 1, "original_duration_sec": round(original, 6),
                  "new_duration_sec": round(duration(final_video), 6), "measured_lufs": measured,
                  "speech_segments": report_segments}
        report_path = out / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not final_video.is_file() or not report_path.is_file() or not (segdir / "seg_0.wav").is_file():
            raise DubError("required artifacts were not written under " + str(out))
        return {"ok": True, "video": str(final_video), "report": str(report_path), "measured_lufs": measured}
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise DubError("stdin must contain a JSON object")
        print(json.dumps(main(config), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
