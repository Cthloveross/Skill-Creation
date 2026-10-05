#!/usr/bin/env python3
"""Validate and atomically write a tutorial chapter-index JSON artifact.

JSON stdin:
{
 "video_title":"required string", "duration_seconds":123.0,
 "titles":["exact supplied title", ...], "times":[0, 12.5, ...],
 "output_path":"/required/tutorial_index.json"
}
On success writes output_path and emits a JSON success summary. On any invariant
failure it emits a JSON error and does not replace the target file.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    raise SystemExit(2)


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(f"{name} must be a finite numeric value")
    return value


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid input JSON: {exc}")
    if not isinstance(data, dict):
        fail("input must be a JSON object")
    title = data.get("video_title")
    output_path = data.get("output_path")
    titles = data.get("titles")
    times = data.get("times")
    if not isinstance(title, str):
        fail("video_title must be a string")
    if not isinstance(output_path, str) or not output_path:
        fail("output_path must be a nonempty string")
    if not isinstance(titles, list) or not titles or not all(isinstance(x, str) for x in titles):
        fail("titles must be a nonempty array of strings")
    if not isinstance(times, list) or len(times) != len(titles):
        fail("times must be an array with exactly one item per title")
    duration = number(data.get("duration_seconds"), "duration_seconds")
    if duration < 0:
        fail("duration_seconds must be nonnegative")
    checked_times = [number(value, f"times[{i}]") for i, value in enumerate(times)]
    if checked_times[0] != 0:
        fail("the first chapter time must be exactly 0")
    previous = None
    for i, timestamp in enumerate(checked_times):
        if timestamp < 0 or timestamp > duration:
            fail(f"times[{i}] is outside [0, duration_seconds]")
        if previous is not None and timestamp <= previous:
            fail(f"times[{i}] must be strictly greater than times[{i - 1}]")
        previous = timestamp

    artifact = {"video_info": {"title": title, "duration_seconds": duration},
                "chapters": [{"time": timestamp, "title": chapter_title}
                             for timestamp, chapter_title in zip(checked_times, titles)]}
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(target.parent),
                                         prefix=".chapter-index-", suffix=".json", delete=False) as handle:
            json.dump(artifact, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_name = handle.name
        os.replace(temporary_name, target)
    except OSError as exc:
        try:
            os.unlink(temporary_name)
        except (OSError, UnboundLocalError):
            pass
        fail(f"could not write output_path: {exc}")
    print(json.dumps({"ok": True, "output_path": str(target), "chapter_count": len(titles),
                      "duration_seconds": duration}))


if __name__ == "__main__":
    main()
