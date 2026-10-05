#!/usr/bin/env python3
"""Extract grayscale codec keyframes and count supplied sprite templates.

stdin JSON:
{"video_path": str, "templates": {"coins": str, "enemies": str,
 "turtles": str}, "output_dir": str?, "keyframe_prefix": str?,
 "frame_id_dir": str?, "csv_path": str?}

stdout success:
{"ok": true, "codec_keyframes": int, "frames": int, "csv_path": str,
 "calibration": object, "validation": object}
stdout failure: {"ok": false, "error": str}
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


class SkillError(RuntimeError):
    pass


def checked(command):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=False)
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % command[0]) from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (command[0], detail))
    return result.stdout


def require_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is not a readable regular file: %s" % (label, value))
    return path.resolve()


def codec_key_flags(video):
    text = checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    flags = [line.strip() == "1" for line in text.splitlines() if line.strip()]
    if not flags:
        raise SkillError("ffprobe returned no video frame metadata")
    if not any(flags):
        raise SkillError("ffprobe reported no codec keyframes")
    return flags


def png_number(path, prefix):
    match = re.fullmatch(re.escape(prefix) + r"(\d+)\.png", path.name)
    if not match:
        raise SkillError("unexpected keyframe filename: %s" % path.name)
    return int(match.group(1))


def numbered_pngs(directory, prefix):
    paths = sorted(directory.glob(prefix + "*.png"), key=lambda item: png_number(item, prefix))
    numbers = [png_number(path, prefix) for path in paths]
    if not paths or numbers != list(range(1, len(paths) + 1)):
        raise SkillError("keyframe filenames are not consecutive from 001: %r" % numbers)
    return paths


def remove_existing_keyframes(directory, prefix):
    for path in directory.glob(prefix + "*.png"):
        if path.is_file():
            path.unlink()


def extract_positions(video, stage, prefix, flags):
    """Decode each flagged presentation index to one explicit output PNG.

    Invoking FFmpeg once per selected frame avoids output-vsync and image-sequence
    behavior that can otherwise omit selected frames with unusual timestamps.
    """
    positions = [index for index, is_key in enumerate(flags) if is_key]
    for ordinal, position in enumerate(positions, start=1):
        destination = stage / (prefix + "%03d.png" % ordinal)
        # argv is passed directly, so the backslash is preserved for FFmpeg's
        # filter parser and protects the comma in eq(n, presentation_index).
        selector = "select=eq(n\\,%d)" % position
        checked([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video), "-map", "0:v:0", "-an", "-vf", selector,
            "-vsync", "0", "-frames:v", "1", str(destination),
        ])
        if not destination.is_file() or destination.stat().st_size == 0:
            raise SkillError("FFmpeg did not write selected keyframe %d" % ordinal)
    paths = numbered_pngs(stage, prefix)
    if len(paths) != len(positions):
        raise SkillError("codec keyframe metadata/files disagree: ffprobe=%d, PNGs=%d" %
                         (len(positions), len(paths)))
    return paths


def grayscale_image(path, preserve_alpha_mask=False):
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
        if preserve_alpha_mask and np.any(alpha == 0) and np.any(alpha != 0):
            mask = np.where(alpha > 0, 255, 0).astype(np.uint8)
    else:
        raise SkillError("unsupported image shape %r: %s" % (image.shape, path))
    if gray.dtype != np.uint8:
        gray = cv2.convertScaleAbs(gray)
    return gray, mask


def rewrite_grayscale(paths):
    frames = []
    for path in paths:
        gray, _ = grayscale_image(path)
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not overwrite PNG as grayscale: %s" % path)
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2:
            raise SkillError("saved PNG is not native grayscale: %s" % path)
        frames.append(reopened)
    return frames


def local_peaks(frame, template, mask):
    frame_height, frame_width = frame.shape[:2]
    template_height, template_width = template.shape[:2]
    if min(template_height, template_width) < 2:
        raise SkillError("template is too small for matching")
    if template_height > frame_height or template_width > frame_width:
        raise SkillError("template (%dx%d) exceeds frame (%dx%d)" %
                         (template_width, template_height, frame_width, frame_height))
    if mask is None:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    else:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCORR_NORMED, mask=mask)
    if not np.isfinite(response).all():
        raise SkillError("template response contains non-finite values")
    radius = max(1, int(round(min(template_height, template_width) * 0.30)))
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    maxima = response >= cv2.dilate(response, kernel)
    ys, xs = np.where(maxima)
    return [(float(response[y, x]), int(x), int(y)) for y, x in zip(ys, xs)], max(template_height, template_width)


def suppress(peaks, threshold, distance):
    kept = []
    distance_squared = distance * distance
    for score, x, y in sorted((peak for peak in peaks if peak[0] >= threshold), reverse=True):
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > distance_squared
               for _, old_x, old_y in kept):
            kept.append((score, x, y))
    return kept


def count_templates(frames, templates):
    counts = {}
    calibration = {}
    for name in COLUMNS:
        template, mask = templates[name]
        frame_peaks = []
        scales = []
        for frame in frames:
            peaks, scale = local_peaks(frame, template, mask)
            frame_peaks.append(peaks)
            scales.append(scale)
        scores = np.asarray([score for peaks in frame_peaks for score, _, _ in peaks], dtype=np.float32)
        if scores.size == 0:
            raise SkillError("no local template-match peaks for %s" % name)
        # Keep only the extreme observed peak tail. Exact sprite-template matches
        # remain high while repeated background responses are discarded. The floor
        # prevents a uniformly weak score map from producing detections.
        threshold = max(0.55, float(np.quantile(scores, 0.9995)))
        distance = max(1, int(round(scales[0] * 0.80)))
        per_frame = [len(suppress(peaks, threshold, distance)) for peaks in frame_peaks]
        counts[name] = per_frame
        calibration[name] = {
            "threshold": threshold,
            "suppression_distance_px": distance,
            "detections": int(sum(per_frame)),
        }
    return counts, calibration


def write_csv(path, records):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["frame_id", *COLUMNS], lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def validate(paths, expected_count, csv_path, frame_id_dir):
    if len(paths) != expected_count:
        raise SkillError("final PNG count differs from codec-keyframe count")
    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 2:
            raise SkillError("final image is unreadable or not grayscale: %s" % path)
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header = ["frame_id", *COLUMNS]
    if not rows or rows[0] != header:
        raise SkillError("CSV header is not %r" % header)
    if len(rows) != len(paths) + 1:
        raise SkillError("CSV does not have exactly one data row per frame")
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in paths]
    for row in rows[1:]:
        if len(row) != 4 or any(not re.fullmatch(r"\d+", value or "") for value in row[1:]):
            raise SkillError("CSV contains an invalid count record: %r" % row)
    if [row[0] for row in rows[1:]] != expected_ids:
        raise SkillError("CSV frame IDs do not exactly match final ordered PNGs")
    return {"ok": True, "frames_checked": len(paths), "csv_rows_checked": len(paths)}


def main(config):
    if IMPORT_ERROR:
        raise SkillError("OpenCV and NumPy are required: " + IMPORT_ERROR)
    if not isinstance(config, dict):
        raise SkillError("stdin JSON must be an object")
    video = require_file(config.get("video_path"), "video")
    template_spec = config.get("templates")
    if not isinstance(template_spec, dict) or set(template_spec) != set(COLUMNS):
        raise SkillError("templates must contain exactly coins, enemies, turtles")
    template_paths = {name: require_file(template_spec[name], "template " + name) for name in COLUMNS}

    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty basename prefix")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    stage = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    fd, temporary_csv_name = tempfile.mkstemp(prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent))
    os.close(fd)
    staged_csv = Path(temporary_csv_name)
    try:
        flags = codec_key_flags(video)
        expected_count = sum(flags)
        staged_paths = extract_positions(video, stage, prefix, flags)
        frames = rewrite_grayscale(staged_paths)
        templates = {name: grayscale_image(path, preserve_alpha_mask=True)
                     for name, path in template_paths.items()}
        counts, calibration = count_templates(frames, templates)
        records = []
        for index, staged_path in enumerate(staged_paths):
            record = {"frame_id": str((frame_id_dir / staged_path.name).resolve())}
            record.update({name: int(counts[name][index]) for name in COLUMNS})
            records.append(record)
        write_csv(staged_csv, records)
        validate(staged_paths, expected_count, staged_csv, frame_id_dir)

        # Publication occurs only after complete staged image and CSV validation.
        remove_existing_keyframes(output_dir, prefix)
        if csv_path.exists():
            if not csv_path.is_file():
                raise SkillError("CSV destination is not a regular file: %s" % csv_path)
            csv_path.unlink()
        final_paths = []
        for source in staged_paths:
            destination = output_dir / source.name
            os.replace(source, destination)
            final_paths.append(destination)
        os.replace(staged_csv, csv_path)
        validation = validate(final_paths, expected_count, csv_path, frame_id_dir)
        return {
            "ok": True,
            "codec_keyframes": expected_count,
            "frames": len(final_paths),
            "csv_path": str(csv_path),
            "calibration": calibration,
            "validation": validation,
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if staged_csv.exists():
            staged_csv.unlink()


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = main(payload)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    print(json.dumps(result, allow_nan=False))
