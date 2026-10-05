#!/usr/bin/env python3
"""Create synchronized teaching-video silence removal artifacts from JSON stdin."""
from __future__ import annotations

import array
import json
import math
import os
import re
import subprocess
import sys
from typing import Any

from media_common import (MediaError, complement_intervals, decode_stream, normalize_intervals,
                          probe, run, timeline_audio_errors, validate_report_data)


def number(value: Any, default: float, name: str, low: float, high: float) -> float:
    if value is None:
        return default
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise MediaError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or not low <= value <= high:
        raise MediaError(f"{name} must be between {low} and {high}")
    return value


def activity_flags(video: str, noise_db: float) -> list[bool]:
    command = ["ffmpeg", "-v", "error", "-nostdin", "-i", video, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(f"Unable to decode audio activity track: {exc}") from exc
    samples = array.array("f")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise MediaError("Audio decoded to no samples")
    flags: list[bool] = []
    for begin in range(0, len(samples), 4000):
        chunk = samples[begin:begin + 4000]
        rms = math.sqrt(sum(float(v) * float(v) for v in chunk) / len(chunk))
        flags.append(20.0 * math.log10(max(rms, 1e-12)) > noise_db)
    return flags


def static_flags(video: str, threshold: float) -> list[bool]:
    size = 64 * 36
    command = ["ffmpeg", "-v", "error", "-nostdin", "-i", video, "-map", "0:v:0", "-an", "-vf", "fps=1,scale=64:36:flags=area,format=gray", "-f", "rawvideo", "-"]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise MediaError("Unable to start visual opening analysis") from exc
    assert process.stdout is not None
    frames: list[bytes] = []
    try:
        while True:
            frame = process.stdout.read(size)
            if not frame:
                break
            if len(frame) != size:
                raise MediaError("Incomplete video frame during opening analysis")
            frames.append(frame)
        if process.wait(timeout=300) != 0 or not frames:
            raise MediaError("Unable to decode video frames for opening analysis")
    except Exception:
        process.kill()
        process.wait()
        raise
    answer, previous = [True], frames[0]
    for frame in frames[1:]:
        difference = sum(abs(a - b) for a, b in zip(frame, previous)) / size
        answer.append(difference <= threshold)
        previous = frame
    return answer


def detect_silences(video: str, noise_db: float, duration: float) -> list[tuple[float, float]]:
    result = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", video, "-map", "0:a:0", "-vn", "-af", f"silencedetect=noise={noise_db:g}dB:d=0.1", "-f", "null", "-"], timeout=300)
    starts: list[float] = []
    found: list[tuple[float, float]] = []
    for line in result.stderr.splitlines():
        match = re.search(r"silence_start:\s*([-+0-9.eE]+)", line)
        if match:
            starts.append(float(match.group(1)))
            continue
        match = re.search(r"silence_end:\s*([-+0-9.eE]+)", line)
        if match and starts:
            found.append((starts.pop(0), float(match.group(1))))
    found.extend((start, duration) for start in starts)
    return normalize_intervals(found, duration)


def opening_end(activity: list[bool], static: list[bool], confirmation: float) -> float:
    width = max(4, int(math.ceil(confirmation / 0.25)))
    if len(activity) < width:
        return 0.0
    for index in range(1, len(activity) - width + 1):
        if sum(activity[index:index + width]) / width < 0.65:
            continue
        prefix = activity[:index]
        quiet_fraction = 1.0 - sum(prefix) / len(prefix)
        visual_count = min(len(static), max(1, int(math.ceil(index * 0.25))))
        static_fraction = sum(static[:visual_count]) / visual_count if visual_count else 0.0
        if quiet_fraction >= 0.50 or static_fraction >= 0.75:
            return index * 0.25
    return 0.0


def exact_serialized_intervals(output_dir: str, removed: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Round-trip the planned report representation before any media trimming."""
    plan = [{"start": start, "end": end, "duration": round(end - start, 6)} for start, end in removed]
    path = os.path.join(output_dir, ".removal_plan.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"segments_removed": plan}, handle)
    try:
        with open(path, encoding="utf-8") as handle:
            reread = json.load(handle)["segments_removed"]
        return [(float(item["start"]), float(item["end"])) for item in reread]
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def build_output(source: str, destination: str, keep: list[tuple[float, float]]) -> None:
    if not keep:
        raise MediaError("All media would be removed; refusing to make an empty output")
    filters: list[str] = []
    video_inputs: list[str] = []
    audio_inputs: list[str] = []
    for index, (start, end) in enumerate(keep):
        filters.append(f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]")
        filters.append(f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{index}]")
        video_inputs.append(f"[v{index}]")
        audio_inputs.append(f"[a{index}]")
    # Separate concat nodes are essential: combined A/V concat can extend each audio
    # segment to its video duration, introducing cumulative audio drift at many joins.
    filters.append("".join(video_inputs) + f"concat=n={len(keep)}:v=1:a=0[vout]")
    filters.append("".join(audio_inputs) + f"concat=n={len(keep)}:v=0:a=1[aout]")
    run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", source, "-filter_complex", ";".join(filters),
         "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", destination], timeout=600)


def make_report(source_duration: float, output_duration: float, removed: list[tuple[float, float]]) -> dict[str, Any]:
    segments = [{"start": start, "end": end, "duration": round(end - start, 6)} for start, end in removed]
    removed_duration = round(sum(item["duration"] for item in segments), 6)
    return {"original_duration_seconds": round(source_duration, 6),
            "compressed_duration_seconds": round(output_duration, 6),
            "removed_duration_seconds": removed_duration,
            "compression_percentage": round(100.0 * removed_duration / source_duration if source_duration else 0.0, 6),
            "segments_removed": segments}


def process(config: dict[str, Any]) -> dict[str, Any]:
    source = config.get("video_path")
    if not isinstance(source, str) or not source:
        raise MediaError("video_path is required")
    source = os.path.abspath(source)
    if not os.path.isfile(source):
        raise MediaError(f"Input video does not exist: {source}")
    output_dir = os.path.abspath(config.get("output_dir", os.getcwd()))
    os.makedirs(output_dir, exist_ok=True)
    minimum = number(config.get("min_pause_seconds"), 2.0, "min_pause_seconds", 0.2, 120.0)
    noise = number(config.get("silence_noise_db"), -35.0, "silence_noise_db", -80.0, -5.0)
    confirmation = number(config.get("opening_confirmation_seconds"), 8.0, "opening_confirmation_seconds", 1.0, 60.0)
    guard = number(config.get("boundary_guard_seconds"), 0.08, "boundary_guard_seconds", 0.0, 1.0)
    threshold = number(config.get("static_difference_threshold"), 1.2, "static_difference_threshold", 0.0, 50.0)
    source_meta = probe(source)
    if not source_meta["has_video"] or not source_meta["has_audio"] or source_meta["duration"] <= 0:
        raise MediaError("Input must be a nonempty audiovisual video")
    duration = source_meta["duration"]
    onset = opening_end(activity_flags(source, noise), static_flags(source, threshold), confirmation)
    proposed: list[tuple[float, float]] = []
    if onset > guard:
        proposed.append((0.0, onset - guard))
    for start, end in detect_silences(source, noise, duration):
        start = max(start, onset)
        if end - start >= minimum and end - guard > start + guard:
            proposed.append((start + guard, end - guard))
    detected = normalize_intervals(proposed, duration)
    removed = exact_serialized_intervals(output_dir, detected)
    keep = complement_intervals(removed, duration)
    output_video = os.path.join(output_dir, "compressed_video.mp4")
    report_path = os.path.join(output_dir, "compression_report.json")
    build_output(source, output_video, keep)
    output_meta = probe(output_video)
    if not output_meta["has_video"] or not output_meta["has_audio"]:
        raise MediaError("Output is missing an audio or video stream")
    decode_stream(output_video, "0:v:0")
    decode_stream(output_video, "0:a:0")
    report = make_report(duration, output_meta["duration"], removed)
    errors = validate_report_data(report, duration, output_meta["duration"])
    errors.extend(timeline_audio_errors(source, output_video, removed, duration, output_meta["duration"]))
    if errors:
        raise MediaError("Post-encode validation failed: " + "; ".join(errors))
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return {"ok": True, "compressed_video": output_video, "compression_report": report_path,
            "opening_onset_candidate_seconds": round(onset, 6), "segments_removed": report["segments_removed"],
            "validation": {"ok": True, "errors": []}}


def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise MediaError("stdin must contain a JSON object")
        result = process(config)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
