#!/usr/bin/env python3
"""Build a validated tutorial chapter index from alignment data.

Reads JSON stdin:
{
  "output_path": str, "video_title": str, "duration_seconds": number,
  "chapters": [{"time": number, "title": str}, ...]
}
Writes JSON stdout. On success it writes output_path and returns
{"ok": true, "output_path": str, "chapter_count": int}; otherwise it returns
{"ok": false, "errors": [str]}.
"""
import json
import os
import sys
from index_common import is_number, validate_index


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        emit({"ok": False, "errors": [f"Invalid input JSON: {exc}"]})
        return
    output = data.get("output_path")
    title = data.get("video_title")
    duration = data.get("duration_seconds")
    chapters = data.get("chapters")
    errors = []
    if not isinstance(output, str) or not output:
        errors.append("output_path must be a nonempty string")
    if not isinstance(title, str):
        errors.append("video_title must be a string")
    if not is_number(duration) or duration < 0:
        errors.append("duration_seconds must be a nonnegative finite number")
    if not isinstance(chapters, list):
        errors.append("chapters must be an array")
    if errors:
        emit({"ok": False, "errors": errors})
        return
    index = {"video_info": {"title": title, "duration_seconds": duration}, "chapters": chapters}
    expected_titles = [x.get("title") if isinstance(x, dict) else None for x in chapters]
    errors = validate_index(index, expected_titles, duration, title)
    if errors:
        emit({"ok": False, "errors": errors})
        return
    directory = os.path.dirname(os.path.abspath(output))
    if not os.path.isdir(directory):
        emit({"ok": False, "errors": [f"Output directory does not exist: {directory}"]})
        return
    try:
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        emit({"ok": False, "errors": [f"Could not write output: {exc}"]})
        return
    emit({"ok": True, "output_path": output, "chapter_count": len(chapters)})


if __name__ == "__main__":
    main()
