#!/usr/bin/env python3
"""Validate an existing compressed MP4 and source-time removal report."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from media_common import (MediaError, decode_stream, intervals_from_report, probe,
                          timeline_audio_errors, validate_report_data)


def validate(config: dict[str, Any]) -> dict[str, Any]:
    source_path = config.get("input_video")
    output_path = config.get("output_video")
    report_path = config.get("report")
    if not all(isinstance(item, str) and item for item in (source_path, output_path, report_path)):
        raise MediaError("input_video, output_video, and report are required string paths")
    if not all(os.path.isfile(item) for item in (source_path, output_path, report_path)):
        raise MediaError("input video, output video, and report must exist")
    source, output = probe(source_path), probe(output_path)
    errors: list[str] = []
    if not source["has_audio"] or not source["has_video"]:
        errors.append("input lacks an audio or video stream")
    if not output["has_audio"] or not output["has_video"]:
        errors.append("output lacks an audio or video stream")
    report: dict[str, Any] | None = None
    try:
        with open(report_path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            errors.append("report root is not an object")
        else:
            report = loaded
            errors.extend(validate_report_data(report, source["duration"], output["duration"]))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read report: {exc}")
    if not errors:
        try:
            decode_stream(output_path, "0:v:0")
            decode_stream(output_path, "0:a:0")
            assert report is not None
            errors.extend(timeline_audio_errors(source_path, output_path, intervals_from_report(report), source["duration"], output["duration"]))
        except MediaError as exc:
            errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "input_duration_seconds": source["duration"],
            "output_duration_seconds": output["duration"], "output_has_video": output["has_video"],
            "output_has_audio": output["has_audio"]}


def main() -> None:
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise MediaError("stdin must contain a JSON object")
        answer = validate(config)
    except Exception as exc:
        answer = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(answer, indent=2))
    if not answer["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
