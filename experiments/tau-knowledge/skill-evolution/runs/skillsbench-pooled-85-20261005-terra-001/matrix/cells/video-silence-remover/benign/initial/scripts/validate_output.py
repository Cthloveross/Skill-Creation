#!/usr/bin/env python3
"""Validate a silence-removal report and its corresponding produced MP4."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from media_common import MediaError, decode_stream, probe, validate_report_data


def validate(config: dict[str, Any]) -> dict[str, Any]:
    input_path = config.get("input_video")
    output_path = config.get("output_video")
    report_path = config.get("report")
    if not all(isinstance(value, str) and value for value in (input_path, output_path, report_path)):
        raise MediaError("input_video, output_video, and report are required string paths")
    if not all(os.path.isfile(value) for value in (input_path, output_path, report_path)):
        raise MediaError("input video, output video, and report must all exist")
    source = probe(input_path)
    output = probe(output_path)
    errors: list[str] = []
    if not source["has_video"] or not source["has_audio"]:
        errors.append("input is missing a required audio or video stream")
    if not output["has_video"] or not output["has_audio"]:
        errors.append("output is missing a required audio or video stream")
    try:
        with open(report_path, encoding="utf-8") as handle:
            report = json.load(handle)
        if not isinstance(report, dict):
            errors.append("report root is not an object")
        else:
            errors.extend(validate_report_data(report, source["duration"], output["duration"]))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read JSON report: {exc}")
    if not errors:
        try:
            decode_stream(output_path, "0:v:0")
            decode_stream(output_path, "0:a:0")
        except MediaError as exc:
            errors.append(str(exc))
    return {
        "ok": not errors,
        "errors": errors,
        "input_duration_seconds": source["duration"],
        "output_duration_seconds": output["duration"],
        "output_has_video": output["has_video"],
        "output_has_audio": output["has_audio"],
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise MediaError("stdin must contain a JSON object")
        answer = validate(data)
    except Exception as exc:
        answer = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(answer, indent=2))
    if not answer["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
