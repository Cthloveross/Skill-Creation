#!/usr/bin/env python3
"""Timed dubbing entrypoint: JSON stdin -> JSON stdout."""
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RATE = 48000
TARGET_LUFS = -23.0


class DubError(RuntimeError):
    pass


def run(args, timeout=240):
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError("command timed out: " + " ".join(map(str, args))) from exc
    if proc.returncode != 0:
        raise DubError("command failed: %s\n%s" %
                       (" ".join(map(str, args)), proc.stderr[-1800:]))
    return proc.stdout, proc.stderr


def require_tool(name):
    if not shutil.which(name):
        raise DubError("required executable is unavailable: " + name)


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                  "-of", "json", str(path)])
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DubError("ffprobe returned invalid JSON for " + str(path)) from exc


def media_duration(path):
    info = probe(path)
    value = info.get("format", {}).get("duration")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DubError("no readable duration in " + str(path)) from exc
    if not math.isfinite(result) or result <= 0:
        raise DubError("nonpositive duration in " + str(path))
    return result


def audio_duration(path):
    info = probe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            try:
                result = float(stream.get("duration"))
                if math.isfinite(result) and result > 0:
                    return result
            except (TypeError, ValueError):
                pass
    return media_duration(path)


def timestamp(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not match:
        raise DubError("invalid SRT timestamp: " + value)
    hour, minute, second, milli = map(int, match.groups())
    if minute >= 60 or second >= 60:
        raise DubError("invalid SRT timestamp: " + value)
    return hour * 3600 + minute * 60 + second + milli / 1000.0


def read_srt(path):
    try:
        body = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DubError("cannot read %s: %s" % (path, exc)) from exc
    body = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not body:
        raise DubError("empty SRT: " + str(path))
    entries = []
    for block in re.split(r"\n\s*\n", body):
        lines = [line.strip() for line in block.split("\n")]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            raise DubError("SRT cue lacks timing in " + str(path))
        fields = lines[timing_index].split("-->")
        if len(fields) != 2:
            raise DubError("malformed SRT timing in " + str(path))
        start = timestamp(fields[0])
        end = timestamp(fields[1].split()[0])
        text = "\n".join(line for line in lines[timing_index + 1:] if line).strip()
        if end <= start or not text:
            raise DubError("empty or nonpositive cue in " + str(path))
        entries.append({"start": start, "end": end, "text": text})
    if not entries:
        raise DubError("no usable cues in " + str(path))
    return entries


def target_code(path):
    try:
        raw = Path(path).read_text(encoding="utf-8-sig").strip().lower()
    except OSError as exc:
        raise DubError("cannot read target language file: " + str(exc)) from exc
    if not re.fullmatch(r"[a-z]{2}", raw):
        raise DubError("target_language.txt must contain a two-letter ISO 639-1 code")
    return raw


def atempo_filters(factor):
    # ffmpeg atempo accepts factors in [0.5, 2]; chain filters for larger changes.
    filters = []
    while factor > 2.0 + 1e-8:
        filters.append("atempo=2")
        factor /= 2.0
    while factor < 0.5 - 1e-8:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append("atempo=%.9f" % factor)
    return ",".join(filters)


def synthesize(text, language, output):
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if not engine:
        raise DubError("espeak-ng or espeak is required for local target-language TTS")
    # Passing text as one argument preserves all reference-script characters.
    run([engine, "-v", language, "-w", str(output), text], timeout=120)
    if not output.is_file() or output.stat().st_size < 128 or audio_duration(output) <= 0:
        raise DubError("TTS did not produce usable audio for language " + language)


def render_segment(raw, output, raw_seconds, window_seconds):
    if raw_seconds <= window_seconds:
        control = "pad_silence"
        filt = "aresample=48000,apad,atrim=duration=%.9f" % window_seconds
    else:
        control = "rate_adjust"
        filt = "aresample=48000,%s,apad,atrim=duration=%.9f" % (
            atempo_filters(raw_seconds / window_seconds), window_seconds)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", filt,
         "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(output)])
    return control


def make_timeline(segments, windows, original_seconds, output):
    # The first finite anullsrc input fixes the full original-video timeline.
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", "%.9f" % original_seconds,
            "-i", "anullsrc=r=48000:cl=mono"]
    for segment in segments:
        args += ["-i", str(segment)]
    clauses = []
    labels = ["[0:a]"]
    for index, window in enumerate(windows):
        label = "s%d" % index
        delay_samples = int(round(window["start"] * RATE))
        clauses.append("[%d:a]adelay=%dS:all=1[%s]" % (index + 1, delay_samples, label))
        labels.append("[%s]" % label)
    clauses.append("%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[a]" %
                   ("".join(labels), len(labels), original_seconds))
    args += ["-filter_complex", ";".join(clauses), "-map", "[a]", "-ar", str(RATE),
             "-ac", "1", "-c:a", "pcm_s16le", str(output)]
    run(args)


def normalize_timeline(source, output):
    # A single loudnorm render is robust for short programs; final delivery is
    # subsequently measured and gain-corrected from the encoded MP4.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af",
         "loudnorm=I=-23:TP=-1:LRA=7:linear=true", "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(output)])


def mux(video, audio, output):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-ar", str(RATE), "-ac", "1", "-shortest", "-movflags", "+faststart", str(output)])


def measured_lufs(video):
    _, stderr = run(["ffmpeg", "-hide_banner", "-v", "info", "-i", str(video),
                     "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    readings = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", stderr)
    if not readings or readings[-1].lower() in {"inf", "-inf"}:
        raise DubError("final MP4 audio has no measurable integrated loudness")
    return float(readings[-1])


def gain_correct(audio, gain_db, output):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-af",
         "volume=%.6fdB" % gain_db, "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(output)])


def main(cfg):
    for tool in ("ffmpeg", "ffprobe"):
        require_tool(tool)
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
        cfg.setdefault(key, value)
    required = ("input_video", "segments_srt", "source_srt", "reference_target_srt", "target_language_file")
    for key in required:
        if not Path(cfg[key]).is_file():
            raise DubError("required input is not a file: " + str(cfg[key]))
    source_language = str(cfg["source_language"]).strip().lower()
    if source_language != "en":
        raise DubError("this task requires source_language en")
    language = target_code(cfg["target_language_file"])
    windows = read_srt(cfg["segments_srt"])
    source = read_srt(cfg["source_srt"])
    target = read_srt(cfg["reference_target_srt"])
    if not (len(windows) == len(source) == len(target)):
        raise DubError("segments, source, and reference SRTs must have equal cue counts")
    original_seconds = media_duration(cfg["input_video"])
    if any(cue["end"] > original_seconds + 0.01 for cue in windows):
        raise DubError("a speech window exceeds the input video duration")

    out = Path(cfg["output_dir"])
    segment_dir = out / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="dubbing-", dir=str(out)))
    try:
        rendered = []
        report_segments = []
        for index, window in enumerate(windows):
            raw = work / ("raw_%d.wav" % index)
            wav = segment_dir / ("seg_%d.wav" % index)
            synthesize(target[index]["text"], language, raw)
            raw_seconds = audio_duration(raw)
            window_seconds = window["end"] - window["start"]
            control = render_segment(raw, wav, raw_seconds, window_seconds)
            rendered.append(wav)
            report_segments.append({
                "window_start_sec": round(window["start"], 6),
                "window_end_sec": round(window["end"], 6),
                "placed_start_sec": round(window["start"], 6),
                "placed_end_sec": round(window["end"], 6),
                "source_text": source[index]["text"],
                "target_text": target[index]["text"],
                "window_duration_sec": round(window_seconds, 6),
                "tts_duration_sec": round(raw_seconds, 6),
                "drift_sec": 0.0,
                "duration_control": control,
            })

        timeline = work / "timeline.wav"
        normalized = work / "normalized.wav"
        candidate = work / "dubbed.mp4"
        make_timeline(rendered, windows, original_seconds, timeline)
        normalize_timeline(timeline, normalized)
        mux(cfg["input_video"], normalized, candidate)
        final_value = measured_lufs(candidate)
        # Codec and program-length gating can shift the first normalization.
        # Correct from the actually delivered MP4, then remeasure that final mux.
        if abs(final_value - TARGET_LUFS) > 0.20:
            corrected = work / "corrected.wav"
            gain_correct(normalized, TARGET_LUFS - final_value, corrected)
            mux(cfg["input_video"], corrected, candidate)
            final_value = measured_lufs(candidate)

        info = probe(candidate)
        audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
        video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        if audio is None or video is None:
            raise DubError("final MP4 lacks required video or audio stream")
        if int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
            raise DubError("final MP4 is not 48 kHz mono")
        if not -25.0 <= final_value <= -21.0:
            raise DubError("could not normalize final MP4 near -23 LUFS; measured %.2f" % final_value)

        delivered = out / "dubbed.mp4"
        shutil.copyfile(candidate, delivered)
        report = {
            "source_language": "en",
            "target_language": language,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(media_duration(cfg["input_video"]), 6),
            "new_duration_sec": round(media_duration(delivered), 6),
            "measured_lufs": final_value,
            "speech_segments": report_segments,
        }
        report_path = out / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "video": str(delivered), "report": str(report_path),
                "measured_lufs": final_value}
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise DubError("stdin must be a JSON object")
        print(json.dumps(main(config), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)
