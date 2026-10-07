#!/usr/bin/env python3
"""Independent reference calculator for longest task-submit sessions.

stdin: JSON object with task_input and job_input paths. Optional numeric schema keys
are documented in SKILL.md. stdout: {"rows": [[job_id, maximum], ...]}.
"""
import csv
import gzip
import json
import os
import sys
from collections import defaultdict

DEFAULTS = {
    "task_timestamp_column": 0,
    "task_job_id_column": 2,
    "task_event_type_column": 5,
    "job_job_id_column": 2,
    "job_event_type_column": 5,
    "submit_event_type": 0,
    "finish_event_type": 4,
    "gap_microseconds": 600_000_000,
}


def fail(message):
    print(json.dumps({"error": message}), file=sys.stderr)
    raise SystemExit(2)


def integer(value, label):
    try:
        return int(value)
    except (TypeError, ValueError):
        fail("%s must be an integer" % label)


def rows_from_gzip(path):
    if not isinstance(path, str) or not path:
        fail("input path must be a nonempty string")
    if not os.path.isfile(path):
        fail("input file does not exist: %s" % path)
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            for row in csv.reader(source):
                yield row
    except OSError as exc:
        fail("cannot read gzip input %s: %s" % (path, exc))


def required_int(row, column):
    if column < 0 or column >= len(row) or row[column] == "":
        return None
    try:
        return int(row[column])
    except ValueError:
        return None


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must contain one JSON object: %s" % exc)
    if not isinstance(request, dict):
        fail("top-level JSON value must be an object")

    cfg = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in request:
            cfg[key] = integer(request[key], key)
    if cfg["gap_microseconds"] < 0:
        fail("gap_microseconds must be nonnegative")

    submissions = defaultdict(list)
    for row in rows_from_gzip(request.get("task_input")):
        event_type = required_int(row, cfg["task_event_type_column"])
        if event_type != cfg["submit_event_type"]:
            continue
        timestamp = required_int(row, cfg["task_timestamp_column"])
        job_id = required_int(row, cfg["task_job_id_column"])
        if timestamp is not None and job_id is not None:
            submissions[job_id].append(timestamp)

    finished = set()
    for row in rows_from_gzip(request.get("job_input")):
        event_type = required_int(row, cfg["job_event_type_column"])
        if event_type != cfg["finish_event_type"]:
            continue
        job_id = required_int(row, cfg["job_job_id_column"])
        if job_id is not None:
            finished.add(job_id)

    result = []
    gap = cfg["gap_microseconds"]
    for job_id in sorted(finished):
        times = sorted(submissions.get(job_id, []))
        if not times:
            continue
        best = current = 1
        previous = times[0]
        for timestamp in times[1:]:
            # Session windows [t, t+gap) merge only when they overlap.
            if timestamp - previous < gap:
                current += 1
            else:
                best = max(best, current)
                current = 1
            previous = timestamp
        result.append([job_id, max(best, current)])

    json.dump({"rows": result}, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
