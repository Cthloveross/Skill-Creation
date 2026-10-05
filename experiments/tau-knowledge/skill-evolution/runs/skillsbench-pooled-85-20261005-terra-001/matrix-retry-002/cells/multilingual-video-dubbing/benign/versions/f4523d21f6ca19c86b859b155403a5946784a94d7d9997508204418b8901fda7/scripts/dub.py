#!/usr/bin/env python3
"""Create timed dubbing artifacts. JSON object on stdin -> JSON object on stdout."""
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
TARGET = -23.0
LANG_NAMES = {
    "english": "en", "japanese": "ja", "french": "fr", "german": "de",
    "spanish": "es", "italian": "it", "portuguese": "pt", "korean": "ko",
    "chinese": "zh", "mandarin": "zh", "hindi": "hi", "russian": "ru",
    "arabic": "ar", "dutch": "nl", "polish": "pl", "turkish": "tr"
}
KOKORO_LANG = {"en": "a", "ja": "j", "zh": "z", "es": "e", "fr": "f", "hi": "h", "it": "i", "pt": "p"}
KOKORO_VOICE = {"en": "af_heart", "ja": "jf_alpha"}

class DubError(RuntimeError):
    pass

def command(args, capture=True):
    proc = subprocess.run(args, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE, text=True)
    if proc.returncode:
        raise DubError("command failed: %s\n%s" % (" ".join(map(str, args)), proc.stderr[-1800:]))
    return proc.stdout or "", proc.stderr or ""

def require(executable):
    if not shutil.which(executable):
        raise DubError("required executable is unavailable: " + executable)

def probe(path):
    out, _ = command(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)])
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for %s: %s" % (path, exc))

def duration(path, stream_type=None):
    info = probe(path)
    if stream_type:
        for stream in info.get("streams", []):
            if stream.get("codec_type") == stream_type:
                value = stream.get("duration")
                if value not in (None, "N/A"):
                    try:
                        value = float(value)
                        if value > 0:
                            return value
                    except ValueError:
                        pass
    value = info.get("format", {}).get("duration")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise DubError("no readable duration in " + str(path))
    if not math.isfinite(value) or value <= 0:
        raise DubError("nonpositive duration in " + str(path))
    return value

def parse_time(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    hour, minute, second, millisecond = map(int, match.groups())
    if minute >= 60 or second >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return hour * 3600 + minute * 60 + second + millisecond / 1000.0

def read_srt(path):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read %s: %s" % (path, exc))
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise DubError("empty SRT: " + str(path))
    entries = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.split("\n")]
        timing_at = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_at is None:
            raise DubError("SRT cue has no timing line in " + str(path))
        parts = lines[timing_at].split("-->")
        if len(parts) != 2:
            raise DubError("malformed SRT timing in " + str(path))
        start = parse_time(parts[0])
        end = parse_time(parts[1].split()[0])
        cue_text = "\n".join(line for line in lines[timing_at + 1:] if line).strip()
        if not cue_text or end <= start:
            raise DubError("empty or nonpositive SRT cue in " + str(path))
        entries.append({"start": start, "end": end, "text": cue_text})
    if not entries:
        raise DubError("no usable cues in " + str(path))
    return entries

def language_code(value):
    raw = value.strip().lower().replace("_", "-")
    if raw in LANG_NAMES:
        return LANG_NAMES[raw]
    if re.fullmatch(r"[a-z]{2}", raw):
        return raw
    if re.fullmatch(r"[a-z]{2}-[a-z]{2}", raw):
        return raw[:2]
    raise DubError("unsupported language declaration: " + value.strip())

def write_pcm16(path, samples, sample_rate):
    try:
        import numpy as np
    except ImportError as exc:
        raise DubError("Kokoro synthesis requires numpy: " + str(exc))
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=0 if audio.shape[0] <= 8 else 1)
    audio = np.clip(audio.reshape(-1), -1.0, 1.0)
    if audio.size == 0:
        raise DubError("TTS returned an empty waveform")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes((audio * 32767.0).astype("<i2").tobytes())

def synth_kokoro(text, lang, output, requested_voice):
    if lang not in KOKORO_LANG:
        raise DubError("Kokoro language configuration unavailable for " + lang)
    try:
        import numpy as np
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code=KOKORO_LANG[lang])
        voice = requested_voice or KOKORO_VOICE.get(lang, "af_heart")
        pieces = []
        for item in pipeline(text, voice=voice):
            # Kokoro generator tuples conventionally end with the waveform.
            pieces.append(np.asarray(item[-1], dtype=np.float32).reshape(-1))
        if not pieces:
            raise DubError("Kokoro returned no waveform")
        write_pcm16(output, np.concatenate(pieces), 24000)
    except DubError:
        raise
    except Exception as exc:
        raise DubError("Kokoro synthesis failed: " + str(exc))

def synth_espeak(text, lang, output):
    executable = shutil.which("espeak-ng") or shutil.which("espeak")
    if not executable:
        raise DubError("espeak-ng/espeak is unavailable")
    command([executable, "-v", lang, "-w", str(output), text])
    if not output.is_file() or duration(output, "audio") <= 0:
        raise DubError("espeak produced no usable audio")

def synth(text, lang, output, backend, voice):
    choices = [backend] if backend != "auto" else ["kokoro", "espeak"]
    errors = []
    for choice in choices:
        try:
            if choice == "kokoro":
                synth_kokoro(text, lang, output, voice)
            elif choice == "espeak":
                synth_espeak(text, lang, output)
            else:
                raise DubError("unknown tts_backend: " + choice)
            return choice
        except Exception as exc:
            errors.append(choice + ": " + str(exc))
            output.unlink(missing_ok=True)
    raise DubError("no local TTS backend succeeded; " + " | ".join(errors))

def atempo_chain(factor):
    filters = []
    while factor > 2.0 + 1e-9:
        filters.append("atempo=2")
        factor /= 2.0
    while factor < 0.5 - 1e-9:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append("atempo=%.9f" % factor)
    return ",".join(filters)

def render_clip(raw, output, raw_seconds, window_seconds):
    if raw_seconds <= window_seconds:
        control = "pad_silence"
        audio_filter = "aresample=48000,apad,atrim=duration=%.9f" % window_seconds
    elif raw_seconds / window_seconds <= 1.5:
        control = "rate_adjust"
        audio_filter = "aresample=48000,%s,apad,atrim=duration=%.9f" % (
            atempo_chain(raw_seconds / window_seconds), window_seconds)
    else:
        control = "trim"
        audio_filter = "aresample=48000,atrim=duration=%.9f" % window_seconds
    command(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", audio_filter,
             "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    return control

def loudnorm_measure(path):
    _, stderr = command(["ffmpeg", "-hide_banner", "-v", "info", "-i", str(path), "-af",
                         "loudnorm=I=-23:TP=-2:LRA=7:print_format=json", "-f", "null", "-"])
    matches = re.findall(r"\{\s*\"input_i\".*?\}", stderr, re.S)
    if not matches:
        raise DubError("ffmpeg loudnorm produced no measurement JSON")
    try:
        measured = json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        raise DubError("cannot parse loudnorm measurement: " + str(exc))
    required = ("input_i", "input_lra", "input_tp", "input_thresh", "target_offset")
    if any(key not in measured for key in required):
        raise DubError("incomplete loudnorm measurement")
    if str(measured["input_i"]).lower() in ("-inf", "inf"):
        raise DubError("audio has no measurable speech loudness")
    return measured

def normalize_final(source, output):
    measured = loudnorm_measure(source)
    filt = ("loudnorm=I=-23:TP=-2:LRA=7:measured_I={input_i}:measured_LRA={input_lra}:"
            "measured_TP={input_tp}:measured_thresh={input_thresh}:offset={target_offset}:"
            "linear=true:print_format=summary").format(**measured)
    command(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", filt,
             "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])

def final_lufs(video):
    _, stderr = command(["ffmpeg", "-hide_banner", "-v", "info", "-i", str(video), "-map", "0:a:0",
                         "-af", "ebur128=peak=true", "-f", "null", "-"])
    values = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not values or values[-1].lower() in ("-inf", "inf"):
        raise DubError("final MP4 audio has no measurable integrated loudness")
    return float(values[-1])

def main(cfg):
    for tool in ("ffmpeg", "ffprobe"):
        require(tool)
    defaults = {
        "input_video": "/root/input.mp4", "segments_srt": "/root/segments.srt",
        "source_srt": "/root/source_text.srt", "reference_target_srt": "/root/reference_target_text.srt",
        "target_language_file": "/root/target_language.txt", "output_dir": "/outputs"
    }
    for key, value in defaults.items():
        cfg.setdefault(key, value)
    for key in ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file"):
        if not Path(cfg[key]).is_file():
            raise DubError("required input is not a file: " + str(cfg[key]))
    windows = read_srt(cfg["segments_srt"])
    source_cues = read_srt(cfg["source_srt"])
    target_cues = read_srt(cfg["reference_target_srt"])
    if len(windows) != len(source_cues) or len(windows) != len(target_cues):
        raise DubError("timing, source, and target SRT files must have equal cue counts")
    target_raw = Path(cfg["target_language_file"]).read_text(encoding="utf-8-sig").strip()
    target = language_code(target_raw)
    if not re.fullmatch(r"[a-z]{2}", target_raw):
        raise DubError("target_language.txt must contain an ISO 639-1 language code")
    source = language_code(str(cfg.get("source_language", "en")))
    original_seconds = duration(cfg["input_video"], "video")
    for entry in windows:
        if entry["end"] > original_seconds + 0.010:
            raise DubError("a speech window exceeds input video duration")
    backend = cfg.get("tts_backend", "auto")
    if backend not in ("auto", "kokoro", "espeak"):
        raise DubError("tts_backend must be auto, kokoro, or espeak")
    out = Path(cfg["output_dir"])
    segment_dir = out / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="dubbing-", dir=str(out)))
    used = []
    report_segments = []
    try:
        for index, window in enumerate(windows):
            raw = temporary / ("raw-%d.wav" % index)
            rendered = segment_dir / ("seg_%d.wav" % index)
            used.append(synth(target_cues[index]["text"], target, raw, backend, cfg.get("kokoro_voice")))
            raw_seconds = duration(raw, "audio")
            win_seconds = window["end"] - window["start"]
            control = render_clip(raw, rendered, raw_seconds, win_seconds)
            report_segments.append({
                "window_start_sec": round(window["start"], 6),
                "window_end_sec": round(window["end"], 6),
                "placed_start_sec": round(window["start"], 6),
                "placed_end_sec": round(window["end"], 6),
                "source_text": source_cues[index]["text"],
                "target_text": target_cues[index]["text"],
                "window_duration_sec": round(win_seconds, 6),
                "tts_duration_sec": round(raw_seconds, 6),
                "drift_sec": 0.0,
                "duration_control": control
            })
        timeline = temporary / "timeline.wav"
        args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono"]
        for index in range(len(windows)):
            args.extend(["-i", str(segment_dir / ("seg_%d.wav" % index))])
        labels, clauses = [], []
        for index, window in enumerate(windows):
            label = "d%d" % index
            labels.append("[%s]" % label)
            clauses.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, round(window["start"] * RATE), label))
        clauses.append("[0:a]%samix=inputs=%d:duration=longest:normalize=0,atrim=duration=%.9f[a]" %
                       ("".join(labels), len(windows) + 1, original_seconds))
        args.extend(["-filter_complex", ";".join(clauses), "-map", "[a]", "-t", "%.9f" % original_seconds,
                     "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(timeline)])
        command(args)
        normalized = temporary / "normalized.wav"
        normalize_final(timeline, normalized)
        dubbed = out / "dubbed.mp4"
        command(["ffmpeg", "-y", "-v", "error", "-i", str(cfg["input_video"]), "-i", str(normalized),
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-ar", str(RATE),
                 "-ac", "1", "-shortest", "-movflags", "+faststart", str(dubbed)])
        info = probe(dubbed)
        audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
        if not audios or int(audios[0].get("sample_rate", 0)) != RATE or int(audios[0].get("channels", 0)) != 1:
            raise DubError("final MP4 is not 48 kHz mono")
        report = {
            "source_language": source,
            "target_language": target_raw,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(duration(cfg["input_video"]), 6),
            "new_duration_sec": round(duration(dubbed), 6),
            "measured_lufs": final_lufs(dubbed),
            "speech_segments": report_segments
        }
        report_path = out / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "video": str(dubbed), "report": str(report_path),
                "tts_backends_used": sorted(set(used))}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise DubError("stdin must be a JSON object")
        print(json.dumps(main(config), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
