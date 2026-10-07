#!/usr/bin/env python3
"""Validate delivered dub files and report without modifying them. JSON stdin -> JSON stdout."""
import json, re, shutil, subprocess, sys
from pathlib import Path

def run(a):
    return subprocess.run(a, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def lufs(video):
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"])
    x = re.findall(r"\bI:\s*(-?(?:\d+(?:\.\d*)?|inf))\s*LUFS", p.stderr, re.I)
    if not x or x[-1].lower() == "-inf": raise ValueError("no finite integrated loudness")
    return float(x[-1])

def main(c):
    errors = []
    for b in ("ffmpeg", "ffprobe"):
        if not shutil.which(b): errors.append(b + " unavailable")
    video, report_path = Path(c["video"]), Path(c["report"])
    if not video.is_file(): errors.append("missing video")
    if not report_path.is_file(): errors.append("missing report")
    if errors: return {"ok": False, "errors": errors}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    required = {"source_language", "target_language", "audio_sample_rate_hz", "audio_channels", "original_duration_sec", "new_duration_sec", "measured_lufs", "speech_segments"}
    errors += ["report missing " + k for k in required - set(report)]
    p = run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels", "-of", "json", str(video)])
    streams = json.loads(p.stdout).get("streams", [])
    if not streams: errors.append("MP4 has no audio stream")
    else:
        if int(streams[0].get("sample_rate", 0)) != 48000: errors.append("audio is not 48000 Hz")
        if int(streams[0].get("channels", 0)) != 1: errors.append("audio is not mono")
    segdir = Path(c.get("segment_dir", report_path.parent / "tts_segments"))
    for i, s in enumerate(report.get("speech_segments", [])):
        missing = {"window_start_sec", "window_end_sec", "placed_start_sec", "placed_end_sec", "drift_sec", "duration_control"} - set(s)
        errors += ["segment %d missing %s" % (i, x) for x in missing]
        if missing: continue
        if abs(float(s["placed_start_sec"]) - float(s["window_start_sec"])) > .010: errors.append("segment %d start misaligned" % i)
        expected = float(s["placed_end_sec"]) - float(s["window_end_sec"])
        if abs(expected - float(s["drift_sec"])) > .005: errors.append("segment %d drift inconsistent" % i)
        if abs(float(s["drift_sec"])) > .2: errors.append("segment %d drift exceeds 0.2 sec" % i)
        if s["duration_control"] not in ("rate_adjust", "pad_silence", "trim"): errors.append("invalid duration control")
        if not (segdir / ("seg_%d.wav" % i)).is_file(): errors.append("missing seg_%d.wav" % i)
    measured = None
    if not errors:
        try:
            measured = lufs(video)
            if abs(measured - float(report["measured_lufs"])) > .3: errors.append("report LUFS is not final-file measurement")
            if abs(measured + 23.0) > float(c.get("lufs_tolerance", 1.0)): errors.append("final loudness outside tolerance")
        except Exception as e: errors.append(str(e))
    return {"ok": not errors, "errors": errors, "measured_lufs": measured}
if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin))))
    except Exception as e:
        print(json.dumps({"ok": False, "errors": [str(e)]})); sys.exit(1)
