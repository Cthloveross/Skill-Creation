#!/usr/bin/env python3
"""Extract codec keyframes, convert them to grayscale, count templates, and write CSV.

Input JSON:
{
  "video_path": "/path/video.mp4",
  "templates": {"coins": "/path/coin.png", "enemies": "/path/enemy.png",
                "turtles": "/path/turtle.png"},
  "output_dir": "/optional/output",
  "keyframe_prefix": "optional_prefix_",
  "frame_id_dir": "/optional/csv/frame/id/directory",
  "csv_path": "/optional/counting_results.csv"
}

Output JSON success:
{"ok":true,"codec_keyframes":int,"frames":int,"csv_path":str,
 "extraction_method":str,"calibration":object,"validation":object}
Output JSON failure: {"ok":false,"error":str}
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
except Exception as exc:
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


def keyframe_metadata(video):
    """Return keyframe count plus zero-based decoded presentation indexes."""
    text = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    flags = [line.strip() for line in text.splitlines() if line.strip()]
    if not flags:
        raise SkillError("ffprobe returned no video-frame metadata")
    indexes = [index for index, value in enumerate(flags) if value == "1"]
    if not indexes:
        raise SkillError("ffprobe reported no codec keyframes")
    return len(indexes), indexes


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


def extract_command(video, destination_pattern, mode, indexes=None):
    """Return a no-shell FFmpeg command for a codec-keyframe extraction mode."""
    common = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    ]
    if mode == "skip_frame_nokey":
        # This decoder option is an input option. It discards non-key frames
        # before output and avoids time/FPS sampling entirely.
        return common + [
            "-skip_frame", "nokey", "-i", str(video), "-map", "0:v:0", "-an",
            "-vsync", "0", "-start_number", "1", "-pix_fmt", "gray",
            destination_pattern,
        ]
    if mode == "ffprobe_indexes":
        if not indexes:
            raise SkillError("no ffprobe indexes supplied for extraction fallback")
        # Quotes are intentionally part of the filter argument. They make
        # commas expression syntax rather than filter-chain separators even
        # though subprocess does not involve a shell.
        terms = "+".join("eq(n,%d)" % index for index in indexes)
        selector = "select='%s'" % terms
        return common + [
            "-i", str(video), "-map", "0:v:0", "-an", "-vf", selector,
            "-vsync", "0", "-start_number", "1", "-pix_fmt", "gray",
            destination_pattern,
        ]
    raise SkillError("unknown extraction mode: %s" % mode)


def extract_keyframes(video, stage, prefix, expected_count, indexes):
    errors = []
    target = str(stage / (prefix + "%03d.png"))
    for mode in ("skip_frame_nokey", "ffprobe_indexes"):
        clear_numbered_pngs(stage, prefix)
        try:
            run_checked(extract_command(video, target, mode, indexes))
            paths = numbered_pngs(stage, prefix)
            if len(paths) == expected_count:
                return paths, mode
            errors.append("%s wrote %d PNGs (expected %d)" % (mode, len(paths), expected_count))
        except SkillError as exc:
            errors.append("%s: %s" % (mode, exc))
    raise SkillError(
        "codec keyframe extraction does not match ffprobe metadata (%d): %s"
        % (expected_count, "; ".join(errors))
    )


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
    """Return PNG IHDR color type, enough to assert native grayscale output."""
    data = path.read_bytes()
    if len(data) < 29 or not data.startswith(PNG_SIGNATURE):
        raise SkillError("saved keyframe is not a readable PNG: %s" % path)
    if data[12:16] != b"IHDR" or data[8:12] != b"\x00\x00\x00\x0d":
        raise SkillError("saved keyframe lacks a valid PNG IHDR: %s" % path)
    return data[25]


def ensure_native_grayscale(paths):
    frames = []
    for path in paths:
        original = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        gray = as_gray(original, "keyframe " + str(path))
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not write grayscale keyframe: %s" % path)
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2:
            raise SkillError("reopened keyframe is not one-channel grayscale: %s" % path)
        if png_color_type(path) not in (0, 4):
            raise SkillError("saved PNG is not native grayscale: %s" % path)
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


def peak_candidates(frame, template, mask):
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
    neighborhood = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    local = scores >= cv2.dilate(scores, neighborhood)
    ys, xs = np.where(local)
    return [(float(scores[y, x]), int(x), int(y)) for y, x in zip(ys, xs)], max(height, width)


def suppress(candidates, threshold, distance):
    accepted = []
    squared = distance * distance
    for score, x, y in sorted((item for item in candidates if item[0] >= threshold), reverse=True):
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > squared for _, old_x, old_y in accepted):
            accepted.append((score, x, y))
    return accepted


def count_objects(frames, templates):
    counts, calibration = {}, {}
    for name in COLUMNS:
        template, mask = templates[name]
        candidates_per_frame = []
        scales = []
        for frame in frames:
            candidates, scale = peak_candidates(frame, template, mask)
            candidates_per_frame.append(candidates)
            scales.append(scale)
        all_scores = np.asarray([score for group in candidates_per_frame for score, _, _ in group])
        if all_scores.size == 0:
            raise SkillError("no local template-match peaks for " + name)
        # The quantile adapts to current templates/frames while the floor
        # prevents ordinary background texture from becoming detections.
        threshold = max(0.65, float(np.quantile(all_scores, 0.9985)))
        distance = max(1, int(round(max(scales) * 0.75)))
        values = [len(suppress(group, threshold, distance)) for group in candidates_per_frame]
        counts[name] = values
        calibration[name] = {"threshold": threshold, "suppression_distance_px": distance}
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
    observed_ids = []
    for row in rows[1:]:
        if len(row) != 4:
            raise SkillError("CSV row does not have four columns: %r" % row)
        if any(not re.fullmatch(r"\d+", value or "") for value in row[1:]):
            raise SkillError("CSV count is not a non-negative integer: %r" % row)
        observed_ids.append(row[0])
    if observed_ids != expected_ids:
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

    # Never permit a previous partial run to look like the result of this run.
    clear_numbered_pngs(output_dir, prefix)
    if csv_path.exists():
        csv_path.unlink()

    stage = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    temporary_csv = None
    try:
        expected_count, indexes = keyframe_metadata(video)
        staged_paths, method = extract_keyframes(video, stage, prefix, expected_count, indexes)
        frames = ensure_native_grayscale(staged_paths)
        templates = {name: load_template(template_paths[name]) for name in COLUMNS}
        counts, calibration = count_objects(frames, templates)

        # Publish every validated image first. The CSV is constructed from the
        # corresponding final paths and is published only after they exist.
        for source in staged_paths:
            os.replace(source, output_dir / source.name)
        final_paths = numbered_pngs(output_dir, prefix)
        if len(final_paths) != expected_count:
            raise SkillError("published keyframe set is incomplete")

        records = []
        for index, path in enumerate(final_paths):
            record = {"frame_id": str((frame_id_dir / path.name).resolve())}
            record.update({name: int(counts[name][index]) for name in COLUMNS})
            records.append(record)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent))
        os.close(descriptor)
        temporary_csv = Path(temporary_name)
        write_csv(temporary_csv, records)
        validate(final_paths, expected_count, temporary_csv, frame_id_dir)
        os.replace(temporary_csv, csv_path)
        temporary_csv = None
        validation = validate(final_paths, expected_count, csv_path, frame_id_dir)
        return {
            "ok": True,
            "codec_keyframes": expected_count,
            "frames": len(final_paths),
            "csv_path": str(csv_path),
            "extraction_method": method,
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
