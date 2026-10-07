#!/usr/bin/env python3
"""Validate a completed tutorial chapter index.

Reads JSON stdin:
{
  "index_path": str, "expected_titles": [str, ...], "duration_seconds": number,
  "expected_video_title": str (optional)
}
Writes {"ok": bool, "errors": [str], "chapter_count": int?} to stdout.
"""
import json
import os
import sys
from index_common import is_number, validate_index


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def main():
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        emit({"ok": False, "errors": [f"Invalid input JSON: {exc}"]})
        return
    path = request.get("index_path")
    titles = request.get("expected_titles")
    duration = request.get("duration_seconds")
    expected_title = request.get("expected_video_title")
    errors = []
    if not isinstance(path, str) or not path:
        errors.append("index_path must be a nonempty string")
    elif not os.path.isfile(path):
        errors.append(f"Index file does not exist: {path}")
    if not isinstance(titles, list) or not all(isinstance(x, str) for x in titles):
        errors.append("expected_titles must be an array of strings")
    if not is_number(duration) or duration < 0:
        errors.append("duration_seconds must be a nonnegative finite number")
    if expected_title is not None and not isinstance(expected_title, str):
        errors.append("expected_video_title must be a string when supplied")
    if errors:
        emit({"ok": False, "errors": errors})
        return
    try:
        with open(path, encoding="utf-8") as handle:
            index = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        emit({"ok": False, "errors": [f"Could not read index JSON: {exc}"]})
        return
    errors = validate_index(index, titles, duration, expected_title)
    result = {"ok": not errors, "errors": errors}
    if isinstance(index, dict) and isinstance(index.get("chapters"), list):
        result["chapter_count"] = len(index["chapters"])
    emit(result)


if __name__ == "__main__":
    main()
