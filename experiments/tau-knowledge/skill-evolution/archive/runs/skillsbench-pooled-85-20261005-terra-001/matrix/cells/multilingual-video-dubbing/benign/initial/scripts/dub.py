#!/usr/bin/env python3
"""Build a timed, normalized dialogue dub. JSON stdin -> JSON stdout."""
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RATE = 48000
TARGET_LUFS = -23.0


def run(args, *, text=False):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=text)
    if p.returncode:
        err = p.stderr if text else p.stderr.decode("utf-8", "replace")
        raise RuntimeError("command failed (%s): %s" % (" ".join(map(str, args)), err[-1600:]))
    return p.stdout, p.stderr


def ffprobe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_entries",
                  "format=duration:stream=index,codec_type,sample_rate,channels,duration",
                  "-of", "json", str(path)], text=True)
    return json.loads(out)


def duration_of(path):
    data = ffprobe(path)
    try:
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("could not determine duration for %s" % path)


def parse_time(value):
    m = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not m:
        raise ValueError("invalid SRT timestamp: " + value)
    h, minute, sec, ms = map(int, m.groups())
    if minute >= 60 or sec >= 60:
        raise ValueError("invalid SRT clock value: " + value)
    return h * 3600 + minute * 60 + sec + ms / 1000.0


def parse_srt(path):
    """Return [{start,end,text}] while preserving multiline dialogue."""
    raw = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    result = []
    for block in re.split(r"\n[ \t]*\n", raw.strip()):
        lines = [x.strip() for x in block.split("\n")]
        if len(lines) < 2:
            continue
        time_i = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_i is None:
            raise ValueError("SRT entry has no timing line in " + str(path))
        pair = lines[time_i].split("-->")
        if len(pair) != 2:
            raise ValueError("invalid SRT range in " + str(path))
        start, end = parse_time(pair[0]), parse_time(pair[1].split()[0])
        text = "\n".join(x for x in lines[time_i + 1:] if x).strip()
        if not text:
            raise ValueError("empty dialogue entry in " + str(path))
        result.append({"start": start, "end": end, "text": text})
    if not result:
        raise ValueError("no SRT entries in " + str(path))
    return result


def language_from_text(text):
    # SRT does not encode language. This is only a safe default for omitted input.
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    return "en"


def checked_iso(code, label):
    code = code.strip().lower()
    if not re.fullmatch(r"[a-z]{2}", code):
        raise ValueError("%s must be an ISO 639-1 two-letter code" % label)
    return code


def atempo_chain(tempo):
    """ffmpeg atempo accepts 0.5..2 per filter; compose arbitrary positive tempo."""
    if tempo <= 0 or not math.isfinite(tempo):
        raise ValueError("invalid tempo")
    values = []
    while tempo > 2.0 + 1e-10:
        values.append(2.0)
        tempo /= 2.0
    while tempo < 0.5 - 1e-10:
        values.append(0.5)
        tempo /= 0.5
    values.append(tempo)
    return ",".join("atempo=%.10f" % x for x in values)


def measure_lufs(path):
    # ebur128 summary is emitted on stderr. Last integrated value is the summary.
    _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                  "-filter:a", "ebur128=peak=true", "-f", "null", "-"], text=True)
    vals = re.findall(r"\bI:\s*([-+]?\d+(?:\.\d+)?)\s*LUFS", err)
    if not vals:
        raise RuntimeError("ffmpeg ebur128 did not report integrated LUFS for " + str(path))
    value = float(vals[-1])
    if not math.isfinite(value) or value <= -69.0:
        raise RuntimeError("audio is silent or not BS.1770 measurable: " + str(path))
    return value


def volume_adjust(src, dst, gain_db):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:a:0",
         "-af", "volume=%.8fdB" % gain_db, "-ar", str(RATE), "-ac", "1",
         "-c:a", "pcm_s16le", str(dst)])


def normalize_to_target(src, dst):
    """Measured gain correction; repeat once because gated integrated loudness rounds."""
    first = measure_lufs(src)
    temporary = str(dst) + ".first.wav"
    volume_adjust(src, temporary, TARGET_LUFS - first)
    second = measure_lufs(temporary)
    volume_adjust(temporary, dst, TARGET_LUFS - second)
    Path(temporary).unlink(missing_ok=True)
    return measure_lufs(dst)


def synthesize(text, lang, output, template):
    if template:
        if not isinstance(template, str):
            raise ValueError("tts_command must be a command-template string")
        try:
            command = shlex.split(template.format(text=text, output=str(output), lang=lang))
        except KeyError as e:
            raise ValueError("unknown tts_command placeholder: %s" % e)
        if not command:
            raise ValueError("empty tts_command")
        run(command, text=True)
    else:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise RuntimeError("no tts_command supplied and neither espeak-ng nor espeak is installed")
        run([exe, "-v", lang, "-w", str(output), text], text=True)
    if not Path(output).is_file() or Path(output).stat().st_size == 0:
        raise RuntimeError("TTS did not create WAV output " + str(output))


def mux(video, audio, output):
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-ar", str(RATE), "-ac", "1", "-movflags", "+faststart", str(output)])


def main(config):
    video = Path(config.get("input_video", "/root/input.mp4"))
    segments_path = Path(config.get("segments_srt", "/root/segments.srt"))
    source_path = Path(config.get("source_srt", "/root/source_text.srt"))
    target_path = Path(config.get("reference_target_srt", "/root/reference_target_text.srt"))
    target_language_path = Path(config.get("target_language_file", "/root/target_language.txt"))
    outdir = Path(config.get("output_dir", "/outputs"))
    for required in (video, segments_path, source_path, target_path, target_language_path):
        if not required.is_file():
            raise FileNotFoundError("missing required input: " + str(required))

    target_lang = checked_iso(target_language_path.read_text(encoding="utf-8-sig"), "target language")
    windows, sources, targets = parse_srt(segments_path), parse_srt(source_path), parse_srt(target_path)
    if len(sources) < len(windows) or len(targets) < len(windows):
        raise ValueError("source and reference target SRTs must each contain at least as many entries as segments")
    for i, item in enumerate(windows):
        if item["end"] <= item["start"]:
            raise ValueError("nonpositive segment window at index %d" % i)
        if i and item["start"] < windows[i - 1]["start"]:
            raise ValueError("segments must be time ordered")

    requested_source = config.get("source_language", "auto")
    source_lang = language_from_text(sources[0]["text"]) if requested_source == "auto" else checked_iso(requested_source, "source language")
    video_duration = duration_of(video)
    if video_duration <= 0:
        raise RuntimeError("input video has no positive duration")
    for item in windows:
        if item["end"] > video_duration + 0.010:
            raise ValueError("segment window exceeds input video duration")

    outdir.mkdir(parents=True, exist_ok=True)
    segment_dir = outdir / "tts_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="dub-", dir=str(outdir)))
    template = config.get("tts_command")
    fitted = []
    report_segments = []
    try:
        for i, window in enumerate(windows):
            raw = temp / ("raw_%d.wav" % i)
            synthesize(targets[i]["text"], target_lang, raw, template)
            raw_duration = duration_of(raw)
            samples = max(1, int(round((window["end"] - window["start"]) * RATE)))
            fitted_un = temp / ("fit_%d.wav" % i)
            if raw_duration < samples / RATE - 1.0 / RATE:
                control = "pad_silence"
                af = "aresample=%d, aformat=channel_layouts=mono, apad=whole_len=%d, atrim=end_sample=%d, asetpts=N/SR/TB" % (RATE, samples, samples)
            else:
                control = "rate_adjust"
                tempo = raw_duration / (samples / RATE)
                af = "aresample=%d, aformat=channel_layouts=mono, %s, apad=whole_len=%d, atrim=end_sample=%d, asetpts=N/SR/TB" % (RATE, atempo_chain(tempo), samples, samples)
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-map", "0:a:0", "-af", af,
                 "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(fitted_un)])
            seg_out = segment_dir / ("seg_%d.wav" % i)
            normalize_to_target(fitted_un, seg_out)
            actual_samples = int(round(duration_of(seg_out) * RATE))
            placed_start = window["start"]
            placed_end = placed_start + actual_samples / RATE
            drift = placed_end - window["end"]
            fitted.append((seg_out, int(round(placed_start * RATE))))
            report_segments.append({
                "window_start_sec": round(window["start"], 6),
                "window_end_sec": round(window["end"], 6),
                "placed_start_sec": round(placed_start, 6),
                "placed_end_sec": round(placed_end, 6),
                "source_text": sources[i]["text"],
                "target_text": targets[i]["text"],
                "window_duration_sec": round(window["end"] - window["start"], 6),
                "tts_duration_sec": round(raw_duration, 6),
                "drift_sec": round(drift, 6),
                "duration_control": control
            })

        # Construct the timeline from sample-positioned inputs, never encoded bytes.
        args = ["ffmpeg", "-y", "-v", "error"]
        for wav, _ in fitted:
            args += ["-i", str(wav)]
        labels = []
        filters = []
        for i, (_, start_samples) in enumerate(fitted):
            label = "d%d" % i
            filters.append("[%d:a]adelay=%dS[%s]" % (i, start_samples, label))
            labels.append("[%s]" % label)
        final_samples = max(1, int(math.floor(video_duration * RATE)))
        filters.append("%samix=inputs=%d:duration=longest:normalize=0,apad=whole_len=%d,atrim=end_sample=%d,asetpts=N/SR/TB[m]" % ("".join(labels), len(labels), final_samples, final_samples))
        mixed = temp / "mixed.wav"
        args += ["-filter_complex", ";".join(filters), "-map", "[m]", "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(mixed)]
        run(args)

        normalized = temp / "program.wav"
        normalize_to_target(mixed, normalized)
        dubbed = outdir / "dubbed.mp4"
        mux(video, normalized, dubbed)
        # Measure the delivered AAC stream and correct one more time if necessary.
        delivered_lufs = measure_lufs(dubbed)
        if abs(delivered_lufs - TARGET_LUFS) > 0.05:
            corrected = temp / "program_corrected.wav"
            volume_adjust(normalized, corrected, TARGET_LUFS - delivered_lufs)
            mux(video, corrected, dubbed)
            delivered_lufs = measure_lufs(dubbed)

        probe = ffprobe(dubbed)
        audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
        video_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
        if not audio_streams or not video_streams:
            raise RuntimeError("delivered MP4 does not contain both video and audio")
        audio = audio_streams[0]
        if int(audio.get("sample_rate", 0)) != RATE or int(audio.get("channels", 0)) != 1:
            raise RuntimeError("delivered audio is not 48000 Hz mono")
        if any(abs(x["placed_start_sec"] - x["window_start_sec"]) > 0.010 for x in report_segments):
            raise RuntimeError("placement-start validation failed")
        if any(abs(x["drift_sec"]) > 0.2 for x in report_segments):
            raise RuntimeError("drift validation failed")
        new_duration = duration_of(dubbed)
        report = {
            "source_language": source_lang,
            "target_language": target_lang,
            "audio_sample_rate_hz": RATE,
            "audio_channels": 1,
            "original_duration_sec": round(video_duration, 6),
            "new_duration_sec": round(new_duration, 6),
            "measured_lufs": round(delivered_lufs, 3),
            "speech_segments": report_segments
        }
        report_path = outdir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "report": str(report_path), "dubbed_video": str(dubbed),
                "segment_audio": str(segment_dir / "seg_0.wav"),
                "validation": {"audio_sample_rate_hz": RATE, "audio_channels": 1,
                               "measured_lufs": round(delivered_lufs, 3),
                               "max_abs_drift_sec": round(max(abs(x["drift_sec"]) for x in report_segments), 6)}}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("stdin must contain a JSON object")
        print(json.dumps(main(supplied), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
