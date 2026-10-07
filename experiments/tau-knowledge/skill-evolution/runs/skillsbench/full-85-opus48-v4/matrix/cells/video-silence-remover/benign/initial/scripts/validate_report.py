#!/usr/bin/env python3
"""Validate compression_report.json against the public task contract.

Input (JSON on stdin): one of
  {"report_path": "compression_report.json", "input": "...", "output": "..."}
  or {"report": {...}, "input": "...", "output": "..."}
Output (JSON on stdout): {"ok": bool, "errors": [...], "warnings": [...]}

Checks are derived from the public request: required fields and numeric types,
segment ordering / non-overlap / non-negative / within-duration, and
original ~= compressed + removed. If an output video path is supplied it is
probed to confirm audio+video streams and that measured duration matches the
reported compressed duration.
"""
import sys, os, json, subprocess

FIELDS = ["original_duration_seconds", "compressed_duration_seconds",
          "removed_duration_seconds", "compression_percentage",
          "segments_removed"]


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=False)


def probe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path])
    try:
        return float(json.loads(r.stdout.decode())["format"]["duration"])
    except Exception:
        return None


def stream_types(path):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type", "-of", "csv=p=0", path])
    return [x.strip() for x in r.stdout.decode().splitlines() if x.strip()]


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def main():
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        print(json.dumps({"ok": False, "errors": [f"bad stdin: {e}"]}))
        return 1

    errors, warnings = [], []
    report = cfg.get("report")
    if report is None:
        rp = cfg.get("report_path", "compression_report.json")
        if not os.path.exists(rp):
            print(json.dumps({"ok": False,
                              "errors": [f"report not found: {rp}"]}))
            return 1
        with open(rp) as fh:
            report = json.load(fh)

    for f in FIELDS:
        if f not in report:
            errors.append(f"missing field: {f}")
    if errors:
        print(json.dumps({"ok": False, "errors": errors}))
        return 1

    orig = report["original_duration_seconds"]
    comp = report["compressed_duration_seconds"]
    rem = report["removed_duration_seconds"]
    pct = report["compression_percentage"]
    segs = report["segments_removed"]

    for name, v in (("original", orig), ("compressed", comp),
                    ("removed", rem), ("compression_percentage", pct)):
        if not is_num(v):
            errors.append(f"{name} is not numeric: {v!r}")
    if not isinstance(segs, list):
        errors.append("segments_removed is not a list")
        segs = []

    if is_num(orig) and is_num(comp) and is_num(rem):
        if abs(orig - (comp + rem)) > max(0.5, 0.01 * orig):
            errors.append(
                f"math inconsistent: original={orig} vs compressed+removed="
                f"{round(comp + rem, 3)}")
        if orig > 0 and is_num(pct):
            exp = round(rem / orig * 100.0, 3)
            if abs(pct - exp) > 1.0:
                warnings.append(
                    f"compression_percentage {pct} != removed/original*100 "
                    f"({exp})")
        if comp < 0 or rem < 0:
            errors.append("negative compressed/removed duration")
        if comp > orig + 0.5:
            errors.append("compressed longer than original")

    prev_end = -1.0
    seg_sum = 0.0
    for i, s in enumerate(segs):
        if not isinstance(s, dict):
            errors.append(f"segment {i} not an object")
            continue
        for k in ("start", "end", "duration"):
            if k not in s or not is_num(s[k]):
                errors.append(f"segment {i} missing/non-numeric {k}")
        if any(k not in s or not is_num(s[k])
               for k in ("start", "end", "duration")):
            continue
        st, en, du = s["start"], s["end"], s["duration"]
        if st < 0 or en < 0 or du < 0:
            errors.append(f"segment {i} has negative value")
        if en < st:
            errors.append(f"segment {i} end<start")
        if abs((en - st) - du) > 0.05:
            warnings.append(f"segment {i} duration != end-start")
        if is_num(orig) and en > orig + 0.5:
            errors.append(f"segment {i} end {en} beyond duration {orig}")
        if st < prev_end - 1e-3:
            errors.append(f"segment {i} overlaps/not sorted (start {st} <"
                          f" prev_end {prev_end})")
        prev_end = max(prev_end, en)
        seg_sum += du

    if is_num(rem) and segs and abs(seg_sum - rem) > max(1.0, 0.05 * (rem or 1)):
        warnings.append(
            f"sum of segment durations {round(seg_sum, 3)} differs from "
            f"removed_duration_seconds {rem}")

    out = cfg.get("output")
    if out and os.path.exists(out):
        types = stream_types(out)
        if "video" not in types:
            errors.append("output has no video stream")
        if "audio" not in types:
            warnings.append("output has no audio stream")
        md = probe_duration(out)
        if md is not None and is_num(comp) and abs(md - comp) > max(1.0, 0.02 * comp):
            warnings.append(
                f"measured output duration {round(md, 3)} differs from "
                f"reported compressed {comp}")
    elif out:
        warnings.append(f"output video not found: {out}")

    print(json.dumps({"ok": len(errors) == 0, "errors": errors,
                      "warnings": warnings}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
