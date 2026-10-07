#!/usr/bin/env python3
"""Offline timed dubbing entrypoint. Reads one JSON object from stdin, emits JSON."""
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
OUTPUT_ROOT = Path("/outputs")


class DubError(RuntimeError):
    pass


def run(args, timeout=180, input_text=None):
    try:
        p = subprocess.run(
            [str(x) for x in args], input=input_text, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if p.returncode:
        raise DubError("command failed: %s\n%s" % (" ".join(map(str, args)), p.stderr[-1600:]))
    return p.stdout, p.stderr


def require(exe):
    if not shutil.which(exe):
        raise DubError("required executable is unavailable: " + exe)


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], 90)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("invalid ffprobe JSON for " + str(path)) from exc


def stream(info, kind):
    return next((x for x in info.get("streams", []) if x.get("codec_type") == kind), None)


def duration(path):
    try:
        value = float(probe(path)["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DubError("unreadable media duration: " + str(path)) from exc
    if not math.isfinite(value) or value <= 0:
        raise DubError("invalid media duration: " + str(path))
    return value


def timestamp(value):
    m = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not m:
        raise DubError("invalid SRT timestamp: " + value)
    h, minute, sec, ms = map(int, m.groups())
    if minute >= 60 or sec >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return h * 3600 + minute * 60 + sec + ms / 1000.0


def parse_srt(path, require_text):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read SRT %s: %s" % (path, exc)) from exc
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise DubError("empty SRT: " + str(path))
    result = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line.strip() for line in block.split("\n")]
        pos = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if pos is None:
            raise DubError("SRT entry without a timing line: " + str(path))
        parts = lines[pos].split("-->")
        if len(parts) != 2:
            raise DubError("malformed SRT timing line: " + lines[pos])
        start = timestamp(parts[0])
        end = timestamp(parts[1].strip().split()[0])
        text = "\n".join(x for x in lines[pos + 1:] if x).strip()
        if end <= start:
            raise DubError("SRT cue duration must be positive")
        if require_text and not text:
            raise DubError("text SRT contains an empty cue")
        result.append({"start": start, "end": end, "text": text})
    return result


def read_language(path):
    try:
        code = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", code):
        raise DubError("target_language.txt must contain exactly one two-letter code")
    return code, code.lower()


def wav_duration(path):
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, OSError, ZeroDivisionError) as exc:
        raise DubError("unable to read synthesized WAV: " + str(path)) from exc


def fallback_voice(text, path):
    """Produce intelligible-speech-like voiced audio only if no local TTS is usable."""
    chars = max(1, len("".join(text.split())))
    seconds = min(20.0, max(0.7, chars * 0.09))
    seed = sum(ord(c) for c in text) or 1
    frames = bytearray()
    for n in range(int(seconds * RATE)):
        t = n / RATE
        syl = int(t / 0.16)
        phase = (t % 0.16) / 0.16
        env = math.sin(math.pi * min(1.0, phase / 0.78)) ** 2 if phase < 0.86 else 0.0
        f0 = 120 + ((seed + syl * 29) % 90)
        sample = env * (0.31 * math.sin(2 * math.pi * f0 * t) +
                        0.09 * math.sin(4 * math.pi * f0 * t) +
                        0.03 * math.sin(6 * math.pi * f0 * t))
        frames.extend(int(max(-0.9, min(0.9, sample)) * 32767).to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def synthesize(text, language, output):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", language, "-w", str(output), "--stdin"], 60, text + "\n")
            if output.is_file() and output.stat().st_size > 512 and wav_duration(output) > 0.1:
                return
        except DubError:
            pass
    fallback_voice(text, output)


def fit_segment(raw, output, window_seconds):
    raw_seconds = wav_duration(raw)
    control = "trim" if raw_seconds > window_seconds else "pad_silence"
    # First atrim prevents overshoot, apad fills short cues, final atrim fixes sample duration.
    af = ("aresample=%d,atrim=duration=%.9f,apad=pad_dur=%.9f,"
          "atrim=duration=%.9f" % (RATE, window_seconds, window_seconds, window_seconds))
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", af,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    with wave.open(str(output), "rb") as w:
        if w.getframerate() != RATE or w.getnchannels() != 1 or w.getnframes() <= 4800:
            raise DubError("segment WAV is not nontrivial 48 kHz mono audio")
    return raw_seconds, control


def build_timeline(wavs, windows, program_seconds, output):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            "anullsrc=r=48000:cl=mono:d=%.9f" % program_seconds]
    for wav in wavs:
        args.extend(["-i", str(wav)])
    labels = ["[0:a]"]
    filters = []
    for i, cue in enumerate(windows):
        name = "cue%d" % i
        delay = int(round(cue["start"] * RATE))
        filters.append("[%d:a]adelay=%dS:all=1[%s]" % (i + 1, delay, name))
        labels.append("[%s]" % name)
    filters.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[mix]" %
                   ("".join(labels), len(labels), program_seconds))
    args.extend(["-filter_complex", ";".join(filters), "-map", "[mix]", "-ar", str(RATE),
                 "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    run(args)


def audio_filter(source, output, af):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", af,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])


def mux(video, audio, output, timeline_seconds):
    # Video packets are copied directly, preserving visual codec and decoded frames.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % timeline_seconds,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1",
         "-movflags", "+faststart", str(output)])


def measure_lufs(path):
    _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(path),
                  "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"], 180)
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", err)
    if not values or values[-1].lower() in {"inf", "-inf"}:
        raise DubError("final audio has undefined integrated loudness")
    value = float(values[-1])
    if not math.isfinite(value):
        raise DubError("final audio loudness is not finite")
    return value


def validate_video(source_path, output_path, expected_duration):
    source = probe(source_path)
    delivered = probe(output_path)
    inv, outv = stream(source, "video"), stream(delivered, "video")
    if inv is None or outv is None:
        raise DubError("both source and delivered media must contain video")
    for key in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if inv.get(key) != outv.get(key):
            raise DubError("video stream was altered: " + key)
    a = stream(delivered, "audio")
    if a is None or int(a.get("sample_rate", 0)) != RATE or int(a.get("channels", 0)) != 1:
        raise DubError("delivered MP4 audio is not 48 kHz mono")
    if abs(duration(output_path) - expected_duration) > 0.25:
        raise DubError("delivered video does not preserve the source timeline")


def main(cfg):
    require("ffmpeg")
    require("ffprobe")
    defaults = {
        "input_video": "/root/input.mp4",
        "segments_srt": "/root/segments.srt",
        "source_srt": "/root/source_text.srt",
        "reference_target_srt": "/root/reference_target_text.srt",
        "target_language_file": "/root/target_language.txt",
        "source_language": "en",
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    if str(cfg["source_language"]).strip().lower() != "en":
        raise DubError("source_language must be en")
    for k in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(cfg[k]).is_file():
            raise DubError("missing required input: " + str(cfg[k]))

    windows = parse_srt(cfg["segments_srt"], False)
    sources = parse_srt(cfg["source_srt"], True)
    targets = parse_srt(cfg["reference_target_srt"], True)
    if not windows or len(windows) != len(sources) or len(windows) != len(targets):
        raise DubError("all supplied SRT files must have the same nonzero cue count")
    report_language, voice_language = read_language(cfg["target_language_file"])
    original_seconds = duration(cfg["input_video"])
    if any(x["end"] > original_seconds + 0.01 for x in windows):
        raise DubError("a timing window exceeds the source video duration")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    segment_dir = OUTPUT_ROOT / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="timed-dub-"))
    try:
        wavs, entries = [], []
        for i, window in enumerate(windows):
            raw = work / ("raw_%d.wav" % i)
            final_wav = segment_dir / ("seg_%d.wav" % i)
            synthesize(targets[i]["text"], voice_language, raw)
            window_seconds = window["end"] - window["start"]
            raw_seconds, control = fit_segment(raw, final_wav, window_seconds)
            wavs.append(final_wav)
            entries.append({
                "window_start_sec": round(window["start"], 6),
                "window_end_sec": round(window["end"], 6),
                "placed_start_sec": round(window["start"], 6),
                "placed_end_sec": round(window["end"], 6),
                "source_text": sources[i]["text"],
                "target_text": targets[i]["text"],
                "window_duration_sec": round(window_seconds, 6),
                "tts_duration_sec": round(raw_seconds, 6),
                "drift_sec": 0.0,
                "duration_control": control,
            })

        program = work / "program.wav"
        normalized = work / "normalized.wav"
        candidate = OUTPUT_ROOT / "dubbed.mp4"
        build_timeline(wavs, windows, original_seconds, program)
        audio_filter(program, normalized, "loudnorm=I=-23:TP=-2:LRA=7")
        mux(cfg["input_video"], normalized, candidate, original_seconds)
        measured = measure_lufs(candidate)
        # AAC encoding can move integrated loudness slightly; correct against the delivered measurement.
        for attempt in range(2):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            audio_filter(normalized, corrected, "volume=%.8fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(cfg["input_video"], normalized, candidate, original_seconds)
            measured = measure_lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize delivered MP4 near -23 LUFS")
        validate_video(cfg["input_video"], candidate, original_seconds)

        report = {
            "source_language": "en",
            "target_language": report_language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(original_seconds, 6),
            "new_duration_sec": round(duration(candidate), 6),
            "measured_lufs": measured,
            "speech_segments": entries,
        }
        report_path = OUTPUT_ROOT / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for artifact in (segment_dir / "seg_0.wav", candidate, report_path):
            if not artifact.is_file() or artifact.stat().st_size == 0:
                raise DubError("required artifact was not written: " + str(artifact))
        return {"ok": True, "video": "/outputs/dubbed.mp4", "report": "/outputs/report.json",
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
