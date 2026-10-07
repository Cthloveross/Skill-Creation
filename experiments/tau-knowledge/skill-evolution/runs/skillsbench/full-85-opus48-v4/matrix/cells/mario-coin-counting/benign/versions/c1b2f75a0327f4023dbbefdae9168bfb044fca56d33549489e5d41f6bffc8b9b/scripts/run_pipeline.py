#!/usr/bin/env python3
"""End-to-end: extract key frames -> grayscale in place -> count -> CSV.

stdin (all optional; defaults match the mario-coin-counting task):
{
  "video": "/root/super-mario.mp4",
  "out_dir": "/root",
  "basename": "keyframes",
  "templates": {"coins": "/root/coin.png",
                 "enemies": "/root/enemy.png",
                 "turtles": "/root/turtle.png"},
  "columns": ["coins", "enemies", "turtles"],
  "csv": "/root/counting_results.csv",
  "thresholds": 0.7,
  "scales": [0.5,0.75,1.0,1.25,1.5,2.0],
  "iou": 0.3
}
stdout: {"csv": path, "rows": N, "frames": N, "all_grayscale": bool,
         "results": [...]}

The CSV header is ["frame_id"] + columns; frame_id is each frame's absolute
path; counts are integers; one row per key frame in sorted (timeline) order.
"""
import csv
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matching import read_gray, read_template_gray, count_objects  # noqa: E402

DEFAULT_SCALES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def _thr(thresholds, name):
    if isinstance(thresholds, dict):
        return float(thresholds.get(name, 0.7))
    return float(thresholds)


def extract_keyframes(video, out_dir, basename):
    if not os.path.isfile(video):
        raise FileNotFoundError("video not found: %s" % video)
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, basename + "_%03d.png")
    glob_pat = os.path.join(out_dir, basename + "_*.png")
    for old in glob.glob(glob_pat):
        try:
            os.remove(old)
        except OSError:
            pass
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-skip_frame", "nokey",
           "-i", video, "-an", "-vsync", "vfr", pattern]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    frames = sorted(glob.glob(glob_pat))
    if proc.returncode != 0 or not frames:
        for old in frames:
            try:
                os.remove(old)
            except OSError:
                pass
        cmd2 = ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-an",
                "-vf", "select=eq(pict_type\\,I)", "-vsync", "vfr", pattern]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True)
        frames = sorted(glob.glob(glob_pat))
        if proc2.returncode != 0 or not frames:
            raise RuntimeError(
                "ffmpeg key-frame extraction failed: %s | %s"
                % (proc.stderr, proc2.stderr))
    return frames


def main():
    cfg = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    video = cfg.get("video", "/root/super-mario.mp4")
    out_dir = cfg.get("out_dir", "/root")
    basename = cfg.get("basename", "keyframes")
    templates = cfg.get("templates", {
        "coins": "/root/coin.png",
        "enemies": "/root/enemy.png",
        "turtles": "/root/turtle.png",
    })
    columns = cfg.get("columns", ["coins", "enemies", "turtles"])
    csv_path = cfg.get("csv", "/root/counting_results.csv")
    thresholds = cfg.get("thresholds", 0.7)
    scales = cfg.get("scales", DEFAULT_SCALES)
    iou = float(cfg.get("iou", 0.3))

    for name in columns:
        if name not in templates:
            raise KeyError("no template path supplied for column '%s'" % name)
        if not os.path.isfile(templates[name]):
            raise FileNotFoundError("template not found: %s" % templates[name])

    # Step 1: extract key frames (preserving timeline order).
    frames = extract_keyframes(video, out_dir, basename)

    # Step 3: grayscale in place; verify colorspace.
    import cv2
    all_gray = True
    for p in frames:
        img = cv2.imread(p, cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError("cannot read frame: %s" % p)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if not cv2.imwrite(p, gray):
            raise IOError("failed to overwrite %s" % p)
        if cv2.imread(p, cv2.IMREAD_UNCHANGED).ndim != 2:
            all_gray = False

    # Steps 4-5: count each template per frame.
    templ_gray = {name: read_template_gray(templates[name])
                  for name in columns}
    results = []
    for fp in frames:
        g = read_gray(fp)
        row = {"frame_id": fp}
        for name in columns:
            row[name] = int(count_objects(g, templ_gray[name],
                                          _thr(thresholds, name), scales, iou))
        results.append(row)

    # Step 6: write CSV, one record per frame, integer counts.
    header = ["frame_id"] + list(columns)
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in results:
            w.writerow([row["frame_id"]] + [int(row[c]) for c in columns])

    # Validate: one row per frame.
    with open(csv_path, newline="") as fh:
        rows = list(csv.reader(fh))
    data_rows = len(rows) - 1
    if data_rows != len(frames):
        raise AssertionError(
            "CSV row count %d != frame count %d" % (data_rows, len(frames)))
    if rows[0] != header:
        raise AssertionError("CSV header mismatch: %s" % rows[0])

    json.dump({"csv": csv_path, "rows": data_rows, "frames": len(frames),
               "all_grayscale": all_gray, "results": results}, sys.stdout)


if __name__ == "__main__":
    main()
