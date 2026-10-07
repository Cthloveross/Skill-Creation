#!/usr/bin/env python3
"""Independent validator for a longest event-time session Flink result.

JSON is read from stdin and JSON is emitted to stdout. Required input fields:
  task_input, job_input, task_schema, job_schema

Schema objects require timestamp_column, job_id_column, event_type_column, plus
submit_value for task_schema and finish_values (a list) for job_schema. Optional:
  output: an output file or a Flink output directory to compare
  gap_microseconds: positive integer; default 600000000
  include_finished_without_submits: boolean; default false

The program reads plain CSV and .gz CSV. It intentionally does not deduplicate
rows. Invalid CSV rows or fields are skipped and reported in diagnostics.
"""
import csv
import gzip
import json
import os
import re
import sys
from collections import defaultdict

TUPLE_RE = re.compile(r"^\s*\(\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\)\s*$")


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def as_int(value, label):
    text = str(value).strip()
    if not text:
        raise ValueError(label + " is empty")
    # Trace CSV integer fields are normally unadorned. Accept integral decimal
    # renderings as well, but reject fractional values rather than truncating.
    if re.match(r"^[+-]?\d+$", text):
        return int(text)
    if re.match(r"^[+-]?\d+\.0+$", text):
        return int(text.split(".", 1)[0])
    raise ValueError(label + " is not an integer: " + repr(text))


def checked_schema(value, name, need_submit=False, need_finish=False):
    if not isinstance(value, dict):
        raise ValueError(name + " must be an object")
    result = {}
    for key in ("timestamp_column", "job_id_column", "event_type_column"):
        if key not in value:
            raise ValueError(name + " missing " + key)
        result[key] = as_int(value[key], name + "." + key)
        if result[key] < 0:
            raise ValueError(name + "." + key + " must be non-negative")
    if need_submit:
        if "submit_value" not in value:
            raise ValueError(name + " missing submit_value")
        result["submit_value"] = str(value["submit_value"]).strip()
    if need_finish:
        values = value.get("finish_values")
        if not isinstance(values, list) or not values:
            raise ValueError(name + ".finish_values must be a nonempty list")
        result["finish_values"] = {str(x).strip() for x in values}
    return result


def open_csv(path):
    if path.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, "rt", encoding="utf-8", newline="")


def rows(path):
    with open_csv(path) as handle:
        for number, row in enumerate(csv.reader(handle), 1):
            yield number, row


def get_field(row, index, source, line):
    if index >= len(row):
        raise ValueError("%s line %d has %d columns, needs column %d" %
                         (source, line, len(row), index))
    return row[index].strip()


def parse_inputs(task_path, job_path, task_schema, job_schema):
    submits = defaultdict(list)
    completed = set()
    diagnostics = {
        "task_rows": 0, "task_submit_rows": 0, "task_invalid_rows": 0,
        "job_rows": 0, "job_finish_rows": 0, "job_invalid_rows": 0,
    }
    for line, row in rows(task_path):
        diagnostics["task_rows"] += 1
        try:
            event_type = get_field(row, task_schema["event_type_column"], task_path, line)
            if event_type != task_schema["submit_value"]:
                continue
            job_id = as_int(get_field(row, task_schema["job_id_column"], task_path, line), "task job id")
            timestamp = as_int(get_field(row, task_schema["timestamp_column"], task_path, line), "task timestamp")
            submits[job_id].append(timestamp)
            diagnostics["task_submit_rows"] += 1
        except (ValueError, csv.Error):
            diagnostics["task_invalid_rows"] += 1
    for line, row in rows(job_path):
        diagnostics["job_rows"] += 1
        try:
            event_type = get_field(row, job_schema["event_type_column"], job_path, line)
            if event_type not in job_schema["finish_values"]:
                continue
            job_id = as_int(get_field(row, job_schema["job_id_column"], job_path, line), "job id")
            # Read and validate timestamp too: this catches a schema mismatch
            # rather than treating arbitrary columns as a lifecycle record.
            as_int(get_field(row, job_schema["timestamp_column"], job_path, line), "job timestamp")
            completed.add(job_id)
            diagnostics["job_finish_rows"] += 1
        except (ValueError, csv.Error):
            diagnostics["job_invalid_rows"] += 1
    return submits, completed, diagnostics


def expected_results(submits, completed, gap, include_empty):
    answer = {}
    for job_id, timestamps in submits.items():
        timestamps.sort()
        current = 0
        best = 0
        previous = None
        for timestamp in timestamps:
            if previous is None or timestamp - previous >= gap:
                if current > best:
                    best = current
                current = 1
            else:
                current += 1
            previous = timestamp
        if current > best:
            best = current
        if job_id in completed:
            answer[job_id] = best
    if include_empty:
        for job_id in completed:
            answer.setdefault(job_id, 0)
    return answer


def output_files(path):
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise ValueError("output path does not exist: " + path)
    files = []
    for root, _, names in os.walk(path):
        for name in names:
            if name.startswith("_") or name.startswith("."):
                continue
            candidate = os.path.join(root, name)
            if os.path.isfile(candidate):
                files.append(candidate)
    return sorted(files)


def read_actual(path):
    actual = {}
    malformed = []
    duplicates = []
    for filename in output_files(path):
        with open(filename, "rt", encoding="utf-8") as handle:
            for line_number, text in enumerate(handle, 1):
                if not text.strip():
                    continue
                match = TUPLE_RE.match(text)
                if not match:
                    malformed.append({"file": filename, "line": line_number, "text": text.rstrip("\n")})
                    continue
                key, value = int(match.group(1)), int(match.group(2))
                if key in actual:
                    duplicates.append({"job_id": key, "previous": actual[key], "new": value})
                actual[key] = value
    return actual, malformed, duplicates


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        task_path = request["task_input"]
        job_path = request["job_input"]
        task_schema = checked_schema(request["task_schema"], "task_schema", need_submit=True)
        job_schema = checked_schema(request["job_schema"], "job_schema", need_finish=True)
        gap = as_int(request.get("gap_microseconds", 600000000), "gap_microseconds")
        if gap <= 0:
            raise ValueError("gap_microseconds must be positive")
        include_empty = bool(request.get("include_finished_without_submits", False))
        submits, completed, diagnostics = parse_inputs(task_path, job_path, task_schema, job_schema)
        expected = expected_results(submits, completed, gap, include_empty)
        response = {
            "ok": True,
            "gap_microseconds": gap,
            "diagnostics": diagnostics,
            "expected": [{"job_id": key, "longest_stage": expected[key]} for key in sorted(expected)],
        }
        if "output" in request and request["output"] is not None:
            actual, malformed, duplicates = read_actual(request["output"])
            missing = sorted(set(expected) - set(actual))
            unexpected = sorted(set(actual) - set(expected))
            incorrect = [{"job_id": key, "expected": expected[key], "actual": actual[key]}
                         for key in sorted(set(expected) & set(actual)) if expected[key] != actual[key]]
            comparison = {
                "ok": not missing and not unexpected and not incorrect and not malformed and not duplicates,
                "missing_job_ids": missing,
                "unexpected_job_ids": unexpected,
                "incorrect": incorrect,
                "malformed_lines": malformed,
                "duplicate_job_ids": duplicates,
            }
            response["comparison"] = comparison
            response["ok"] = comparison["ok"]
        print(json.dumps(response, sort_keys=True))
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
