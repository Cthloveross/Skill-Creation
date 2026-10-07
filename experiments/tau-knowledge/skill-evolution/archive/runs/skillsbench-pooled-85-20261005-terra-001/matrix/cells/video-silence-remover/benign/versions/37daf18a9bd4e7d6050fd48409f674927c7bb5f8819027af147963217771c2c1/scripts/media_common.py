#!/usr/bin/env python3
"""Shared standard-library media, interval, and timeline validation helpers."""
from __future__ import annotations

import array
import json
import math
import subprocess
import sys
from typing import Any, Iterable


class MediaError(RuntimeError):
    pass


def run(command: list[str], *, timeout: float = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError as exc:
        raise MediaError(f"Required executable is unavailable: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"Command timed out: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise MediaError(f"Command failed ({command[0]}): {detail[-1200:]}") from exc


def probe(path: str) -> dict[str, Any]:
    result = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path], timeout=90)
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError(f"Unable to obtain container duration from {path}") from exc
    if not math.isfinite(duration) or duration < 0:
        raise MediaError(f"Invalid duration for {path}: {duration!r}")
    streams = data.get("streams", [])
    return {"duration": duration, "streams": streams,
            "has_video": any(s.get("codec_type") == "video" for s in streams),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def normalize_intervals(intervals: Iterable[tuple[float, float]], duration: float, epsilon: float = 1e-6) -> list[tuple[float, float]]:
    clean: list[tuple[float, float]] = []
    for start, end in intervals:
        if not (math.isfinite(start) and math.isfinite(end)):
            continue
        start, end = max(0.0, min(duration, float(start))), max(0.0, min(duration, float(end)))
        if end - start > epsilon:
            clean.append((start, end))
    clean.sort()
    merged: list[list[float]] = []
    for start, end in clean:
        if merged and start <= merged[-1][1] + epsilon:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(start, 6), round(end, 6)) for start, end in merged]


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


def decode_stream(path: str, specifier: str) -> None:
    run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", specifier, "-f", "null", "-"], timeout=300)


def validate_report_data(report: dict[str, Any], input_duration: float, output_duration: float) -> list[str]:
    required = ("original_duration_seconds", "compressed_duration_seconds", "removed_duration_seconds", "compression_percentage", "segments_removed")
    missing = [f"missing report field: {key}" for key in required if key not in report]
    if missing:
        return missing
    try:
        original = float(report["original_duration_seconds"])
        compressed = float(report["compressed_duration_seconds"])
        removed = float(report["removed_duration_seconds"])
        percentage = float(report["compression_percentage"])
    except (TypeError, ValueError):
        return ["top-level duration and percentage fields must be numeric"]
    errors: list[str] = []
    if not all(math.isfinite(x) for x in (original, compressed, removed, percentage)):
        errors.append("top-level numeric values must be finite")
    if abs(original - input_duration) > 0.25:
        errors.append("original_duration_seconds does not match input duration")
    if abs(compressed - output_duration) > 0.25:
        errors.append("compressed_duration_seconds does not match output duration")
    segments = report["segments_removed"]
    if not isinstance(segments, list):
        return errors + ["segments_removed must be a list"]
    total, previous_end = 0.0, 0.0
    for index, segment in enumerate(segments):
        try:
            start, end, declared = float(segment["start"]), float(segment["end"]), float(segment["duration"])
        except (TypeError, ValueError, KeyError, AttributeError):
            errors.append(f"segment {index} lacks numeric start/end/duration")
            continue
        if not all(math.isfinite(x) for x in (start, end, declared)):
            errors.append(f"segment {index} has non-finite values")
            continue
        if start < -1e-6 or end > input_duration + 1e-6 or end <= start:
            errors.append(f"segment {index} is invalid or outside source bounds")
        if start < previous_end - 1e-6:
            errors.append(f"segment {index} overlaps or is out of order")
        if abs((end - start) - declared) > 0.002:
            errors.append(f"segment {index} duration is inconsistent")
        previous_end, total = max(previous_end, end), total + max(0.0, end - start)
    if abs(total - removed) > 0.02:
        errors.append("removed_duration_seconds disagrees with segments")
    expected_percentage = 100.0 * removed / original if original > 0 else 0.0
    if abs(percentage - expected_percentage) > 0.02:
        errors.append("compression_percentage is inconsistent")
    if abs(original - compressed - removed) > max(0.35, original * 0.002):
        errors.append("source duration is not approximately compressed plus removed")
    return errors


def intervals_from_report(report: dict[str, Any]) -> list[tuple[float, float]]:
    return [(float(item["start"]), float(item["end"])) for item in report.get("segments_removed", [])]


def decode_pcm(path: str, start: float, length: float) -> list[int]:
    try:
        result = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{start:.6f}", "-i", path,
                                 "-t", f"{length:.6f}", "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(f"Unable to decode PCM for alignment validation: {exc}") from exc
    samples = array.array("h")
    samples.frombytes(result.stdout[:len(result.stdout) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    return list(samples)


def correlation(x: list[int], y: list[int]) -> float | None:
    n = min(len(x), len(y))
    if n < 4000:
        return None
    x, y = x[:n], y[:n]
    mx, my = sum(x) / n, sum(y) / n
    xx = sum((v - mx) ** 2 for v in x)
    yy = sum((v - my) ** 2 for v in y)
    if xx <= 1e6 or yy <= 1e6:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(xx * yy)


def timeline_audio_errors(source: str, output: str, removed: list[tuple[float, float]], source_duration: float, output_duration: float) -> list[str]:
    """Compare retained source excerpts to their report-implied output positions."""
    keeps = complement_intervals(removed, source_duration)
    candidates = sorted((item for item in keeps if item[1] - item[0] >= 4.0), key=lambda item: item[1] - item[0], reverse=True)[:2]
    checked = 0
    for begin, _end in candidates:
        source_time = begin + 0.75
        output_time = source_time - sum(max(0.0, min(source_time, end) - start) for start, end in removed if start < source_time)
        if output_time + 2.5 > output_duration:
            continue
        src, dst = decode_pcm(source, source_time, 2.5), decode_pcm(output, output_time, 2.5)
        best: float | None = None
        for lag in range(-960, 961, 160):
            value = correlation(src[lag:], dst) if lag >= 0 else correlation(src, dst[-lag:])
            if value is not None:
                best = value if best is None else max(best, value)
        if best is not None:
            checked += 1
            if best < 0.70:
                return [f"audio does not follow serialized keep timeline near source {source_time:.2f}s (correlation {best:.3f})"]
    return [] if checked else ["no non-silent retained audio excerpt was available for alignment validation"]
