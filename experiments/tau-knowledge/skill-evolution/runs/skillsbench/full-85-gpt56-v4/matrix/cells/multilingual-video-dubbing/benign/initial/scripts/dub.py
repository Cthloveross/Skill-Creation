#!/usr/bin/env python3
"""JSON-stdin multilingual dubbing entrypoint; emits one JSON object on stdout."""
import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VOICE = {
    "ar": "ar-SA-ZariyahNeural", "de": "de-DE-KatjaNeural",
    "en": "en-US-AriaNeural", "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural", "hi": "hi-IN-SwaraNeural",
    "it": "it-IT-ElsaNeural", "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural", "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural", "zh": "zh-CN-XiaoxiaoNeural",
}

def fail(message):
    raise RuntimeError(message)

def run(args, purpose):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        tail = (p.stderr or p.stdout)[-1500:].replace("\n", " ")
        fail(f"{purpose} failed: {tail}")
    return p.stdout, p.stderr

def require_tool(name):
    if not shutil.which(name):
        fail(f"Required executable is unavailable: {name}")

def parse_tc(value):
    m = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not m:
        fail(f"Invalid SRT timecode: {value!r}")
    h, minute, sec, ms = map(int, m.groups())
    return h * 3600 + minute * 60 + sec + ms / 1000.0

def parse_srt(path):
    raw = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    entries = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [x.strip() for x in block.split("\n")]
        if len(lines) < 3:
            continue
        time_at = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if time_at is None:
            continue
        bits = [x.strip() for x in lines[time_at].split("-->")]
        if len(bits) != 2:
            fail(f"Invalid SRT timing line in {path}: {lines[time_at]}")
        start, end = parse_tc(bits[0]), parse_tc(bits[1])
        text = " ".join(x for x in lines[time_at + 1:] if x).strip()
        if end <= start:
            fail(f"Non-positive subtitle window in {path}")
        entries.append({"start": start, "end": end, "text": text})
    if not entries:
        fail(f"No valid SRT entries found in {path}")
    return entries

def probe(path, selector=None, field="format=duration"):
    args = ["ffprobe", "-v", "error"]
    if selector:
        args += ["-select_streams", selector]
    args += ["-show_entries", field, "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    out, _ = run(args, f"ffprobe {path}")
    value = out.strip().splitlines()[0] if out.strip() else ""
    if not value or value == "N/A":
        fail(f"Could not read {field} from {path}")
    return value

def duration(path):
    return float(probe(path))

def stream_info(path, selector, fields):
    return probe(path, selector, "stream=" + ",".join(fields)).split("\n")

def ensure_edge_tts():
    try:
        import edge_tts  # noqa: F401
        return
    except ImportError:
        pass
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "edge-tts"], "Installing edge-tts")
    try:
        import edge_tts  # noqa: F401
    except ImportError as e:
        fail(f"edge-tts installation did not make the module available: {e}")

async def edge_save(text, voice, destination):
    import edge_tts
    await edge_tts.Communicate(text=text, voice=voice).save(destination)

def synthesize(text, lang, mp3):
    if not text:
        fail("Reference target SRT contains an empty speech entry")
    ensure_edge_tts()
    try:
        asyncio.run(edge_save(text, VOICE[lang], str(mp3)))
    except Exception as e:
        fail(f"Neural TTS synthesis failed for language {lang}: {e}")

def atempo_chain(ratio):
    # FFmpeg atempo permits each stage in [0.5, 2.0]. ratio is playback speed.
    if ratio <= 0 or not math.isfinite(ratio):
        fail("Invalid duration ratio")
    values = []
    while ratio > 2.0 + 1e-10:
        values.append(2.0); ratio /= 2.0
    while ratio < 0.5 - 1e-10:
        values.append(0.5); ratio /= 0.5
    values.append(ratio)
    return ",".join("atempo=%.10f" % x for x in values)

def ebur_lufs(path):
    _, err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], "LUFS measurement")
    hits = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS", err, flags=re.I)
    if not hits:
        fail("FFmpeg ebur128 did not report integrated loudness")
    value = float(hits[-1])
    if not math.isfinite(value):
        fail("Final audio has undefined integrated loudness")
    return value

def normalize_lufs(src, dst):
    # loudnorm followed by a measured correction gives a reportable final value.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
         "loudnorm=I=-23:LRA=7:TP=-2", "-ar", "48000", "-ac", "1", str(dst)], "Loudness normalization")
    for _ in range(2):
        current = ebur_lufs(dst)
        if abs(current + 23.0) <= 0.12:
            break
        corrected = str(dst) + ".corrected.wav"
        gain = -23.0 - current
        run(["ffmpeg", "-y", "-v", "error", "-i", str(dst), "-af", f"volume={gain:.5f}dB", "-ar", "48000", "-ac", "1", corrected], "LUFS correction")
        os.replace(corrected, dst)
    return ebur_lufs(dst)

def guess_source_language(entries):
    text = "".join(x["text"] for x in entries)
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text):
        return "ja" if re.search(r"[\u3040-\u30ff]", text) else "zh"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    return "en"

def main(config):
    for tool in ("ffmpeg", "ffprobe"):
        require_tool(tool)
    paths = {
        "input_video": config.get("input_video", "/root/input.mp4"),
        "segments_srt": config.get("segments_srt", "/root/segments.srt"),
        "source_srt": config.get("source_srt", "/root/source_text.srt"),
        "reference_srt": config.get("reference_srt", "/root/reference_target_text.srt"),
        "target_language_file": config.get("target_language_file", "/root/target_language.txt"),
    }
    for key, value in paths.items():
        if not Path(value).is_file():
            fail(f"Missing required {key}: {value}")
    target = Path(paths["target_language_file"]).read_text(encoding="utf-8").strip().lower()
    if not re.fullmatch(r"[a-z]{2}", target):
        fail("target_language.txt must contain one ISO 639-1 two-letter language code")
    if target not in VOICE:
        fail(f"No verified neural voice mapping is packaged for target language {target}")
    windows = parse_srt(paths["segments_srt"])
    sources = parse_srt(paths["source_srt"])
    refs = parse_srt(paths["reference_srt"])
    if len(sources) < len(windows) or len(refs) < len(windows):
        fail("Source/reference SRT has fewer entries than timing segments; cannot pair text safely")
    if len(sources) != len(windows) or len(refs) != len(windows):
        fail("SRT entry counts must match segments SRT to avoid ambiguous text pairing")
    outdir = Path(config.get("output_dir", "/outputs"))
    segdir = outdir / "tts_segments"
    segdir.mkdir(parents=True, exist_ok=True)
    input_duration = duration(paths["input_video"])
    source_language = str(config.get("source_language") or guess_source_language(sources)).strip().lower()
    if not re.fullmatch(r"[a-z]{2}", source_language):
        fail("source_language must be an ISO 639-1 two-letter code")
    work = Path(tempfile.mkdtemp(prefix="dubbing-"))
    report_segments = []
    fitted = []
    try:
        for index, win in enumerate(windows):
            if win["end"] > input_duration + 0.02:
                fail(f"Segment {index} ends beyond input video duration")
            raw_mp3, raw_wav = work / f"raw_{index}.mp3", work / f"raw_{index}.wav"
            fitted_wav, segment_out = work / f"fit_{index}.wav", segdir / f"seg_{index}.wav"
            synthesize(refs[index]["text"], target, raw_mp3)
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_mp3), "-ar", "48000", "-ac", "1", str(raw_wav)], "TTS decoding")
            raw_duration = duration(raw_wav)
            window_duration = win["end"] - win["start"]
            ratio = raw_duration / window_duration
            filt = atempo_chain(ratio) + f",atrim=duration={window_duration:.6f},asetpts=PTS-STARTPTS"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_wav), "-af", filt, "-ar", "48000", "-ac", "1", str(fitted_wav)], "Duration fitting")
            normalize_lufs(fitted_wav, segment_out)
            final_dur = duration(segment_out)
            if abs(final_dur - window_duration) > 0.010:
                fail(f"Segment {index} rendered duration differs from its window by over 10 ms")
            placed_end = win["start"] + window_duration
            fitted.append((segment_out, win["start"]))
            report_segments.append({
                "window_start_sec": round(win["start"], 3), "window_end_sec": round(win["end"], 3),
                "placed_start_sec": round(win["start"], 3), "placed_end_sec": round(placed_end, 3),
                "source_text": sources[index]["text"], "target_text": refs[index]["text"],
                "window_duration_sec": round(window_duration, 3), "tts_duration_sec": round(raw_duration, 3),
                "drift_sec": round(placed_end - win["end"], 6), "duration_control": "rate_adjust"
            })
        silent = work / "silence.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{input_duration:.6f}", str(silent)], "Silence timeline creation")
        args = ["ffmpeg", "-y", "-v", "error", "-i", str(silent)]
        for wav, _ in fitted:
            args += ["-i", str(wav)]
        labels = ["[0:a]"]
        clauses = []
        for n, (_, start) in enumerate(fitted, 1):
            delay = int(round(start * 1000))
            clauses.append(f"[{n}:a]adelay={delay}:all=1[a{n}]")
            labels.append(f"[a{n}]")
        clauses.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0[m]")
        mixed = work / "mixed.wav"
        args += ["-filter_complex", ";".join(clauses), "-map", "[m]", "-ar", "48000", "-ac", "1", str(mixed)]
        run(args, "Timeline mixing")
        final_wav = work / "final.wav"
        normalize_lufs(mixed, final_wav)
        dubbed = outdir / "dubbed.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-i", paths["input_video"], "-i", str(final_wav),
             "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac",
             "-ar", "48000", "-ac", "1", "-movflags", "+faststart", "-shortest", str(dubbed)], "Video muxing")
        # Validate final deliverable, then measure the muxed audio itself.
        sample_rate, channels = stream_info(dubbed, "a:0", ["sample_rate", "channels"])
        if int(sample_rate) != 48000 or int(channels) != 1:
            fail("Final MP4 audio is not 48000 Hz mono")
        in_codec = stream_info(paths["input_video"], "v:0", ["codec_name"])[0]
        out_codec = stream_info(dubbed, "v:0", ["codec_name"])[0]
        if in_codec != out_codec:
            fail("Final video codec differs from input; video stream was not preserved")
        measured = ebur_lufs(dubbed)
        report = {
            "source_language": source_language, "target_language": target,
            "audio_sample_rate_hz": 48000, "audio_channels": 1,
            "original_duration_sec": round(input_duration, 3), "new_duration_sec": round(duration(dubbed), 3),
            "measured_lufs": round(measured, 2), "speech_segments": report_segments
        }
        report_path = outdir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "outputs": {"dubbed": str(dubbed), "report": str(report_path), "segments_dir": str(segdir)}, "measured_lufs": report["measured_lufs"], "segment_count": len(report_segments)}
    finally:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            fail("stdin must contain a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
