#!/usr/bin/env python3
"""Extract codec keyframes, save grayscale PNGs, count template peaks, and write CSV.

stdin JSON:
{
  "video_path": "/root/super-mario.mp4",
  "templates": {"coins": "/root/coin.png", "enemies": "/root/enemy.png", "turtles": "/root/turtle.png"},
  "output_dir": "/root",
  "keyframe_prefix": "keyframes_",
  "frame_id_dir": "/root",
  "csv_path": "/root/counting_results.csv"
}

stdout success JSON:
{"ok":true,"frames":int,"csv_path":str,"calibration":object,"validation":object}
stdout error JSON:
{"ok":false,"error":str}
"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except Exception as exc:
    cv2 = None
    np = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = None


class SkillError(RuntimeError):
    pass


def run_checked(args):
    try:
        proc = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % args[0]) from exc
    if proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (args[0], detail))
    return proc.stdout


def require_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is missing or is not a regular file: %s" % (label, value))
    return path.resolve()


def frame_number(path, prefix):
    match = re.fullmatch(re.escape(prefix) + r"(\d+)\.png", path.name)
    if not match:
        raise SkillError("unexpected keyframe filename: %s" % path)
    return int(match.group(1))


def probe_codec_keyframe_count(video):
    """Use the same frame=key_frame metadata semantics required by the task."""
    text = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    count = sum(line.strip() == "1" for line in text.splitlines())
    if count <= 0:
        raise SkillError("ffprobe found no codec keyframes in the video")
    return count


def remove_owned_outputs(output_dir, prefix, csv_path):
    output_dir.mkdir(parents=True, exist_ok=True)
    # This invocation owns only prefix-matching PNG products in output_dir.
    for path in output_dir.glob(prefix + "*.png"):
        if path.is_file():
            path.unlink()
    if csv_path.exists():
        if not csv_path.is_file():
            raise SkillError("CSV destination exists but is not a regular file: %s" % csv_path)
        csv_path.unlink()


def list_keyframes(output_dir, prefix):
    paths = sorted(output_dir.glob(prefix + "*.png"), key=lambda p: frame_number(p, prefix))
    if not paths:
        raise SkillError("ffmpeg wrote no keyframe PNG files")
    numbers = [frame_number(path, prefix) for path in paths]
    expected = list(range(1, len(paths) + 1))
    if numbers != expected:
        raise SkillError("extracted keyframes are not consecutively numbered from 001: %r" % numbers)
    return paths


def extract_codec_keyframes(video, output_dir, prefix, expected_count):
    """Select decoded AVFrames with key_frame set, preserving their presentation sequence."""
    pattern = str(output_dir / (prefix + "%03d.png"))
    # The escaped comma belongs to FFmpeg's select expression, not shell quoting.
    # -vsync 0 prevents FFmpeg from padding or duplicating selected frames.
    run_checked([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-map", "0:v:0", "-vf", "select=eq(key\\,1)", "-vsync", "0", "-an", pattern,
    ])
    paths = list_keyframes(output_dir, prefix)
    if len(paths) != expected_count:
        raise SkillError("keyframe metadata/files disagree: ffprobe=%d, PNGs=%d" %
                         (expected_count, len(paths)))
    return paths


def load_gray(path):
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SkillError("OpenCV could not read image: %s" % path)
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 1:
        gray = image[:, :, 0]
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        raise SkillError("unsupported image shape %r for %s" % (image.shape, path))
    if gray.dtype != np.uint8:
        gray = cv2.convertScaleAbs(gray)
    return gray


def grayscale_frames_in_place(paths):
    result = []
    for path in paths:
        gray = load_gray(path)
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not overwrite keyframe as grayscale PNG: %s" % path)
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2:
            raise SkillError("written keyframe is not a single-channel grayscale PNG: %s" % path)
        result.append(reopened)
    return result


def otsu_score_threshold(response):
    low, high = float(response.min()), float(response.max())
    if high - low < 1e-12:
        return high
    encoded = np.clip((response - low) * (255.0 / (high - low)), 0, 255).astype(np.uint8)
    cutoff, _ = cv2.threshold(encoded, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return low + (high - low) * (float(cutoff) / 255.0)


def detect_template(frame, template):
    fh, fw = frame.shape[:2]
    th, tw = template.shape[:2]
    if th < 2 or tw < 2:
        raise SkillError("template is too small for correlation matching")
    if th > fh or tw > fw:
        raise SkillError("template dimensions exceed a keyframe (%dx%d > %dx%d)" %
                         (tw, th, fw, fh))

    response = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    if not np.isfinite(response).all():
        raise SkillError("template response contained non-finite scores")

    otsu = otsu_score_threshold(response)
    background_tail = float(np.quantile(response, 0.995))
    threshold = max(otsu, background_tail)
    radius = max(1, int(round(min(th, tw) * 0.45)))
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    local_peaks = response >= cv2.dilate(response, kernel)
    ys, xs = np.where(local_peaks & (response >= threshold))
    candidates = sorted(((float(response[y, x]), int(x), int(y)) for y, x in zip(ys, xs)),
                        reverse=True)

    kept = []
    distance_sq = radius * radius
    for score, x, y in candidates:
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > distance_sq
               for _, old_x, old_y in kept):
            kept.append((score, x, y))
    return kept, {"threshold": float(threshold), "otsu_threshold": float(otsu),
                  "background_tail": background_tail,
                  "suppression_radius_px": radius, "candidate_peaks": len(candidates)}


def write_csv(csv_path, columns, records):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def validate(frame_paths, metadata_count, csv_path, columns, frame_id_dir):
    if len(frame_paths) != metadata_count:
        raise SkillError("keyframe metadata/files disagree during validation")
    for path in frame_paths:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if img is None or img.ndim != 2:
            raise SkillError("validation found a non-grayscale or unreadable frame: %s" % path)

    try:
        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != columns:
                raise SkillError("CSV columns are %r, expected %r" % (reader.fieldnames, columns))
            rows = list(reader)
    except OSError as exc:
        raise SkillError("could not reopen CSV: %s" % csv_path) from exc

    if len(rows) != len(frame_paths):
        raise SkillError("CSV row count %d does not equal keyframe count %d" %
                         (len(rows), len(frame_paths)))
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in frame_paths]
    if [row.get("frame_id") for row in rows] != expected_ids:
        raise SkillError("CSV frame_id values are not the final timeline-ordered PNG paths")
    for row in rows:
        for column in columns[1:]:
            if not re.fullmatch(r"\d+", row.get(column) or ""):
                raise SkillError("CSV count is not a nonnegative integer for column %s" % column)
    return {"ok": True, "frames_checked": len(frame_paths), "csv_rows_checked": len(rows)}


def main(config):
    if IMPORT_ERROR:
        raise SkillError("OpenCV and NumPy are required: " + IMPORT_ERROR)
    if not isinstance(config, dict):
        raise SkillError("stdin JSON must be an object")

    video = require_file(config.get("video_path"), "video")
    template_spec = config.get("templates")
    if not isinstance(template_spec, dict) or not template_spec:
        raise SkillError("templates must be a nonempty object mapping columns to image paths")
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
           for name in template_spec):
        raise SkillError("template names must be simple CSV column identifiers")
    templates = {name: require_file(value, "template " + name)
                 for name, value in template_spec.items()}

    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty filename prefix without separators")

    expected_count = probe_codec_keyframe_count(video)
    remove_owned_outputs(output_dir, prefix, csv_path)
    frame_paths = extract_codec_keyframes(video, output_dir, prefix, expected_count)
    frames = grayscale_frames_in_place(frame_paths)
    gray_templates = {name: load_gray(path) for name, path in templates.items()}

    columns = ["frame_id"] + list(template_spec.keys())
    calibration = {name: {"threshold_min": float("inf"), "threshold_max": float("-inf"),
                          "detections": 0} for name in template_spec}
    records = []
    for path, frame in zip(frame_paths, frames):
        row = {"frame_id": str((frame_id_dir / path.name).resolve())}
        for name in template_spec:
            detections, details = detect_template(frame, gray_templates[name])
            row[name] = len(detections)
            summary = calibration[name]
            summary["threshold_min"] = min(summary["threshold_min"], details["threshold"])
            summary["threshold_max"] = max(summary["threshold_max"], details["threshold"])
            summary["detections"] += len(detections)
        records.append(row)

    write_csv(csv_path, columns, records)
    validation = validate(frame_paths, expected_count, csv_path, columns, frame_id_dir)
    return {"ok": True, "frames": len(frame_paths), "csv_path": str(csv_path),
            "calibration": calibration, "validation": validation}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        output = main(payload)
    except (SkillError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    print(json.dumps(output, allow_nan=False))
