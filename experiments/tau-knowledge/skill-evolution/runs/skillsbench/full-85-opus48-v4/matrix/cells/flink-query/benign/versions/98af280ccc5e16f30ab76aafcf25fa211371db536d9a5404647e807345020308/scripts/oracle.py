#!/usr/bin/env python3
"""Independent reference oracle for LongestSessionPerJob.

Reads the same gzipped task/job event CSVs the Flink job reads and computes, per job,
the maximum number of SUBMIT task events within an event-time session (stage) whose
consecutive SUBMITs are < gap apart. Uses the SAME units/semantics as the Flink job:
milliseconds = microseconds // 1000, default gap 600000 ms (10 min), count every SUBMIT
(no task dedup), and (by default) emit only jobs that have a FINISH job event.

stdin  JSON: {
  "task_input": str, "job_input": str,
  "gap_ms": int = 600000,
  "finish_event_types": [int] = [4],
  "only_finished": bool = true
}
stdout JSON: {"counts": {jobId(str): maxCount(int)}, "num_jobs": int}
"""
import sys
import json
import gzip
import csv


def read_rows(path):
    with gzip.open(path, "rt", newline="") as fh:
        for row in csv.reader(fh):
            yield row


def main():
    cfg = json.load(sys.stdin)
    task_input = cfg["task_input"]
    job_input = cfg["job_input"]
    gap_ms = int(cfg.get("gap_ms", 600000))
    finish_types = set(cfg.get("finish_event_types", [4]))
    only_finished = bool(cfg.get("only_finished", True))

    submits = {}  # jobId -> list of event-time millis of SUBMIT task events
    for row in read_rows(task_input):
        if len(row) < 6:
            continue
        try:
            ts_us = int(row[0])
            job = int(row[2])
            et = int(row[5])
        except (ValueError, IndexError):
            continue
        if et == 0:  # SUBMIT
            submits.setdefault(job, []).append(ts_us // 1000)

    finished = set()
    for row in read_rows(job_input):
        if len(row) < 4:
            continue
        try:
            job = int(row[2])
            et = int(row[3])
        except (ValueError, IndexError):
            continue
        if et in finish_types:
            finished.add(job)

    counts = {}
    for job, times in submits.items():
        times.sort()
        best = 0
        cur = 0
        prev = None
        for t in times:
            if prev is None or (t - prev) < gap_ms:
                cur += 1
            else:
                cur = 1  # gap >= gap_ms closes the previous session
            prev = t
            if cur > best:
                best = cur
        counts[job] = best

    if only_finished:
        counts = {j: c for j, c in counts.items() if j in finished}

    out = {"counts": {str(j): c for j, c in counts.items()}, "num_jobs": len(counts)}
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
