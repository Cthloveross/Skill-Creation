#!/usr/bin/env python3
"""Detect declared fillers from word timings and stitch their media clips.

Reads one JSON object from stdin and writes one JSON result to stdout.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from filler_core import coerce_words, detect_fillers


def load_json_path(path_value: Any) -> Any:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("transcript_path must be a nonempty path string")
    with open(path_value, "r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_word_array(transcript: Any) -> list[Any]:
    """Accept common word-timestamp containers without using segment timings."""
    if isinstance(transcript, list):
        return transcript
    if not isinstance(transcript, dict):
        raise ValueError("transcript JSON must be an array or object containing words")
    if isinstance(transcript.get("words"), list):
        return transcript["words"]
    segments = transcript.get("segments")
    if isinstance(segments, list):
        result: list[Any] = []
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
                raise ValueError(
                    f"segment {index} has no words array; segment timestamps cannot substitute for word timings"
                )
            result.extend(segment["words"])
        return result
    raise ValueError("could not find a word-level words array in transcript JSON")


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def probe_media(path: str, ffprobe: str) -> dict[str, Any]:
    result = run_checked([
        ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
        "-of", "json", path,
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    try:
        metadata = json.loads(result.stdout)
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ffprobe returned no usable duration for {path}") from exc
    if not math.isfinite(duration) or duration < 0:
        raise RuntimeError(f"invalid media duration from ffprobe: {duration}")
    stream_types = {stream.get("codec_type") for stream in metadata.get("streams", [])}
    return {"duration": duration, "stream_types": stream_types}


def atomic_write_json(path_value: str, payload: Any) -> None:
    target = Path(path_value)
    if not target.parent.exists():
        raise ValueError(f"parent directory does not exist: {target.parent}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".json", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def make_filter(intervals: list[dict[str, Any]]) -> str:
    pieces: list[str] = []
    inputs: list[str] = []
    for index, interval in enumerate(intervals):
        start = interval["clip_start"]
        end = interval["clip_end"]
        pieces.append(
            f"[0:v]trim=start={start:.9f}:end={end:.9f},setpts=PTS-STARTPTS[v{index}]"
        )
        pieces.append(
            f"[0:a]atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS[a{index}]"
        )
        inputs.append(f"[v{index}][a{index}]")
    pieces.append("".join(inputs) + f"concat=n={len(intervals)}:v=1:a=1[vout][aout]")
    return ";".join(pieces)


def stitch(video_path: str, output_path: str, intervals: list[dict[str, Any]], config: dict[str, Any]) -> None:
    output = Path(output_path)
    if not output.parent.exists():
        raise ValueError(f"parent directory does not exist: {output.parent}")
    # Preserve an MP4 extension so ffmpeg selects the intended muxer for the temporary artifact.
    temporary = output.parent / f".{output.stem}.partial.mp4"
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    command = [
        str(config.get("ffmpeg", "ffmpeg")), "-y", "-v", "error", "-i", video_path,
        "-filter_complex", make_filter(intervals), "-map", "[vout]", "-map", "[aout]",
        "-c:v", str(config.get("video_codec", "libx264")), "-pix_fmt", "yuv420p",
        "-c:a", str(config.get("audio_codec", "aac")), "-movflags", "+faststart", str(temporary),
    ]
    result = run_checked(command)
    if result.returncode != 0:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeError(f"ffmpeg clip concat failed: {result.stderr.strip()}")
    os.replace(temporary, output)


def require_path(config: dict[str, Any], name: str) -> str:
    value = config.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required and must be a nonempty path string")
    return value


def main(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("stdin must contain a JSON object")
    has_words = "words" in config
    has_path = "transcript_path" in config
    if has_words == has_path:
        raise ValueError("provide exactly one of words or transcript_path")
    raw_transcript = config["words"] if has_words else load_json_path(config["transcript_path"])
    words = coerce_words(extract_word_array(raw_transcript))
    matches = detect_fillers(words)

    video_path = require_path(config, "video_path")
    annotations_path = require_path(config, "annotations_path")
    output_path = require_path(config, "output_path")
    ffprobe = str(config.get("ffprobe", "ffprobe"))
    source = probe_media(video_path, ffprobe)
    if not {"video", "audio"}.issubset(source["stream_types"]):
        raise RuntimeError("source must contain both video and audio streams for synchronized clip output")

    try:
        padding = float(config.get("clip_padding_seconds", 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("clip_padding_seconds must be numeric") from exc
    if not math.isfinite(padding) or padding < 0:
        raise ValueError("clip_padding_seconds must be finite and nonnegative")

    intervals: list[dict[str, Any]] = []
    for match in matches:
        clip_start = max(0.0, match["start"] - padding)
        clip_end = min(source["duration"], match["end"] + padding)
        if clip_end <= clip_start:
            continue
        intervals.append({**match, "clip_start": clip_start, "clip_end": clip_end})
    if matches and not intervals:
        raise RuntimeError("all detected intervals were outside source duration")
    if not intervals:
        # The task-facing file truthfully records the empty detection result; an empty
        # MP4 would not be a valid stitched set of filler clips, so do not invent one.
        atomic_write_json(annotations_path, [])
        raise RuntimeError("no declared fillers detected; no clip video can be produced")

    expected = sum(item["clip_end"] - item["clip_start"] for item in intervals)
    stitch(video_path, output_path, intervals, config)
    output = probe_media(output_path, ffprobe)
    if not {"video", "audio"}.issubset(output["stream_types"]):
        raise RuntimeError("output validation failed: missing audio or video stream")
    try:
        tolerance = float(config.get("duration_tolerance_seconds", 0.75))
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_tolerance_seconds must be numeric") from exc
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("duration_tolerance_seconds must be finite and nonnegative")
    if abs(output["duration"] - expected) > tolerance:
        raise RuntimeError(
            f"output duration {output['duration']:.6f} differs from interval sum {expected:.6f} beyond tolerance {tolerance}"
        )

    # Write task-facing annotations only after the synchronized media artifact passes validation.
    annotations = [{"word": item["word"], "timestamp": item["timestamp"]} for item in intervals]
    atomic_write_json(annotations_path, annotations)
    detailed_path = config.get("detailed_intervals_path")
    if detailed_path is not None:
        if not isinstance(detailed_path, str) or not detailed_path:
            raise ValueError("detailed_intervals_path must be a nonempty path string when supplied")
        atomic_write_json(detailed_path, intervals)
    return {
        "ok": True,
        "annotation_count": len(annotations),
        "interval_count": len(intervals),
        "input_duration": source["duration"],
        "expected_clip_duration": expected,
        "output_duration": output["duration"],
        "annotations_path": annotations_path,
        "output_path": output_path,
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        response = main(request)
        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, separators=(",", ":")))
        sys.exit(2)
