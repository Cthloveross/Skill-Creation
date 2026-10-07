#!/usr/bin/env python3
"""Render a teaching-video cut list. JSON stdin -> JSON stdout.

Input: {input, output_dir, optional min_pause_seconds, silence_threshold_db,
        remove_intervals:[{start,end}]}
Output: {video, report, diagnostics, report_data}.
"""
import array
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path


def run(cmd, capture=True):
    p = subprocess.run(cmd, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE, check=False)
    if p.returncode:
        msg = p.stderr.decode("utf-8", "replace")[-4000:]
        raise RuntimeError("command failed: " + " ".join(cmd[:3]) + "\n" + msg)
    return p.stdout, p.stderr


def probe(path):
    out, _ = run(["ffprobe", "-v", "error", "-show_entries",
                  "format=duration:stream=codec_type,duration,start_time",
                  "-of", "json", str(path)])
    d = json.loads(out)
    try:
        duration = float(d["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("input/output has no finite container duration")
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("media duration must be finite and positive")
    kinds = [s.get("codec_type") for s in d.get("streams", [])]
    if "video" not in kinds or "audio" not in kinds:
        raise RuntimeError("this Skill requires at least one video and one audio stream")
    return duration, d


def percentile(values, q):
    if not values:
        return -60.0
    x = sorted(values)
    return x[min(len(x) - 1, max(0, int(q * (len(x) - 1))))]


def audio_windows(src, rate=8000, window=0.25):
    """Return window midpoint and RMS dBFS from a small PCM decode."""
    raw, _ = run(["ffmpeg", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
                  "-ar", str(rate), "-f", "s16le", "-"])
    a = array.array("h")
    a.frombytes(raw)
    if sys.byteorder != "little":
        a.byteswap()
    n = max(1, int(rate * window))
    result = []
    for pos in range(0, len(a), n):
        part = a[pos:pos + n]
        if not part:
            continue
        power = sum(int(v) * int(v) for v in part) / len(part)
        db = -100.0 if power <= 0 else 20.0 * math.log10(math.sqrt(power) / 32768.0)
        result.append((pos / rate + len(part) / (2 * rate), db))
    return result, window


def visual_motion(src):
    """One low-resolution luma frame per second; returns mean abs diffs."""
    width, height = 160, 90
    raw, _ = run(["ffmpeg", "-v", "error", "-i", str(src), "-an", "-vf",
                  "fps=1,scale=160:90:flags=fast", "-pix_fmt", "gray",
                  "-f", "rawvideo", "-"])
    size = width * height
    frames = [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]
    diffs = []
    for i in range(1, len(frames)):
        # sampled pixels retain a stable and inexpensive motion indicator
        p, q = frames[i - 1], frames[i]
        diffs.append(sum(abs(p[j] - q[j]) for j in range(0, size, 8)) / (size / 8))
    return diffs


def infer_opening(audio, win, threshold, motion, duration):
    """Conservative prefix rule; returns zero if initial static evidence is absent."""
    if len(audio) < 12 or not motion:
        return 0.0, {"reason": "insufficient_samples"}
    # Initial static video is an explicit prerequisite; threshold is generous for codec noise.
    first = motion[:min(len(motion), 8)]
    static_cut = max(2.0, percentile(motion, 0.20) + 1.5)
    initially_static = sum(v <= static_cut for v in first) >= max(2, len(first) * 0.7)
    if not initially_static:
        return 0.0, {"reason": "prefix_not_static", "static_cut": static_cut}
    active = [db > threshold + 3.0 for _, db in audio]
    # Need approximately 3 seconds of dense audio, or 3 seconds of strong visual change.
    width = max(4, int(round(3.0 / win)))
    onset = None
    for i in range(0, max(0, len(active) - width + 1)):
        audio_sustained = sum(active[i:i + width]) >= int(width * 0.75)
        sec = int(audio[i][0])
        visual_slice = motion[sec:min(len(motion), sec + 3)]
        visual_sustained = len(visual_slice) >= 3 and sum(v > static_cut * 1.8 for v in visual_slice) >= 2
        if (audio_sustained or visual_sustained) and audio[i][0] >= 2.0:
            onset = audio[i][0] - win / 2
            break
    if onset is None:
        return 0.0, {"reason": "no_sustained_transition", "static_cut": static_cut}
    # Avoid inventing a very long opening when a recording never meaningfully changes.
    onset = min(max(0.0, onset), duration)
    return onset, {"reason": "static_prefix_then_sustained_activity", "static_cut": static_cut}


def silence_candidates(src, threshold, minimum, duration):
    # FFmpeg reports source-time boundaries more accurately than coarse analysis windows.
    _, err = run(["ffmpeg", "-hide_banner", "-i", str(src), "-af",
                  "silencedetect=n={:.2f}dB:d={:.3f}".format(threshold, minimum),
                  "-f", "null", "-"])
    text = err.decode("utf-8", "replace")
    starts = [float(x) for x in re.findall(r"silence_start:\s*([-+0-9.eE]+)", text)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([-+0-9.eE]+)", text)]
    intervals = []
    ei = 0
    for start in starts:
        while ei < len(ends) and ends[ei] < start:
            ei += 1
        end = ends[ei] if ei < len(ends) else duration
        if end - start + 1e-6 >= minimum:
            intervals.append((start, min(end, duration)))
        ei += 1
    return intervals


def normalize(intervals, duration):
    cleaned = []
    for s, e in intervals:
        s, e = max(0.0, float(s)), min(duration, float(e))
        if e - s > 0.001:
            cleaned.append((s, e))
    cleaned.sort()
    merged = []
    for s, e in cleaned:
        if merged and s <= merged[-1][1] + 0.001:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def complement(removed, duration):
    keep, cursor = [], 0.0
    for s, e in removed:
        if s - cursor > 0.001:
            keep.append((cursor, s))
        cursor = max(cursor, e)
    if duration - cursor > 0.001:
        keep.append((cursor, duration))
    return keep


def render(src, dest, keep):
    if not keep:
        raise RuntimeError("all media would be removed; refuse to produce an empty lesson")
    pieces = []
    labels = []
    for i, (s, e) in enumerate(keep):
        pieces.append("[0:v]trim=start={:.6f}:end={:.6f},setpts=PTS-STARTPTS[v{}]".format(s, e, i))
        pieces.append("[0:a]atrim=start={:.6f}:end={:.6f},asetpts=PTS-STARTPTS[a{}]".format(s, e, i))
        labels.append("[v{}][a{}]".format(i, i))
    graph = ";".join(pieces + ["{}concat=n={}:v=1:a=1[v][a]".format("".join(labels), len(keep))])
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", graph,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dest)])


def main():
    cfg = json.load(sys.stdin)
    src = Path(cfg["input"])
    outdir = Path(cfg["output_dir"])
    if not src.is_file():
        raise RuntimeError("input file does not exist: " + str(src))
    outdir.mkdir(parents=True, exist_ok=True)
    original, _ = probe(src)
    minimum = float(cfg.get("min_pause_seconds", 2.0))
    if not math.isfinite(minimum) or minimum <= 0:
        raise RuntimeError("min_pause_seconds must be positive")
    audio, win = audio_windows(src)
    levels = [x[1] for x in audio]
    automatic_threshold = min(-32.0, max(-45.0, percentile(levels, 0.10) + 5.0))
    threshold = float(cfg.get("silence_threshold_db", automatic_threshold))
    if not math.isfinite(threshold) or threshold > 0 or threshold < -100:
        raise RuntimeError("silence_threshold_db must be between -100 and 0")
    diagnostics = {"source": str(src), "original_duration_seconds": original,
                   "min_pause_seconds": minimum, "silence_threshold_db": threshold,
                   "automatic_threshold_db": automatic_threshold}
    manual = cfg.get("remove_intervals")
    if manual is not None:
        raw = [(x["start"], x["end"]) for x in manual]
        removed = normalize(raw, original)
        diagnostics["mode"] = "reviewed_manual_intervals"
        diagnostics["program_onset_seconds"] = None
    else:
        motion = visual_motion(src)
        onset, onset_info = infer_opening(audio, win, threshold, motion, original)
        candidates = silence_candidates(src, threshold, minimum, original)
        raw = ([] if onset <= 0.001 else [(0.0, onset)])
        raw.extend((max(s, onset), e) for s, e in candidates if e - max(s, onset) >= minimum)
        removed = normalize(raw, original)
        diagnostics.update({"mode": "automatic", "program_onset_seconds": onset,
                            "opening_inference": onset_info,
                            "audio_silence_candidates": [{"start": s, "end": e} for s, e in candidates],
                            "sampled_motion_frames": len(motion)})
    keep = complement(removed, original)
    video_path = outdir / "compressed_video.mp4"
    report_path = outdir / "compression_report.json"
    diag_path = outdir / "removal_diagnostics.json"
    render(src, video_path, keep)
    compressed, output_probe = probe(video_path)
    removed_total = sum(e - s for s, e in removed)
    expected_compressed = sum(e - s for s, e in keep)
    # A/V encoders may cause millisecond-level container rounding, not whole-cut drift.
    if abs(compressed - expected_compressed) > 0.20:
        raise RuntimeError("rendered duration does not correspond to serialized keep intervals")
    if abs((original - compressed) - removed_total) > 0.20:
        raise RuntimeError("media duration arithmetic is inconsistent after rendering")
    report = {
        "original_duration_seconds": round(original, 3),
        "compressed_duration_seconds": round(compressed, 3),
        "removed_duration_seconds": round(original - compressed, 3),
        "compression_percentage": round((original - compressed) * 100.0 / original, 3),
        "segments_removed": [{"start": round(s, 3), "end": round(e, 3),
                              "duration": round(e - s, 3)} for s, e in removed]
    }
    diagnostics.update({"serialized_removed_intervals": report["segments_removed"],
                        "keep_intervals": [{"start": round(s, 3), "end": round(e, 3)} for s, e in keep],
                        "expected_keep_duration_seconds": expected_compressed,
                        "rendered_duration_seconds": compressed,
                        "rendered_stream_types": [s.get("codec_type") for s in output_probe.get("streams", [])]})
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    diag_path.write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"video": str(video_path), "report": str(report_path),
                      "diagnostics": str(diag_path), "report_data": report}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
