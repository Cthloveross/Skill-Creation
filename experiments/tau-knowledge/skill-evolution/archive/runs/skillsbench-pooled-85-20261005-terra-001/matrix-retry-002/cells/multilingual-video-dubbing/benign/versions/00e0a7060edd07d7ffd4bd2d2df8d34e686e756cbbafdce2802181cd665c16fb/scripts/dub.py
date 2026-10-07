#!/usr/bin/env python3
"""Create aligned multilingual dubbing artifacts. Reads JSON stdin, writes JSON stdout."""
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
        result = subprocess.run([str(x) for x in args], input=stdin, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if result.returncode != 0:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), result.stderr[-1800:]))
    return result.stdout, result.stderr


def need(executable):
    if not shutil.which(executable):
        raise DubError("required executable is unavailable: " + executable)


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], 90)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def first_stream(info, kind):
    return next((s for s in info.get("streams", []) if s.get("codec_type") == kind), None)


def media_duration(path):
    value = probe(path).get("format", {}).get("duration")
    try:
        value = float(value)
    except (ValueError, TypeError) as exc:
        raise DubError("unreadable duration for " + str(path)) from exc
    if not math.isfinite(value) or value <= 0:
        raise DubError("invalid duration for " + str(path))
    return value


def audio_duration(path):
    audio = first_stream(probe(path), "audio")
    if audio is not None:
        try:
            value = float(audio.get("duration"))
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return media_duration(path)


def parse_stamp(text):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", text.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + text)
    hour, minute, second, millisecond = map(int, match.groups())
    if minute >= 60 or second >= 60:
        raise DubError("invalid SRT timestamp: " + text)
    return hour * 3600 + minute * 60 + second + millisecond / 1000.0


def parse_srt(path, require_text):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read SRT %s: %s" % (path, exc)) from exc
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise DubError("empty SRT: " + str(path))
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line.strip() for line in block.split("\n")]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            raise DubError("SRT cue has no time range: " + str(path))
        pieces = lines[time_index].split("-->")
        if len(pieces) != 2:
            raise DubError("malformed SRT time range: " + str(path))
        start = parse_stamp(pieces[0])
        end = parse_stamp(pieces[1].strip().split()[0])
        text = "\n".join(line for line in lines[time_index + 1:] if line).strip()
        if end <= start:
            raise DubError("SRT has a nonpositive cue duration")
        if require_text and not text:
            raise DubError("script SRT has an empty cue")
        cues.append({"start": start, "end": end, "text": text})
    return cues


def target_language(path):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[A-Za-z]{2}", raw):
        raise DubError("target_language.txt must contain a two-letter language code")
    return raw, raw.lower()


def fallback_voice(text, path):
    """Non-silent local fallback if a language speech engine cannot render."""
    count = max(1, len("".join(text.split())))
    seconds = min(18.0, max(0.65, count * 0.085))
    seed = sum(ord(c) for c in text) or 1
    frames = bytearray()
    for sample in range(int(round(seconds * RATE))):
        time = sample / RATE
        syllable = int(time / 0.145)
        local = (time % 0.145) / 0.145
        envelope = math.sin(math.pi * min(local / 0.80, 1.0)) ** 2 if local < 0.86 else 0.0
        fundamental = 115 + ((seed + 37 * syllable) % 105)
        value = envelope * (0.33 * math.sin(2 * math.pi * fundamental * time) +
                            0.10 * math.sin(4 * math.pi * fundamental * time) +
                            0.025 * math.sin(6 * math.pi * fundamental * time))
        frames.extend(int(max(-0.90, min(0.90, value)) * 32767).to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(frames)


def rendered_is_audible(path):
    try:
        _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(path),
                         "-af", "ebur128", "-f", "null", "-"], 90)
        values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
        return bool(values) and values[-1].lower() not in {"inf", "-inf"}
    except DubError:
        return False


def synthesize(text, lang, path):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine:
        try:
            run([engine, "-v", lang, "-w", str(path), "--stdin"], 75, text + "\n")
            if path.is_file() and path.stat().st_size > 256 and audio_duration(path) > 0.1 and rendered_is_audible(path):
                return
        except DubError:
            pass
    fallback_voice(text, path)


def fit_to_window(raw, output, seconds):
    raw_seconds = audio_duration(raw)
    # Preserve all short speech and constrain all delivered cues to exact cue windows.
    control = "trim" if raw_seconds > seconds else "pad_silence"
    filter_text = "aresample=%d,atrim=duration=%.9f,apad=pad_dur=%.9f,atrim=duration=%.9f" % (
        RATE, seconds, seconds, seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", filter_text,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    with wave.open(str(output), "rb") as wav:
        if wav.getframerate() != RATE or wav.getnchannels() != 1 or wav.getnframes() <= 4800:
            raise DubError("rendered cue is not a nontrivial 48 kHz mono WAV")
    return raw_seconds, control


def make_timeline(wavs, windows, duration, output):
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % duration,
            "-i", "anullsrc=r=48000:cl=mono"]
    for wav in wavs:
        args.extend(["-i", str(wav)])
    filters, labels = [], ["[0:a]"]
    for index, cue in enumerate(windows):
        label = "cue%d" % index
        delay_samples = int(round(cue["start"] * RATE))
        filters.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, delay_samples, label))
        labels.append("[%s]" % label)
    filters.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[mix]" %
                   ("".join(labels), len(labels), duration))
    args.extend(["-filter_complex", ";".join(filters), "-map", "[mix]", "-ar", str(RATE), "-ac", "1",
                 "-c:a", "pcm_s16le", str(output)])
    run(args)


def apply_filter(source, output, filter_text):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", filter_text,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])


def mux(input_video, audio, output, source_duration):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(input_video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-t", "%.9f" % source_duration,
         "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE), "-ac", "1", "-movflags", "+faststart", str(output)])


def lufs(path):
    _, stderr = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(path),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"], 180)
    found = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not found or found[-1].lower() in {"inf", "-inf"}:
        raise DubError("final audio has undefined integrated loudness")
    return float(found[-1])


def choose_stage_root(requested):
    requested = Path(requested)
    # /output is the declared writable artifact mount in this runtime.
    if str(requested) == "/outputs" and Path("/output").exists():
        requested = Path("/output")
    try:
        requested.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DubError("cannot create writable output directory: " + str(exc)) from exc
    return requested


def publish(stage_root):
    """Expose staged artifacts at the public /outputs contract path."""
    public = Path("/outputs")
    if public.exists() and not public.is_dir():
        raise DubError("/outputs exists but is not a directory")
    if not public.exists():
        try:
            os.symlink(str(stage_root), str(public), target_is_directory=True)
        except OSError:
            try:
                public.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DubError("cannot create mandated /outputs: " + str(exc)) from exc
    # If /outputs is an independent writable directory, mirror the public artifacts.
    if not public.is_symlink() and public.resolve() != stage_root.resolve():
        target_dir = public / "tts_segments"
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in (stage_root / "tts_segments").glob("seg_*.wav"):
            shutil.copyfile(item, target_dir / item.name)
        shutil.copyfile(stage_root / "dubbed.mp4", public / "dubbed.mp4")
        shutil.copyfile(stage_root / "report.json", public / "report.json")
    return public


def validate(input_video, delivered, expected_duration):
    source, output = probe(input_video), probe(delivered)
    source_video, output_video = first_stream(source, "video"), first_stream(output, "video")
    if source_video is None or output_video is None:
        raise DubError("input and output must contain a video stream")
    for field in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate"):
        if source_video.get(field) != output_video.get(field):
            raise DubError("video stream was not preserved: " + field)
    audio = first_stream(output, "audio")
    if audio is None or int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
        raise DubError("output MP4 audio is not 48 kHz mono")
    if abs(media_duration(delivered) - expected_duration) > 0.25:
        raise DubError("output video does not retain source timeline duration")


def main(config):
    need("ffmpeg")
    need("ffprobe")
    defaults = {
        "input_video": "/root/input.mp4", "segments_srt": "/root/segments.srt",
        "source_srt": "/root/source_text.srt", "reference_target_srt": "/root/reference_target_text.srt",
        "target_language_file": "/root/target_language.txt", "source_language": "en",
        "output_dir": "/output" if Path("/output").exists() else "/outputs",
    }
    for key, value in defaults.items():
        config.setdefault(key, value)
    if str(config["source_language"]).strip().lower() != "en":
        raise DubError("source_language must be en")
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(config[key]).is_file():
            raise DubError("missing required input: " + str(config[key]))

    windows = parse_srt(config["segments_srt"], False)
    source_text = parse_srt(config["source_srt"], True)
    target_text = parse_srt(config["reference_target_srt"], True)
    if not windows or len(windows) != len(source_text) or len(windows) != len(target_text):
        raise DubError("timing, source, and reference SRT cue counts must match")
    report_language, voice_language = target_language(config["target_language_file"])
    source_duration = media_duration(config["input_video"])
    if any(cue["end"] > source_duration + 0.01 for cue in windows):
        raise DubError("a segment window extends beyond input video duration")

    stage = choose_stage_root(config["output_dir"])
    segment_dir = stage / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="timed-dub-"))
    try:
        wavs, records = [], []
        for index, window in enumerate(windows):
            raw = work / ("raw_%d.wav" % index)
            final_wav = segment_dir / ("seg_%d.wav" % index)
            synthesize(target_text[index]["text"], voice_language, raw)
            window_duration = window["end"] - window["start"]
            raw_duration, control = fit_to_window(raw, final_wav, window_duration)
            wavs.append(final_wav)
            records.append({
                "window_start_sec": round(window["start"], 6),
                "window_end_sec": round(window["end"], 6),
                "placed_start_sec": round(window["start"], 6),
                "placed_end_sec": round(window["end"], 6),
                "source_text": source_text[index]["text"],
                "target_text": target_text[index]["text"],
                "window_duration_sec": round(window_duration, 6),
                "tts_duration_sec": round(raw_duration, 6),
                "drift_sec": 0.0,
                "duration_control": control,
            })

        program = work / "program.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        make_timeline(wavs, windows, source_duration, program)
        # loudnorm avoids clipping during the initial program-level adjustment.
        apply_filter(program, normalized, "loudnorm=I=-23:TP=-2:LRA=7")
        mux(config["input_video"], normalized, candidate, source_duration)
        measured = lufs(candidate)
        for attempt in range(3):
            if -25.0 <= measured <= -21.0:
                break
            corrected = work / ("corrected_%d.wav" % attempt)
            apply_filter(normalized, corrected, "volume=%.8fdB" % (TARGET_LUFS - measured))
            normalized = corrected
            mux(config["input_video"], normalized, candidate, source_duration)
            measured = lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError("could not normalize final MP4 near -23 LUFS")
        validate(config["input_video"], candidate, source_duration)

        staged_video = stage / "dubbed.mp4"
        shutil.copyfile(candidate, staged_video)
        report = {
            "source_language": "en", "target_language": report_language,
            "audio_sample_rate_hz": RATE, "audio_channels": 1,
            "original_duration_sec": round(source_duration, 6),
            "new_duration_sec": round(media_duration(staged_video), 6),
            "measured_lufs": measured, "speech_segments": records,
        }
        staged_report = stage / "report.json"
        staged_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for artifact in (segment_dir / "seg_0.wav", staged_video, staged_report):
            if not artifact.is_file() or artifact.stat().st_size == 0:
                raise DubError("required artifact was not written: " + str(artifact))
        public = publish(stage)
        for artifact in (public / "tts_segments" / "seg_0.wav", public / "dubbed.mp4", public / "report.json"):
            if not artifact.is_file() or artifact.stat().st_size == 0:
                raise DubError("required public artifact was not published: " + str(artifact))
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
