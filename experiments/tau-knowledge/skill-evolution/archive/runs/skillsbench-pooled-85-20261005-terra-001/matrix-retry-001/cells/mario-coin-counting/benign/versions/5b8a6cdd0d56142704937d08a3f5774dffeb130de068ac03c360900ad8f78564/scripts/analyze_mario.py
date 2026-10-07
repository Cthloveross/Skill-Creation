#!/usr/bin/env python3
"""Extract codec keyframes, overwrite them as grayscale, count templates, and write CSV.

stdin JSON schema:
{
  "video_path": "/path/video.mp4",
  "templates": {
    "coins": "/path/coin.png",
    "enemies": "/path/enemy.png",
    "turtles": "/path/turtle.png"
  },
  "output_dir": "/optional/output/dir",
  "keyframe_prefix": "optional_prefix_",
  "frame_id_dir": "/optional/csv/frame-id/dir",
  "csv_path": "/optional/counting_results.csv"
}

stdout is either a JSON success object or {"ok": false, "error": string}.
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
except Exception as exc:  # pragma: no cover - dependent on runtime installation
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


def run_checked(argv):
    """Execute an argv command without a shell and return stdout."""
    try:
        result = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False,
        )
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % argv[0]) from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (argv[0], detail))
    return result.stdout


def input_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is not a readable regular file: %s" % (label, value))
    return path.resolve()


def codec_keyframe_count(video):
    text = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    values = [line.strip() for line in text.splitlines() if line.strip()]
    if not values or any(value not in ("0", "1") for value in values):
        raise SkillError("ffprobe returned invalid or empty video frame metadata")
    count = sum(value == "1" for value in values)
    if not count:
        raise SkillError("ffprobe reported no codec keyframes")
    return count


def numbered_pngs(directory, prefix, nonempty=True):
    pattern = re.compile(re.escape(prefix) + r"(\d+)\.png$")
    found = []
    for candidate in directory.glob(prefix + "*.png"):
        match = pattern.fullmatch(candidate.name)
        if match and candidate.is_file():
            found.append((int(match.group(1)), candidate))
    found.sort(key=lambda item: item[0])
    indexes = [number for number, _ in found]
    if (nonempty and not found) or indexes != list(range(1, len(found) + 1)):
        raise SkillError("keyframe names are not consecutive from 001: %r" % indexes)
    return [path for _, path in found]


def clear_numbered_pngs(directory, prefix):
    pattern = re.compile(re.escape(prefix) + r"\d+\.png$")
    for candidate in directory.glob(prefix + "*.png"):
        if candidate.is_file() and pattern.fullmatch(candidate.name):
            candidate.unlink()


def extract_with_selector(video, stage, prefix, selector):
    """Extract selected decoded video frames with image2 sequence numbering."""
    target = str(stage / (prefix + "%03d.png"))
    run_checked([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-map", "0:v:0", "-vf", selector,
        "-vsync", "0", "-start_number", "1", target,
    ])
    return numbered_pngs(stage, prefix)


def extract_codec_keyframes(video, root_stage, prefix, expected):
    """Select key-flag frames, requiring an exact ffprobe-count match.

    The normal selector uses FFmpeg's decoded-frame `key` property. Some older
    codec/filter combinations do not expose that property correctly, so a
    presentation-ordered I-picture fallback is tried only when necessary.
    Neither selector samples by timestamp or frame rate.
    """
    attempts = (
        ("ffmpeg_select_key", r"select=eq(key\,1)"),
        ("ffmpeg_select_i_picture_fallback", r"select=eq(pict_type\,I)"),
    )
    diagnostics = []
    for method, selector in attempts:
        attempt_dir = root_stage / method
        attempt_dir.mkdir(parents=True, exist_ok=True)
        try:
            paths = extract_with_selector(video, attempt_dir, prefix, selector)
        except SkillError as exc:
            diagnostics.append("%s: %s" % (method, exc))
            shutil.rmtree(attempt_dir, ignore_errors=True)
            continue
        if len(paths) == expected:
            return paths, method
        diagnostics.append("%s wrote %d frames, expected %d" % (method, len(paths), expected))
        shutil.rmtree(attempt_dir, ignore_errors=True)
    raise SkillError("could not extract every codec keyframe; " + "; ".join(diagnostics))


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
    """Read PNG IHDR color type without optional Pillow dependency."""
    data = path.read_bytes()
    if len(data) < 29 or not data.startswith(PNG_SIGNATURE):
        raise SkillError("saved frame is not a PNG: %s" % path)
    if data[8:12] != b"\x00\x00\x00\x0d" or data[12:16] != b"IHDR":
        raise SkillError("saved frame lacks a valid PNG IHDR: %s" % path)
    return data[25]


def overwrite_grayscale(paths):
    frames = []
    for path in paths:
        gray = as_gray(cv2.imread(str(path), cv2.IMREAD_UNCHANGED), "keyframe " + str(path))
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not overwrite grayscale keyframe: %s" % path)
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2 or png_color_type(path) not in (0, 4):
            raise SkillError("saved keyframe is not a native grayscale PNG: %s" % path)
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


def score_peaks(frame, template, mask):
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


def nms(candidates, threshold, distance):
    accepted = []
    squared_distance = distance * distance
    for score, x, y in sorted((item for item in candidates if item[0] >= threshold), reverse=True):
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > squared_distance
               for _, old_x, old_y in accepted):
            accepted.append((score, x, y))
    return accepted


def count_templates(frames, templates):
    """Count distinct NMS-surviving template peaks for every frame."""
    counts = {}
    calibration = {}
    for name in COLUMNS:
        template, mask = templates[name]
        groups = []
        dimensions = []
        for frame in frames:
            peaks, dimension = score_peaks(frame, template, mask)
            groups.append(peaks)
            dimensions.append(dimension)
        all_scores = np.asarray([score for group in groups for score, _, _ in group])
        if not all_scores.size:
            raise SkillError("template matching produced no peaks for " + name)
        # The cutoff is based on the supplied score distribution, while the
        # floor rejects ordinary background correlation. NMS turns nearby
        # responses for a single sprite into one detection.
        threshold = max(0.70, float(np.quantile(all_scores, 0.995)))
        distance = max(1, int(round(max(dimensions) * 0.75)))
        counts[name] = [len(nms(group, threshold, distance)) for group in groups]
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


def validate(paths, expected_count, csv_path=None, frame_id_dir=None):
    if len(paths) != expected_count:
        raise SkillError("published frame count differs from codec-keyframe metadata")
    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 2 or png_color_type(path) not in (0, 4):
            raise SkillError("final frame is not a readable grayscale PNG: %s" % path)
    if csv_path is None:
        return {"ok": True, "frames_checked": len(paths)}
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != HEADER:
        raise SkillError("CSV header is not exactly %r" % HEADER)
    if len(rows) != len(paths) + 1:
        raise SkillError("CSV does not contain exactly one row per final keyframe")
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in paths]
    actual_ids = []
    for row in rows[1:]:
        if len(row) != 4:
            raise SkillError("CSV row does not contain four columns: %r" % row)
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
    video = input_file(config.get("video_path"), "video")
    supplied = config.get("templates")
    if not isinstance(supplied, dict) or set(supplied) != set(COLUMNS):
        raise SkillError("templates must contain exactly coins, enemies, turtles")
    template_paths = {name: input_file(supplied[name], "template " + name) for name in COLUMNS}

    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty filename prefix")
    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # A stale partial run must not be mistaken for a complete delivery.
    clear_numbered_pngs(output_dir, prefix)
    if csv_path.exists():
        csv_path.unlink()

    stage = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    temporary_csv = None
    try:
        expected = codec_keyframe_count(video)
        staged_paths, extraction_method = extract_codec_keyframes(video, stage, prefix, expected)
        frames = overwrite_grayscale(staged_paths)
        templates = {name: load_template(template_paths[name]) for name in COLUMNS}
        counts, calibration = count_templates(frames, templates)
        validate(staged_paths, expected)

        # Publish only the complete staged set, then derive CSV records from
        # precisely that published ordered list.
        for source in staged_paths:
            os.replace(source, output_dir / source.name)
        final_paths = numbered_pngs(output_dir, prefix)
        validate(final_paths, expected)

        records = []
        for index, path in enumerate(final_paths):
            record = {"frame_id": str((frame_id_dir / path.name).resolve())}
            record.update({name: int(counts[name][index]) for name in COLUMNS})
            records.append(record)

        descriptor, temp_name = tempfile.mkstemp(
            prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent)
        )
        os.close(descriptor)
        temporary_csv = Path(temp_name)
        write_csv(temporary_csv, records)
        validate(final_paths, expected, temporary_csv, frame_id_dir)
        os.replace(temporary_csv, csv_path)
        temporary_csv = None
        validation = validate(final_paths, expected, csv_path, frame_id_dir)
        return {
            "ok": True,
            "codec_keyframes": expected,
            "frames": len(final_paths),
            "csv_path": str(csv_path),
            "extraction_method": extraction_method,
            "calibration": calibration,
            "validation": validation,
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if temporary_csv is not None and temporary_csv.exists():
            temporary_csv.unlink()


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    print(json.dumps(output, allow_nan=False))
