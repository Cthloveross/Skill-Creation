#!/usr/bin/env python3
"""Extract codec keyframes, grayscale them in place, count supplied templates, and write CSV.

JSON stdin schema:
{
  "video_path": "/root/super-mario.mp4",
  "templates": {"coins": "/root/coin.png", "enemies": "/root/enemy.png", "turtles": "/root/turtle.png"},
  "output_dir": "/root",                 # optional
  "keyframe_prefix": "keyframes_",        # optional
  "frame_id_dir": "/root",                # optional
  "csv_path": "/root/counting_results.csv" # optional
}

Success stdout schema:
{"ok": true, "frames": int, "csv_path": str,
 "calibration": {column: {"threshold_min": float, "threshold_max": float,
                            "detections": int}},
 "validation": {"ok": true, ...}}
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except Exception as exc:  # handled after JSON parsing so callers receive a useful object
    cv2 = None
    np = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = None


class SkillError(RuntimeError):
    pass


def run_checked(args):
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, check=False)
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % args[0]) from exc
    if proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (args[0], detail))
    return proc.stdout


def canonical(path):
    return str(Path(path).expanduser().resolve())


def require_file(path, label):
    candidate = Path(path)
    if not candidate.is_file():
        raise SkillError("%s is missing or is not a regular file: %s" % (label, path))
    return candidate.resolve()


def probe_keyframes(video):
    """Return codec-key-frame metadata in decoded/presentation listing order."""
    output = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
        "-show_entries", "frame=key_frame,best_effort_timestamp_time",
        "-of", "json", str(video),
    ])
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise SkillError("ffprobe returned invalid JSON") from exc
    frames = [frame for frame in payload.get("frames", []) if int(frame.get("key_frame", 0)) == 1]
    if not frames:
        raise SkillError("ffprobe found no decodable codec key frames in the video")
    return frames


def remove_stale_keyframes(output_dir, prefix):
    # The prefix is validated, and only its PNG products are owned by this invocation.
    for path in output_dir.glob(prefix + "*.png"):
        if path.is_file():
            path.unlink()


def extract_keyframes(video, output_dir, prefix):
    output_dir.mkdir(parents=True, exist_ok=True)
    remove_stale_keyframes(output_dir, prefix)
    pattern = str(output_dir / (prefix + "%03d.png"))
    # skip_frame is an input decoder option. -vsync 0 prevents duplication or CFR padding.
    run_checked([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-skip_frame", "nokey",
        "-i", str(video), "-map", "0:v:0", "-an", "-vsync", "0", pattern,
    ])
    paths = sorted(output_dir.glob(prefix + "*.png"), key=frame_number_from_path)
    if not paths:
        raise SkillError("ffmpeg wrote no keyframe PNG files")
    return paths


def frame_number_from_path(path):
    match = re.search(r"(\d+)\.png$", path.name)
    if not match:
        raise SkillError("unexpected keyframe filename: %s" % path)
    return int(match.group(1))


def load_as_gray(path):
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SkillError("OpenCV could not read image: %s" % path)
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 1:
        gray = image[:, :, 0]
    elif image.ndim == 3 and image.shape[2] in (3, 4):
        # OpenCV decodes color PNGs as BGR/BGRA; this is also the conversion used for templates.
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
    else:
        raise SkillError("unsupported image shape %r for %s" % (image.shape, path))
    if gray.dtype != np.uint8:
        gray = cv2.convertScaleAbs(gray)
    return gray


def grayscale_in_place(paths):
    grays = []
    for path in paths:
        gray = load_as_gray(path)
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not overwrite keyframe as grayscale PNG: %s" % path)
        # Reopen the written artifact rather than trusting encoder return status.
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2:
            raise SkillError("written keyframe is not a single-channel grayscale PNG: %s" % path)
        grays.append(reopened)
    return grays


def otsu_response_threshold(response):
    """Map Otsu's threshold from an individual float response map back to score units."""
    lo, hi = float(response.min()), float(response.max())
    if hi - lo < 1e-12:
        return hi
    encoded = np.clip((response - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    otsu_u8, _ = cv2.threshold(encoded, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return lo + (hi - lo) * (float(otsu_u8) / 255.0)


def detect_template(gray_frame, gray_template):
    """Return NMS detections and response-derived calibration details for one image."""
    fh, fw = gray_frame.shape[:2]
    th, tw = gray_template.shape[:2]
    if th < 2 or tw < 2:
        raise SkillError("template is too small for correlation matching")
    if th > fh or tw > fw:
        raise SkillError("template dimensions exceed a keyframe (%dx%d > %dx%d)" % (tw, th, fw, fh))

    response = cv2.matchTemplate(gray_frame, gray_template, cv2.TM_CCOEFF_NORMED)
    if not np.isfinite(response).all():
        raise SkillError("template response contained non-finite scores")

    # Both components are estimated from this frame/template pair: Otsu finds a response
    # population split and the quantile estimates the upper background tail.
    otsu = otsu_response_threshold(response)
    background_tail = float(np.quantile(response, 0.995))
    threshold = max(otsu, background_tail)

    # Object extent controls duplicate suppression; there is no image-independent pixel radius.
    radius = max(1, int(round(min(th, tw) * 0.45)))
    kernel = np.ones((2 * radius + 1, 2 * radius + 1), dtype=np.uint8)
    local_max = response >= cv2.dilate(response, kernel)
    ys, xs = np.where(local_max & (response >= threshold))
    candidates = sorted(((float(response[y, x]), int(x), int(y)) for y, x in zip(ys, xs)), reverse=True)

    # Dilation removes most duplicates. A score-ordered geometric NMS is retained for flat
    # plateaus and neighboring maxima, with distance determined by the template itself.
    kept = []
    min_distance_sq = float(radius * radius)
    for score, x, y in candidates:
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > min_distance_sq
               for _, old_x, old_y in kept):
            kept.append((score, x, y))
    return kept, {
        "threshold": float(threshold),
        "otsu_threshold": float(otsu),
        "background_tail": float(background_tail),
        "suppression_radius_px": radius,
        "candidate_peaks": len(candidates),
    }


def validate_artifacts(frame_paths, expected_keyframe_count, csv_path, columns, frame_id_dir):
    if len(frame_paths) != expected_keyframe_count:
        raise SkillError("keyframe metadata/files disagree: ffprobe=%d, PNGs=%d" %
                         (expected_keyframe_count, len(frame_paths)))
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in frame_paths]
    for path in frame_paths:
        written = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if written is None or written.ndim != 2:
            raise SkillError("validation found a non-grayscale or unreadable frame: %s" % path)
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != columns:
                raise SkillError("CSV columns are %r, expected %r" % (reader.fieldnames, columns))
            rows = list(reader)
    except OSError as exc:
        raise SkillError("could not reopen CSV for validation: %s" % csv_path) from exc
    if len(rows) != len(frame_paths):
        raise SkillError("CSV row count %d does not equal keyframe count %d" % (len(rows), len(frame_paths)))
    actual_ids = [row.get("frame_id") for row in rows]
    if actual_ids != expected_ids:
        raise SkillError("CSV frame_id values are not the canonical timeline-ordered PNG paths")
    for row in rows:
        for column in columns[1:]:
            value = row.get(column)
            if value is None or not re.fullmatch(r"\d+", value):
                raise SkillError("CSV count is not a nonnegative integer for column %s" % column)
    return {"ok": True, "frames_checked": len(frame_paths), "csv_rows_checked": len(rows)}


def main(config):
    if IMPORT_ERROR:
        raise SkillError("OpenCV and NumPy are required: " + IMPORT_ERROR)
    if not isinstance(config, dict):
        raise SkillError("stdin JSON must be an object")
    video = require_file(config.get("video_path", ""), "video")
    templates_spec = config.get("templates")
    if not isinstance(templates_spec, dict) or not templates_spec:
        raise SkillError("templates must be a nonempty object mapping count columns to image paths")
    if any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)
           for k in templates_spec):
        raise SkillError("template names must be simple CSV column identifiers")
    template_paths = {name: require_file(value, "template " + name)
                      for name, value in templates_spec.items()}
    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty filename prefix without path separators")
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_frames = probe_keyframes(video)
    frame_paths = extract_keyframes(video, output_dir, prefix)
    gray_frames = grayscale_in_place(frame_paths)
    gray_templates = {name: load_as_gray(path) for name, path in template_paths.items()}

    columns = ["frame_id"] + list(templates_spec.keys())
    records = []
    calibration = {name: {"threshold_min": float("inf"), "threshold_max": float("-inf"), "detections": 0}
                   for name in templates_spec}
    for path, gray in zip(frame_paths, gray_frames):
        record = {"frame_id": str((frame_id_dir / path.name).resolve())}
        for name in templates_spec:
            detections, details = detect_template(gray, gray_templates[name])
            record[name] = len(detections)
            summary = calibration[name]
            summary["threshold_min"] = min(summary["threshold_min"], details["threshold"])
            summary["threshold_max"] = max(summary["threshold_max"], details["threshold"])
            summary["detections"] += len(detections)
        records.append(record)

    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    validation = validate_artifacts(frame_paths, len(metadata_frames), csv_path, columns, frame_id_dir)
    return {"ok": True, "frames": len(frame_paths), "csv_path": str(csv_path),
            "calibration": calibration, "validation": validation}


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        result = main(config)
    except (SkillError, json.JSONDecodeError, TypeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    print(json.dumps(result, allow_nan=False))
