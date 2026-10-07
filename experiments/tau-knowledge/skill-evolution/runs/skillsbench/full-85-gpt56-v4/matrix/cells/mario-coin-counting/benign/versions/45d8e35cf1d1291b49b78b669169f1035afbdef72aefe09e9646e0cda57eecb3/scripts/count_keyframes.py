#!/usr/bin/env python3
"""JSON stdin -> JSON stdout keyframe extraction and template-counting entrypoint."""
import csv
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def fail(message):
    raise RuntimeError(message)


def require_path(value, field):
    if not isinstance(value, str) or not value:
        fail(f"{field} must be a nonempty path string")
    return value


def pattern_glob(pattern):
    # ffmpeg image-number placeholders (e.g. %03d) become a safe wildcard.
    return re.sub(r"%0?\d*d", "*", pattern)


def frame_path(pattern, number):
    try:
        return pattern % number
    except (TypeError, ValueError) as exc:
        fail(f"frame_pattern must contain one ffmpeg integer placeholder: {exc}")


def run_checked(args):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode:
        detail = proc.stderr[-3000:]
        fail(f"external command failed ({args[0]}): {detail}")
    return proc.stdout


def video_metadata(video):
    text = run_checked([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", video,
    ])
    return json.loads(text)


def remove_old_frames(pattern):
    for name in glob.glob(pattern_glob(pattern)):
        # Restrict deletion to regular files and PNG-like output selected by caller's pattern.
        if os.path.isfile(name):
            os.unlink(name)


def extract_keyframes(video, pattern):
    Path(pattern).parent.mkdir(parents=True, exist_ok=True)
    # select chooses encoded I pictures; -vsync 0 prevents duplication to an output rate.
    run_checked([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video,
        "-vf", "select=eq(pict_type\\,I)", "-vsync", "0", "-start_number", "1", pattern,
    ])
    frames = []
    index = 1
    while os.path.exists(frame_path(pattern, index)):
        frames.append(frame_path(pattern, index))
        index += 1
    if not frames:
        fail("no codec keyframe images were written")
    return frames


def read_gray(path):
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if image is None or image.ndim != 2 or image.size == 0:
        fail(f"cannot read grayscale image: {path}")
    return image


def grayscale_inplace(paths):
    for path in paths:
        # Read source independently of its source colorspace and overwrite as one-channel PNG.
        image = read_gray(path)
        if not cv2.imwrite(path, image):
            fail(f"could not overwrite frame as grayscale: {path}")
        reopened = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2:
            fail(f"frame was not written as a single-channel grayscale PNG: {path}")


def resized_template(template, scale):
    if scale == 1.0:
        return template
    h, w = template.shape
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    return cv2.resize(template, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def count_template(scene, template, threshold, scales, overlap):
    """Return NMS detections as (score, x, y, width, height)."""
    candidates = []
    for scale in scales:
        patch = resized_template(template, scale)
        ph, pw = patch.shape
        if ph > scene.shape[0] or pw > scene.shape[1] or ph < 2 or pw < 2:
            continue
        # Both operands are grayscale uint8, guaranteeing the same image pipeline.
        score_map = cv2.matchTemplate(scene, patch, cv2.TM_CCOEFF_NORMED)
        # Local maxima avoids a cloud of neighboring high response pixels per sprite.
        local = cv2.dilate(score_map, np.ones((3, 3), np.uint8))
        ys, xs = np.where((score_map >= threshold) & (score_map >= local - 1e-7))
        for y, x in zip(ys.tolist(), xs.tolist()):
            candidates.append((float(score_map[y, x]), int(x), int(y), int(pw), int(ph)))
    candidates.sort(reverse=True, key=lambda item: item[0])
    chosen = []
    for candidate in candidates:
        box = candidate[1:]
        if all(iou(box, old[1:]) <= overlap for old in chosen):
            chosen.append(candidate)
    return chosen


def write_and_validate_csv(csv_path, fields, rows, frames):
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        actual = list(reader)
        if reader.fieldnames != fields or len(actual) != len(frames):
            fail("CSV validation failed: schema or row count differs from written frame list")
        for expected_frame, row in zip(frames, actual):
            if row.get("frame_id") != expected_frame:
                fail("CSV validation failed: frame ordering/identity mismatch")
            for field in fields[1:]:
                if not row[field].isdigit() or int(row[field]) < 0:
                    fail(f"CSV validation failed: invalid count for {field}")


def main(config):
    video = require_path(config.get("video"), "video")
    pattern = require_path(config.get("frame_pattern"), "frame_pattern")
    csv_path = require_path(config.get("csv"), "csv")
    templates_arg = config.get("templates")
    if not isinstance(templates_arg, dict) or not templates_arg:
        fail("templates must be a nonempty object of output column names to paths")
    labels = list(templates_arg.keys())
    if any(not isinstance(label, str) or not label for label in labels):
        fail("template labels must be nonempty strings")
    if not os.path.isfile(video):
        fail(f"video does not exist: {video}")
    templates = {}
    for label, path in templates_arg.items():
        path = require_path(path, f"templates.{label}")
        if not os.path.isfile(path):
            fail(f"template does not exist: {path}")
        templates[label] = read_gray(path)

    thresholds = config.get("thresholds", {})
    if not isinstance(thresholds, dict):
        fail("thresholds must be an object")
    scales = config.get("scales", [1.0])
    if not isinstance(scales, list) or not scales or any(not isinstance(v, (int, float)) or v <= 0 for v in scales):
        fail("scales must be a nonempty array of positive numbers")
    scales = [float(v) for v in scales]
    overlap = config.get("nms_overlap", 0.35)
    if not isinstance(overlap, (int, float)) or not 0 < overlap <= 1:
        fail("nms_overlap must be in (0, 1]")
    thresholds = {label: float(thresholds.get(label, 0.75)) for label in labels}
    if any(value < -1 or value > 1 for value in thresholds.values()):
        fail("each threshold must be within normalized correlation range [-1, 1]")

    metadata = video_metadata(video)
    remove_old_frames(pattern)
    frames = extract_keyframes(video, pattern)
    grayscale_inplace(frames)

    rows, diagnostics = [], {label: [] for label in labels}
    for frame in frames:
        scene = read_gray(frame)
        row = {"frame_id": frame}
        for label in labels:
            detections = count_template(scene, templates[label], thresholds[label], scales, float(overlap))
            row[label] = len(detections)
            diagnostics[label].append({"count": len(detections), "scores": [round(d[0], 5) for d in detections]})
        rows.append(row)
    fields = ["frame_id"] + labels
    write_and_validate_csv(csv_path, fields, rows, frames)
    return {"frames": frames, "csv": csv_path, "columns": fields, "metadata": metadata,
            "thresholds": thresholds, "diagnostics": diagnostics}


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            fail("stdin must contain a JSON object")
        print(json.dumps(main(config), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
