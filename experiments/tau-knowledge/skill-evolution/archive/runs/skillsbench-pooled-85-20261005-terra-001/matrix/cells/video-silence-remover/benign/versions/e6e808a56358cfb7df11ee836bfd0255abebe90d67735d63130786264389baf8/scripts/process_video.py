#!/usr/bin/env python3
"""Create a synchronized, pause-compressed teaching video from JSON stdin."""
from __future__ import annotations

import array
import json
import math
import os
import re
import subprocess
import sys
from typing import Any

from media_common import MediaError, complement_intervals, decode_stream, normalize_intervals, probe, run, validate_report_data


def number(value: Any, default: float, name: str, low: float, high: float) -> float:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MediaError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise MediaError(f"{name} must be between {low} and {high}")
    return result


def decode_rms_activity(video: str, noise_db: float) -> list[bool]:
    """Return 0.25-second activity flags derived from decoded mono audio."""
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", video, "-map", "0:a:0",
        "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-",
    ]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(f"Unable to decode audio activity track: {exc}") from exc
    samples = array.array("f")
    samples.frombytes(completed.stdout)
    if not samples:
        raise MediaError("Audio stream decoded to no samples")
    # ffmpeg emits little-endian f32; supported runtime is little-endian Linux.
    if sys.byteorder != "little":
        samples.byteswap()
    window = 4000  # 0.25 seconds at 16 kHz
    flags: list[bool] = []
    for begin in range(0, len(samples), window):
        chunk = samples[begin:begin + window]
        if not chunk:
            continue
        mean_square = sum(float(x) * float(x) for x in chunk) / len(chunk)
        db = 20.0 * math.log10(max(math.sqrt(mean_square), 1e-12))
        flags.append(db > noise_db)
    return flags


def extract_static_flags(video: str, threshold: float) -> list[bool]:
    """Sample one small grayscale frame per second and flag low-change frames."""
    frame_size = 64 * 36
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", video, "-map", "0:v:0",
        "-an", "-vf", "fps=1,scale=64:36:flags=area,format=gray", "-f", "rawvideo", "-",
    ]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise MediaError("Unable to launch ffmpeg for visual analysis") from exc
    assert process.stdout is not None
    frames: list[bytes] = []
    try:
        while True:
            frame = process.stdout.read(frame_size)
            if not frame:
                break
            if len(frame) != frame_size:
                raise MediaError("Incomplete visual-analysis frame")
            frames.append(frame)
        status = process.wait(timeout=300)
    except Exception:
        process.kill()
        process.wait()
        raise
    if status != 0 or not frames:
        raise MediaError("Unable to decode video frames for opening analysis")
    flags = [True]
    prior = frames[0]
    for frame in frames[1:]:
        difference = sum(abs(a - b) for a, b in zip(frame, prior)) / frame_size
        flags.append(difference <= threshold)
        prior = frame
    return flags


def silence_intervals(video: str, noise_db: float, duration: float) -> list[tuple[float, float]]:
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-i", video, "-map", "0:a:0", "-vn",
        "-af", f"silencedetect=noise={noise_db:g}dB:d=0.1", "-f", "null", "-",
    ]
    result = run(command, timeout=300)
    starts: list[float] = []
    intervals: list[tuple[float, float]] = []
    for line in result.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([-+0-9.eE]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
            continue
        end_match = re.search(r"silence_end:\s*([-+0-9.eE]+)", line)
        if end_match and starts:
            intervals.append((starts.pop(0), float(end_match.group(1))))
    # A silence that reaches EOF has a start but no silence_end log line.
    intervals.extend((start, duration) for start in starts)
    return normalize_intervals(intervals, duration)


def find_opening_end(activity: list[bool], static: list[bool], confirmation: float) -> float:
    """Find a sustained onset, requiring evidence that material before it is opening-like."""
    step = 0.25
    width = max(4, int(math.ceil(confirmation / step)))
    if len(activity) < width:
        return 0.0
    for index in range(1, len(activity) - width + 1):
        future = activity[index:index + width]
        # Dense activity over a durable horizon avoids treating an isolated sound as onset.
        if sum(future) / len(future) < 0.65:
            continue
        before = activity[:index]
        quiet_fraction = 1.0 - (sum(before) / len(before))
        seconds_before = max(1, int(math.ceil(index * step)))
        visual = static[:min(seconds_before, len(static))]
        static_fraction = (sum(visual) / len(visual)) if visual else 0.0
        # Either quiet audio or a sustained static visual prefix supports opening status.
        if quiet_fraction >= 0.50 or static_fraction >= 0.75:
            return index * step
    return 0.0


def make_report(source_duration: float, output_duration: float, removed: list[tuple[float, float]]) -> dict[str, Any]:
    segments = [
        {"start": round(start, 6), "end": round(end, 6), "duration": round(end - start, 6)}
        for start, end in removed
    ]
    removed_duration = round(sum(item["duration"] for item in segments), 6)
    return {
        "original_duration_seconds": round(source_duration, 6),
        "compressed_duration_seconds": round(output_duration, 6),
        "removed_duration_seconds": removed_duration,
        "compression_percentage": round((removed_duration / source_duration * 100.0) if source_duration else 0.0, 6),
        "segments_removed": segments,
    }


def build_output(source: str, destination: str, keep: list[tuple[float, float]]) -> None:
    if not keep:
        raise MediaError("All media would be removed; refusing to create an empty teaching video")
    filters: list[str] = []
    inputs: list[str] = []
    for index, (start, end) in enumerate(keep):
        # Both stream trims use exactly the same serialized source-time boundaries.
        filters.append(f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]")
        filters.append(f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{index}]")
        inputs.extend([f"[v{index}]", f"[a{index}]"])
    filters.append("".join(inputs) + f"concat=n={len(keep)}:v=1:a=1[vout][aout]")
    command = [
        "ffmpeg", "-y", "-v", "error", "-nostdin", "-i", source,
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", destination,
    ]
    run(command, timeout=600)


def process(config: dict[str, Any]) -> dict[str, Any]:
    source = config.get("video_path")
    if not isinstance(source, str) or not source:
        raise MediaError("video_path is required")
    source = os.path.abspath(source)
    if not os.path.isfile(source):
        raise MediaError(f"Input video does not exist: {source}")
    output_dir = os.path.abspath(config.get("output_dir", os.getcwd()))
    os.makedirs(output_dir, exist_ok=True)
    min_pause = number(config.get("min_pause_seconds"), 2.0, "min_pause_seconds", 0.2, 120.0)
    noise_db = number(config.get("silence_noise_db"), -35.0, "silence_noise_db", -80.0, -5.0)
    confirmation = number(config.get("opening_confirmation_seconds"), 8.0, "opening_confirmation_seconds", 1.0, 60.0)
    guard = number(config.get("boundary_guard_seconds"), 0.08, "boundary_guard_seconds", 0.0, 1.0)
    static_threshold = number(config.get("static_difference_threshold"), 1.2, "static_difference_threshold", 0.0, 50.0)

    input_meta = probe(source)
    if not input_meta["has_video"] or not input_meta["has_audio"]:
        raise MediaError("Input must contain both video and audio streams")
    duration = input_meta["duration"]
    if duration <= 0:
        raise MediaError("Input has zero duration")

    activity = decode_rms_activity(source, noise_db)
    static = extract_static_flags(source, static_threshold)
    raw_silences = silence_intervals(source, noise_db, duration)
    onset = find_opening_end(activity, static, confirmation)

    proposed: list[tuple[float, float]] = []
    # Back off slightly from inferred onset so the first spoken sound is retained.
    if onset > guard:
        proposed.append((0.0, onset - guard))
    for start, end in raw_silences:
        if end - start < min_pause:
            continue
        start = max(start, onset)
        if end - start >= min_pause:
            # Preserve edges of a pause to avoid clipping a weak consonant or word boundary.
            inner_start, inner_end = start + guard, end - guard
            if inner_end > inner_start:
                proposed.append((inner_start, inner_end))
    removed = normalize_intervals(proposed, duration)
    keep = complement_intervals(removed, duration)

    output_video = os.path.join(output_dir, "compressed_video.mp4")
    report_path = os.path.join(output_dir, "compression_report.json")
    build_output(source, output_video, keep)
    output_meta = probe(output_video)
    if not output_meta["has_video"] or not output_meta["has_audio"]:
        raise MediaError("Encoded output does not contain both required streams")
    decode_stream(output_video, "0:v:0")
    decode_stream(output_video, "0:a:0")
    report = make_report(duration, output_meta["duration"], removed)
    errors = validate_report_data(report, duration, output_meta["duration"])
    if errors:
        raise MediaError("Post-encode validation failed: " + "; ".join(errors))
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return {
        "ok": True,
        "compressed_video": output_video,
        "compression_report": report_path,
        "opening_onset_candidate_seconds": round(onset, 6),
        "segments_removed": report["segments_removed"],
        "validation": {"ok": True, "errors": []},
    }


def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise MediaError("stdin must contain a JSON object")
        answer = process(config)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    main()
