#!/usr/bin/env python3
"""Extract codec keyframes, grayscale them, template-count objects, and write CSV.

stdin JSON:
{
  "video_path": "/path/video.mp4",
  "templates": {"coins": "/path/coin.png", "enemies": "/path/enemy.png",
                "turtles": "/path/turtle.png"},
  "output_dir": "/optional/output",
  "keyframe_prefix": "optional_prefix_",
  "frame_id_dir": "/optional/csv/frame/id/directory",
  "csv_path": "/optional/counting_results.csv"
}

stdout success:
{"ok":true,"codec_keyframes":int,"frames":int,"csv_path":str,
 "extraction_method":"ffprobe_frame_indexes","calibration":object,
 "validation":object}
stdout failure: {"ok":false,"error":str}
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import cv2
    import numpy as np
except Exception as exc:  # report a useful runtime failure through the JSON interface
    cv2 = None
    np = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = None

COLUMNS = ("coins", "enemies", "turtles")
HEADER = ["frame_id", *COLUMNS]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class SkillError(RuntimeError):
    pass


def run_checked(command):
    """Run a no-shell command and turn any failure into a concise SkillError."""
    try:
        completed = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False,
        )
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % command[0]) from exc
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (command[0], detail))
    return completed.stdout


def readable_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is not a readable regular file: %s" % (label, value))
    return path.resolve()


def keyframe_indexes(video):
    """Return zero-based presentation-order decoded indexes marked key_frame=1."""
    text = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    flags = [line.strip() for line in text.splitlines() if line.strip()]
    if not flags:
        raise SkillError("ffprobe returned no video-frame metadata")
    unknown = [flag for flag in flags if flag not in ("0", "1")]
    if unknown:
        raise SkillError("ffprobe returned invalid keyframe metadata: %r" % unknown[:3])
    indexes = [index for index, flag in enumerate(flags) if flag == "1"]
    if not indexes:
        raise SkillError("ffprobe reported no codec keyframes")
    return indexes


def numbered_pngs(directory, prefix, require_nonempty=True):
    expression = re.compile(re.escape(prefix) + r"(\d+)\.png$")
    found = []
    for candidate in directory.glob(prefix + "*.png"):
        match = expression.fullmatch(candidate.name)
        if match and candidate.is_file():
            found.append((int(match.group(1)), candidate))
    found.sort(key=lambda item: item[0])
    indexes = [number for number, _ in found]
    if (require_nonempty and not found) or indexes != list(range(1, len(found) + 1)):
        raise SkillError("keyframe names are not consecutive from 001: %r" % indexes)
    return [path for _, path in found]


def clear_numbered_pngs(directory, prefix):
    expression = re.compile(re.escape(prefix) + r"\d+\.png$")
    for candidate in directory.glob(prefix + "*.png"):
        if candidate.is_file() and expression.fullmatch(candidate.name):
            candidate.unlink()


def extract_keyframes(video, stage, prefix, indexes):
    """Extract precisely the ffprobe-marked decoded frames in presentation order.

    The escaped comma is required by FFmpeg's filter-expression parser. Passing
    it as an argv element (rather than through a shell) preserves it exactly.
    """
    selector = "+".join("eq(n\\,%d)" % index for index in indexes)
    destination = str(stage / (prefix + "%03d.png"))
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-map", "0:v:0", "-an",
        "-vf", "select=" + selector,
        # passthrough prevents timestamp-driven duplication or dropping of
        # sparse selected frames. Image names remain sequential via start_number.
        "-vsync", "0", "-start_number", "1", "-pix_fmt", "gray",
        destination,
    ]
    run_checked(command)
    paths = numbered_pngs(stage, prefix)
    if len(paths) != len(indexes):
        raise SkillError(
            "FFmpeg wrote %d keyframe PNGs but ffprobe metadata requires %d"
            % (len(paths), len(indexes))
        )
    return paths


def as_gray(image, label):
    if image is None:
        raise SkillError("could not read %s" % label)
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 1:
        gray = image[:, :, 0]
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        raise SkillError("unsupported %s shape %r" % (label, image.shape))
    if gray.dtype != np.uint8:
        gray = cv2.convertScaleAbs(gray)
    return gray


def png_color_type(path):
    """Read the IHDR color type without an optional image-library dependency."""
    data = path.read_bytes()
    if len(data) < 29 or not data.startswith(PNG_SIGNATURE):
        raise SkillError("saved keyframe is not a readable PNG: %s" % path)
    if data[8:12] != b"\x00\x00\x00\x0d" or data[12:16] != b"IHDR":
        raise SkillError("saved keyframe lacks a valid PNG IHDR: %s" % path)
    return data[25]


def ensure_native_grayscale(paths):
    frames = []
    for path in paths:
        gray = as_gray(cv2.imread(str(path), cv2.IMREAD_UNCHANGED), "keyframe " + str(path))
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not overwrite grayscale keyframe: %s" % path)
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2 or png_color_type(path) not in (0, 4):
            raise SkillError("saved PNG is not native one-channel grayscale: %s" % path)
        frames.append(reopened)
    return frames


def load_template(path):
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    gray = as_gray(raw, "template " + str(path))
    if min(gray.shape[:2]) < 2:
        raise SkillError("template is too small: %s" % path)
    mask = None
    if raw.ndim == 3 and raw.shape[2] == 4:
        alpha = raw[:, :, 3]
        if np.any(alpha == 0) and np.any(alpha > 0):
            mask = np.where(alpha > 0, 255, 0).astype(np.uint8)
    return gray, mask


def local_candidates(frame, template, mask):
    height, width = template.shape[:2]
    if height > frame.shape[0] or width > frame.shape[1]:
        raise SkillError("template is larger than a keyframe")
    if mask is None:
        scores = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    else:
        scores = cv2.matchTemplate(frame, template, cv2.TM_CCORR_NORMED, mask=mask)
    if not np.isfinite(scores).all():
        raise SkillError("template matching returned non-finite scores")
    radius = max(1, int(round(min(height, width) * 0.25)))
    kernel = np.ones((2 * radius + 1, 2 * radius + 1), dtype=np.uint8)
    is_peak = scores >= cv2.dilate(scores, kernel)
    ys, xs = np.where(is_peak)
    return [(float(scores[y, x]), int(x), int(y)) for y, x in zip(ys, xs)], max(height, width)


def non_maximum_suppression(candidates, threshold, distance):
    accepted = []
    squared_distance = distance * distance
    for score, x, y in sorted((item for item in candidates if item[0] >= threshold), reverse=True):
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > squared_distance
               for _, old_x, old_y in accepted):
            accepted.append((score, x, y))
    return accepted


def count_objects(frames, templates):
    """Count distinct high-confidence local template-match peaks per frame."""
    counts = {}
    calibration = {}
    for name in COLUMNS:
        template, mask = templates[name]
        groups = []
        dimensions = []
        for frame in frames:
            candidates, dimension = local_candidates(frame, template, mask)
            groups.append(candidates)
            dimensions.append(dimension)
        all_scores = np.asarray([score for group in groups for score, _, _ in group])
        if not all_scores.size:
            raise SkillError("no local template-match peaks for " + name)
        # Estimate the decision point from this template and this video. The
        # floor excludes ordinary weak background correlations; NMS then makes
        # clustered responses to one sprite count only once.
        threshold = max(0.65, float(np.quantile(all_scores, 0.9985)))
        distance = max(1, int(round(max(dimensions) * 0.75)))
        counts[name] = [len(non_maximum_suppression(group, threshold, distance)) for group in groups]
        calibration[name] = {
            "threshold": threshold,
            "suppression_distance_px": distance,
        }
    return counts, calibration


def write_csv(path, records):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def validate(paths, expected_count, csv_path, frame_id_dir):
    if len(paths) != expected_count:
        raise SkillError("final PNG count differs from codec-keyframe metadata")
    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 2 or png_color_type(path) not in (0, 4):
            raise SkillError("final keyframe is not a readable native grayscale PNG: %s" % path)
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != HEADER:
        raise SkillError("CSV header is not %r" % HEADER)
    if len(rows) != len(paths) + 1:
        raise SkillError("CSV does not have one row per final keyframe")
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in paths]
    actual_ids = []
    for row in rows[1:]:
        if len(row) != 4:
            raise SkillError("CSV row does not have four columns: %r" % row)
        if any(not re.fullmatch(r"\d+", value or "") for value in row[1:]):
            raise SkillError("CSV count is not a non-negative integer: %r" % row)
        actual_ids.append(row[0])
    if actual_ids != expected_ids:
        raise SkillError("CSV frame_id values do not match final keyframes in order")
    return {"ok": True, "frames_checked": len(paths), "csv_rows_checked": len(paths)}


def main(config):
    if IMPORT_ERROR:
        raise SkillError("OpenCV and NumPy are required: " + IMPORT_ERROR)
    if not isinstance(config, dict):
        raise SkillError("stdin JSON must be an object")
    video = readable_file(config.get("video_path"), "video")
    supplied = config.get("templates")
    if not isinstance(supplied, dict) or set(supplied) != set(COLUMNS):
        raise SkillError("templates must contain exactly coins, enemies, turtles")
    template_paths = {name: readable_file(supplied[name], "template " + name) for name in COLUMNS}

    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty filename prefix")
    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale deliverables before processing. Staging prevents a partially
    # extracted set from being mistaken for complete current output.
    clear_numbered_pngs(output_dir, prefix)
    if csv_path.exists():
        csv_path.unlink()

    stage = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    temporary_csv = None
    try:
        indexes = keyframe_indexes(video)
        staged_paths = extract_keyframes(video, stage, prefix, indexes)
        frames = ensure_native_grayscale(staged_paths)
        templates = {name: load_template(template_paths[name]) for name in COLUMNS}
        counts, calibration = count_objects(frames, templates)

        # Publish the complete validated keyframe set before writing records
        # derived from its final ordered paths.
        for source in staged_paths:
            os.replace(source, output_dir / source.name)
        final_paths = numbered_pngs(output_dir, prefix)
        if len(final_paths) != len(indexes):
            raise SkillError("published keyframe set is incomplete")

        records = []
        for index, path in enumerate(final_paths):
            record = {"frame_id": str((frame_id_dir / path.name).resolve())}
            record.update({name: int(counts[name][index]) for name in COLUMNS})
            records.append(record)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent)
        )
        os.close(descriptor)
        temporary_csv = Path(temporary_name)
        write_csv(temporary_csv, records)
        validate(final_paths, len(indexes), temporary_csv, frame_id_dir)
        os.replace(temporary_csv, csv_path)
        temporary_csv = None
        validation = validate(final_paths, len(indexes), csv_path, frame_id_dir)
        return {
            "ok": True,
            "codec_keyframes": len(indexes),
            "frames": len(final_paths),
            "csv_path": str(csv_path),
            "extraction_method": "ffprobe_frame_indexes",
            "calibration": calibration,
            "validation": validation,
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if temporary_csv is not None and temporary_csv.exists():
            temporary_csv.unlink()


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    print(json.dumps(result, allow_nan=False))
