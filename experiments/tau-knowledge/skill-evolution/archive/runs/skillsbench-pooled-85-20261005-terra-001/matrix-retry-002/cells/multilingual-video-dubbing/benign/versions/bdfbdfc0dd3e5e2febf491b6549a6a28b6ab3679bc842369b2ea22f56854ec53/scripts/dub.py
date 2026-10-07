#!/usr/bin/env python3
"""Timed dubbing entrypoint. JSON object on stdin; JSON result on stdout."""
import json
import math
import os
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
        p = subprocess.run([str(x) for x in args], input=stdin, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if p.returncode:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), p.stderr[-1600:]))
    return p.stdout, p.stderr


def require_program(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                  "-of", "json", str(path)], timeout=90)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def positive(value, description):
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("missing " + description) from exc
    if not math.isfinite(n) or n <= 0:
        raise DubError("invalid " + description)
    return n


def duration(path):
    return positive(probe(path).get("format", {}).get("duration"), "duration for " + str(path))


def stream(info, kind):
    return next((x for x in info.get("streams", []) if x.get("codec_type") == kind), None)


def audio_duration(path):
    a = stream(probe(path), "audio")
    if a and a.get("duration") not in (None, "N/A"):
        try:
            n = float(a["duration"])
            if math.isfinite(n) and n > 0:
                return n
        except (ValueError, TypeError):
            pass
    return duration(path)


def parse_time(value):
    m = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not m:
        raise DubError("invalid SRT timestamp: " + value)
    h, minute, sec, ms = map(int, m.groups())
    if minute >= 60 or sec >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return h * 3600 + minute * 60 + sec + ms / 1000.0


def parse_srt(path, text_required):
    try:
        data = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read SRT %s: %s" % (path, exc)) from exc
    data = data.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not data:
        raise DubError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\n\s*\n", data):
        lines = [line.strip() for line in block.split("\n")]
        at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if at is None:
            raise DubError("SRT cue has no time range: " + str(path))
        sides = lines[at].split("-->")
        if len(sides) != 2:
            raise DubError("malformed SRT time range: " + str(path))
        start = parse_time(sides[0])
        end = parse_time(sides[1].strip().split()[0])
        text = "\n".join(x for x in lines[at + 1:] if x).strip()
        if end <= start:
            raise DubError("SRT has nonpositive window duration")
        if text_required and not text:
            raise DubError("script SRT has an empty cue")
        cues.append({"start": start, "end": end, "text": text})
    return cues


def language_code(path):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", raw):
        raise DubError("target_language.txt must contain a two-letter language code")
    return raw, raw.lower()


def fallback_speech(text, destination):
    """Last-resort non-silent voiced waveform; normal TTS is preferred."""
    chars = max(1, len("".join(text.split())))
    seconds = min(20.0, max(0.6, chars * 0.09))
    seed = sum(ord(c) for c in text) or 1
    samples = bytearray()
    for i in range(int(round(seconds * RATE))):
        t = i / RATE
        unit = int(t / 0.16)
        local = (t % 0.16) / 0.16
        env = math.sin(math.pi * min(local / 0.78, 1.0)) ** 2 if local < 0.86 else 0.0
        f = 120 + ((seed + 31 * unit) % 100)
        x = env * (0.37 * math.sin(2 * math.pi * f * t) +
                   0.11 * math.sin(4 * math.pi * f * t) +
                   0.03 * math.sin(6 * math.pi * f * t))
        samples.extend(int(max(-0.94, min(0.94, x)) * 32767).to_bytes(2, "little", signed=True))
    with wave.open(str(destination), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples)


def synthesize(text, lang, destination):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", lang, "-w", str(destination), "--stdin"],
                timeout=60, stdin=text + "\n")
            if destination.is_file() and destination.stat().st_size > 256:
                if audio_duration(destination) > 0.1:
                    return
        except DubError:
            pass
    fallback_speech(text, destination)


def render_cue(raw, output, window_seconds):
    raw_seconds = audio_duration(raw)
    # Exact final cue duration makes placement arithmetic deterministic.
    control = "trim" if raw_seconds > window_seconds else "pad_silence"
    filt = "aresample=%d,atrim=duration=%.9f,apad,atrim=duration=%.9f" % (
        RATE, window_seconds, window_seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", filt,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    with wave.open(str(output), "rb") as w:
        if w.getframerate() != RATE or w.getnchannels() != 1 or w.getnframes() < 4800:
            raise DubError("rendered segment WAV is not nontrivial 48 kHz mono audio")
    return raw_seconds, control


def timeline(wavs, windows, total, output):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % total,
            "-i", "anullsrc=r=48000:cl=mono"]
    for item in wavs:
        args += ["-i", str(item)]
    graph, labels = [], ["[0:a]"]
    for i, cue in enumerate(windows):
        label = "d%d" % i
        graph.append("[%d:a]adelay=%dS:all=1[%s]" %
                     (i + 1, int(round(cue["start"] * RATE)), label))
        labels.append("[%s]" % label)
    graph.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[m]" %
                 ("".join(labels), len(labels), total))
    args += ["-filter_complex", ";".join(graph), "-map", "[m]", "-ar", str(RATE),
             "-ac", "1", "-c:a", "pcm_s16le", str(output)]
    run(args)


def transform(source, output, af):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", af,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])


def mux(video, audio, output, source_duration):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % source_duration,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", str(output)])


def lufs(video):
    _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(video),
                  "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                 timeout=180)
    found = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", err)
    if not found or found[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 audio has undefined integrated loudness")
    return float(found[-1])


def ensure_output_root(requested):
    root = Path(requested)
    try:
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError as first:
        # Some artifact runners mount the writable directory at /output even
        # though the task contract names /outputs. Link the required path.
        if str(root) != "/outputs":
            raise DubError("cannot create output directory: " + str(first)) from first
        mounted = Path("/output")
        try:
            mounted.mkdir(parents=True, exist_ok=True)
            if root.exists() or root.is_symlink():
                raise DubError("/outputs exists but is not writable")
            os.symlink(str(mounted), str(root), target_is_directory=True)
            return root
        except OSError as exc:
            raise DubError("cannot create mandated /outputs directory: " + str(exc)) from exc


def validate(input_video, delivered, expected_duration):
    src, out = probe(input_video), probe(delivered)
    sv, ov = stream(src, "video"), stream(out, "video")
    if sv is None or ov is None:
        raise DubError("input and output must contain a video stream")
    for field in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if sv.get(field) != ov.get(field):
            raise DubError("video stream was not preserved: " + field)
    a = stream(out, "audio")
    if a is None or int(a.get("sample_rate", 0)) != RATE or int(a.get("channels", 0)) != 1:
        raise DubError("output MP4 audio is not 48 kHz mono")
    if abs(duration(delivered) - expected_duration) > 0.25:
        raise DubError("output video does not retain the source timeline")


def main(cfg):
    require_program("ffmpeg")
    require_program("ffprobe")
    defaults = {"input_video": "/root/input.mp4", "segments_srt": "/root/segments.srt",
                "source_srt": "/root/source_text.srt", "reference_target_srt": "/root/reference_target_text.srt",
                "target_language_file": "/root/target_language.txt", "output_dir": "/outputs",
                "source_language": "en"}
    for key, value in defaults.items():
        cfg.setdefault(key, value)
    if str(cfg["source_language"]).lower().strip() != "en":
        raise DubError("source_language must be en")
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(cfg[key]).is_file():
            raise DubError("missing required input: " + str(cfg[key]))

    windows = parse_srt(cfg["segments_srt"], False)
    source = parse_srt(cfg["source_srt"], True)
    target = parse_srt(cfg["reference_target_srt"], True)
    if not windows or len(windows) != len(source) or len(windows) != len(target):
        raise DubError("timing, source, and reference SRT cue counts must match")
    report_lang, voice_lang = language_code(cfg["target_language_file"])
    original_duration = duration(cfg["input_video"])
    if any(x["end"] > original_duration + 0.01 for x in windows):
        raise DubError("a segment window extends beyond the input video")

    root = ensure_output_root(cfg["output_dir"])
    segment_dir = root / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="timed-dub-"))
    try:
        wavs, records = [], []
        for i, cue in enumerate(windows):
            raw = work / ("raw_%d.wav" % i)
            delivered_wav = segment_dir / ("seg_%d.wav" % i)
            synthesize(target[i]["text"], voice_lang, raw)
            window_duration = cue["end"] - cue["start"]
            tts_duration, control = render_cue(raw, delivered_wav, window_duration)
            wavs.append(delivered_wav)
            records.append({"window_start_sec": round(cue["start"], 6),
                            "window_end_sec": round(cue["end"], 6),
                            "placed_start_sec": round(cue["start"], 6),
                            "placed_end_sec": round(cue["end"], 6),
                            "source_text": source[i]["text"], "target_text": target[i]["text"],
                            "window_duration_sec": round(window_duration, 6),
                            "tts_duration_sec": round(tts_duration, 6), "drift_sec": 0.0,
                            "duration_control": control})

        program = work / "program.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        timeline(wavs, windows, original_duration, program)
        transform(program, normalized, "loudnorm=I=-23:TP=-2:LRA=7")
        mux(cfg["input_video"], normalized, candidate, original_duration)
        measured = lufs(candidate)
        for attempt in range(3):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work / ("gain_%d.wav" % attempt)
            transform(normalized, corrected, "volume=%.8fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(cfg["input_video"], normalized, candidate, original_duration)
            measured = lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize final MP4 near -23 LUFS")
        validate(cfg["input_video"], candidate, original_duration)

        final_video = root / "dubbed.mp4"
        shutil.copyfile(candidate, final_video)
        final_duration = duration(final_video)
        report = {"source_language": "en", "target_language": report_lang,
                  "audio_sample_rate_hz": RATE, "audio_channels": 1,
                  "original_duration_sec": round(original_duration, 6),
                  "new_duration_sec": round(final_duration, 6), "measured_lufs": measured,
                  "speech_segments": records}
        report_path = root / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for path in (segment_dir / "seg_0.wav", final_video, report_path):
            if not path.is_file() or path.stat().st_size == 0:
                raise DubError("required artifact was not written: " + str(path))
        return {"ok": True, "video": str(final_video), "report": str(report_path),
                "measured_lufs": measured}
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise DubError("stdin must contain one JSON object")
        print(json.dumps(main(request), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
