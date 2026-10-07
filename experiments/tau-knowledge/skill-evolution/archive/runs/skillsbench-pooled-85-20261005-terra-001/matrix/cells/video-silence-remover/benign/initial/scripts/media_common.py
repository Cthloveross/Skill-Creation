#!/usr/bin/env python3
"""Standard-library helpers for probing, validating, and normalizing media intervals."""
from __future__ import annotations

import json
import math
import os
import subprocess
from typing import Any, Iterable


class MediaError(RuntimeError):
    pass


def run(command: list[str], *, timeout: float | None = None, capture: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MediaError(f"Required executable is unavailable: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"Command timed out: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise MediaError(f"Command failed ({command[0]}): {detail[-1200:]}") from exc


def probe(path: str) -> dict[str, Any]:
    result = run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", path,
    ], timeout=90)
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError(f"Unable to obtain a finite container duration from {path}") from exc
    if not math.isfinite(duration) or duration < 0:
        raise MediaError(f"Invalid duration reported for {path}: {duration!r}")
    streams = data.get("streams", [])
    return {
        "duration": duration,
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "streams": streams,
    }


def normalize_intervals(intervals: Iterable[tuple[float, float]], duration: float, *, epsilon: float = 1e-6) -> list[tuple[float, float]]:
    """Clamp, sort, discard empty intervals, and merge touching intervals."""
    cleaned: list[tuple[float, float]] = []
    for start, end in intervals:
        if not (math.isfinite(start) and math.isfinite(end)):
            continue
        start = max(0.0, min(duration, float(start)))
        end = max(0.0, min(duration, float(end)))
        if end - start > epsilon:
            cleaned.append((start, end))
    cleaned.sort()
    merged: list[list[float]] = []
    for start, end in cleaned:
        if merged and start <= merged[-1][1] + epsilon:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(a, 6), round(b, 6)) for a, b in merged]


def complement_intervals(removed: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in removed:
        if start > cursor + 1e-6:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor + 1e-6:
        keep.append((cursor, duration))
    return keep


def decode_stream(path: str, stream_specifier: str) -> None:
    """Fully decode one stream to detect corrupt output and missing stream maps."""
    run([
        "ffmpeg", "-v", "error", "-nostdin", "-i", path,
        "-map", stream_specifier, "-f", "null", "-",
    ], timeout=300, capture=True)


def validate_report_data(report: dict[str, Any], input_duration: float, output_duration: float) -> list[str]:
    errors: list[str] = []
    required = [
        "original_duration_seconds", "compressed_duration_seconds",
        "removed_duration_seconds", "compression_percentage", "segments_removed",
    ]
    for key in required:
        if key not in report:
            errors.append(f"missing report field: {key}")
    if errors:
        return errors
    try:
        original = float(report["original_duration_seconds"])
        compressed = float(report["compressed_duration_seconds"])
        removed = float(report["removed_duration_seconds"])
        percentage = float(report["compression_percentage"])
    except (TypeError, ValueError):
        return ["top-level duration and percentage fields must be numeric"]
    if any(not math.isfinite(x) for x in (original, compressed, removed, percentage)):
        errors.append("top-level numeric values must be finite")
    if abs(original - input_duration) > 0.25:
        errors.append("original_duration_seconds does not match input media duration")
    if abs(compressed - output_duration) > 0.25:
        errors.append("compressed_duration_seconds does not match output media duration")
    total = 0.0
    previous_end = 0.0
    segments = report["segments_removed"]
    if not isinstance(segments, list):
        return errors + ["segments_removed must be a list"]
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            errors.append(f"segment {index} is not an object")
            continue
        try:
            start, end, declared = float(segment["start"]), float(segment["end"]), float(segment["duration"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"segment {index} lacks numeric start/end/duration")
            continue
        if not all(math.isfinite(v) for v in (start, end, declared)):
            errors.append(f"segment {index} has non-finite values")
            continue
        if start < -1e-6 or end > input_duration + 1e-6 or end <= start:
            errors.append(f"segment {index} is outside input bounds or empty")
        if start < previous_end - 1e-6:
            errors.append(f"segment {index} overlaps or is out of order")
        if abs((end - start) - declared) > 0.002:
            errors.append(f"segment {index} duration is inconsistent")
        previous_end = max(previous_end, end)
        total += max(0.0, end - start)
    if abs(total - removed) > 0.02:
        errors.append("removed_duration_seconds does not equal segment durations")
    expected_pct = (removed / original * 100.0) if original > 0 else 0.0
    if abs(expected_pct - percentage) > 0.02:
        errors.append("compression_percentage is inconsistent with durations")
    # AAC frame rounding and container timestamps can produce a small offset.
    if abs(original - (compressed + removed)) > max(0.35, original * 0.002):
        errors.append("input duration is not approximately compressed plus removed duration")
    return errors
