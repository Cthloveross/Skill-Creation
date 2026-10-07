#!/usr/bin/env python3
"""Generate grayscale codec-keyframe PNGs and a Mario template-count CSV.

stdin JSON:
{
  "video_path": "/root/super-mario.mp4",
  "templates": {"coins": "/root/coin.png", "enemies": "/root/enemy.png",
                "turtles": "/root/turtle.png"},
  "output_dir": "/root", "keyframe_prefix": "keyframes_",
  "frame_id_dir": "/root", "csv_path": "/root/counting_results.csv"
}

stdout success: {"ok":true,"codec_keyframes":int,"frames":int,
                 "csv_path":str,"calibration":object,"validation":object}
stdout failure: {"ok":false,"error":str}
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
except Exception as exc:  # dependency diagnostic
    cv2 = None
    np = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = None

COUNT_COLUMNS = ("coins", "enemies", "turtles")


class SkillError(RuntimeError):
    pass


def run_checked(args):
    try:
        completed = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False
        )
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % args[0]) from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (args[0], message))
    return completed.stdout


def require_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is missing or is not a regular file: %s" % (label, value))
    return path.resolve()


def probe_codec_keyframe_count(video):
    """Count key-frame flags using the exact public ffprobe metadata field."""
    raw = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    count = sum(line.strip() == "1" for line in raw.splitlines())
    if count <= 0:
        raise SkillError("ffprobe found no codec keyframes in the video")
    return count


def frame_number(path, prefix):
    match = re.fullmatch(re.escape(prefix) + r"(\d+)\.png", path.name)
    if not match:
        raise SkillError("unexpected keyframe filename: %s" % path)
    return int(match.group(1))


def remove_owned_outputs(output_dir, prefix, csv_path):
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob(prefix + "*.png"):
        if path.is_file():
            path.unlink()
    if csv_path.exists():
        if not csv_path.is_file():
            raise SkillError("CSV destination exists but is not a regular file: %s" % csv_path)
        csv_path.unlink()


def list_keyframes(output_dir, prefix):
    paths = list(output_dir.glob(prefix + "*.png"))
    if not paths:
        raise SkillError("ffmpeg wrote no keyframe PNG files")
    paths.sort(key=lambda item: frame_number(item, prefix))
    numbers = [frame_number(path, prefix) for path in paths]
    if numbers != list(range(1, len(paths) + 1)):
        raise SkillError("keyframes are not consecutively numbered from 001: %r" % numbers)
    return paths


def extract_codec_keyframes(video, output_dir, prefix, expected_count):
    """Decode only key frames, preserving their stream presentation sequence.

    `-skip_frame nokey` is a decoder input option. Unlike a filter expression
    listing frame ordinals, it does not depend on FFmpeg filter escaping or an
    implementation-specific selected-frame variable.
    """
    pattern = str(output_dir / (prefix + "%03d.png"))
    run_checked([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-skip_frame", "nokey", "-i", str(video),
        "-map", "0:v:0", "-an", "-vsync", "0", "-start_number", "1", pattern,
    ])
    paths = list_keyframes(output_dir, prefix)
    if len(paths) != expected_count:
        raise SkillError(
            "keyframe metadata/files disagree: ffprobe=%d, PNGs=%d" %
            (expected_count, len(paths))
        )
    return paths


def gray_and_mask(path):
    """Read an image through a shared grayscale pipeline and preserve alpha mask."""
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SkillError("OpenCV could not read image: %s" % path)
    mask = None
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 1:
        gray = image[:, :, 0]
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        alpha = image[:, :, 3]
        if np.any(alpha == 0) and np.any(alpha != 0):
            mask = np.where(alpha != 0, 255, 0).astype(np.uint8)
    else:
        raise SkillError("unsupported image shape %r for %s" % (image.shape, path))
    if gray.dtype != np.uint8:
        gray = cv2.convertScaleAbs(gray)
    return gray, mask


def grayscale_frames_in_place(paths):
    frames = []
    for path in paths:
        gray, _ = gray_and_mask(path)
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not overwrite keyframe as grayscale PNG: %s" % path)
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2:
            raise SkillError("written keyframe is not a single-channel grayscale PNG: %s" % path)
        frames.append(reopened)
    return frames


def otsu_score_threshold(values):
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        raise SkillError("template matching produced no local peaks")
    low, high = float(values.min()), float(values.max())
    if high - low < 1e-12:
        return high
    encoded = np.clip((values - low) * 255.0 / (high - low), 0, 255).astype(np.uint8)
    cutoff, _ = cv2.threshold(encoded, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return low + (high - low) * float(cutoff) / 255.0


def response_peaks(frame, template, mask):
    fh, fw = frame.shape[:2]
    th, tw = template.shape[:2]
    if th < 2 or tw < 2:
        raise SkillError("template is too small for correlation matching")
    if th > fh or tw > fw:
        raise SkillError("template dimensions exceed a keyframe (%dx%d > %dx%d)" %
                         (tw, th, fw, fh))
    if mask is None:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    else:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCORR_NORMED, mask=mask)
    if not np.isfinite(response).all():
        raise SkillError("template response contained non-finite scores")

    # One broad local peak represents one possible sprite, prior to final NMS.
    radius = max(1, int(round(min(th, tw) * 0.45)))
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    local = response >= cv2.dilate(response, kernel)
    ys, xs = np.where(local)
    peaks = [(float(response[y, x]), int(x), int(y)) for y, x in zip(ys, xs)]
    return peaks, radius


def calibrate_threshold(peak_sets):
    """Separate the current template's strongest local peaks from its background.

    Otsu is applied to local maxima rather than all response-map pixels. A high
    current-score quantile additionally prevents broad low-correlation texture
    from becoming detections. Both terms are measured anew per template.
    """
    scores = np.asarray([score for peaks in peak_sets for score, _, _ in peaks], dtype=np.float32)
    if scores.size == 0:
        raise SkillError("template matching produced no local peaks")
    otsu = otsu_score_threshold(scores)
    tail = float(np.quantile(scores, 0.995))
    return max(float(otsu), tail), float(otsu), tail


def suppress(peaks, threshold, radius):
    candidates = sorted((p for p in peaks if p[0] >= threshold), reverse=True)
    kept = []
    distance_squared = radius * radius
    for score, x, y in candidates:
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > distance_squared
               for _, old_x, old_y in kept):
            kept.append((score, x, y))
    return kept


def count_templates(frames, templates):
    records_by_name = {}
    calibration = {}
    for name in COUNT_COLUMNS:
        template, mask = templates[name]
        peak_sets = []
        radii = []
        for frame in frames:
            peaks, radius = response_peaks(frame, template, mask)
            peak_sets.append(peaks)
            radii.append(radius)
        threshold, otsu, tail = calibrate_threshold(peak_sets)
        per_frame = [len(suppress(peaks, threshold, radius))
                     for peaks, radius in zip(peak_sets, radii)]
        records_by_name[name] = per_frame
        calibration[name] = {
            "threshold": threshold,
            "otsu_peak_threshold": otsu,
            "peak_tail_threshold": tail,
            "suppression_radius_px": radii[0],
            "detections": int(sum(per_frame)),
        }
    return records_by_name, calibration


def write_csv(csv_path, records):
    columns = ["frame_id"] + list(COUNT_COLUMNS)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def validate(frame_paths, codec_count, csv_path, frame_id_dir):
    if len(frame_paths) != codec_count:
        raise SkillError("keyframe metadata/files disagree during validation")
    for path in frame_paths:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 2:
            raise SkillError("validation found a non-grayscale or unreadable frame: %s" % path)

    columns = ["frame_id"] + list(COUNT_COLUMNS)
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != columns:
            raise SkillError("CSV columns are %r, expected %r" % (reader.fieldnames, columns))
        rows = list(reader)
    if len(rows) != len(frame_paths):
        raise SkillError("CSV row count %d does not equal keyframe count %d" %
                         (len(rows), len(frame_paths)))
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in frame_paths]
    if [row.get("frame_id") for row in rows] != expected_ids:
        raise SkillError("CSV frame_id values are not final timeline-ordered PNG paths")
    for row in rows:
        if set(row) != set(columns):
            raise SkillError("CSV contains an unexpected data-row schema")
        for column in COUNT_COLUMNS:
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
    if not isinstance(template_spec, dict) or set(template_spec) != set(COUNT_COLUMNS):
        raise SkillError("templates must contain exactly coins, enemies, and turtles")
    template_paths = {name: require_file(template_spec[name], "template " + name)
                      for name in COUNT_COLUMNS}

    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty filename prefix without separators")

    codec_count = probe_codec_keyframe_count(video)
    remove_owned_outputs(output_dir, prefix, csv_path)
    frame_paths = extract_codec_keyframes(video, output_dir, prefix, codec_count)
    frames = grayscale_frames_in_place(frame_paths)
    templates = {name: gray_and_mask(path) for name, path in template_paths.items()}
    counts, calibration = count_templates(frames, templates)

    records = []
    for index, path in enumerate(frame_paths):
        row = {"frame_id": str((frame_id_dir / path.name).resolve())}
        for name in COUNT_COLUMNS:
            row[name] = counts[name][index]
        records.append(row)
    write_csv(csv_path, records)
    validation = validate(frame_paths, codec_count, csv_path, frame_id_dir)
    return {"ok": True, "codec_keyframes": codec_count, "frames": len(frame_paths),
            "csv_path": str(csv_path), "calibration": calibration, "validation": validation}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = main(payload)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    print(json.dumps(result, allow_nan=False))
