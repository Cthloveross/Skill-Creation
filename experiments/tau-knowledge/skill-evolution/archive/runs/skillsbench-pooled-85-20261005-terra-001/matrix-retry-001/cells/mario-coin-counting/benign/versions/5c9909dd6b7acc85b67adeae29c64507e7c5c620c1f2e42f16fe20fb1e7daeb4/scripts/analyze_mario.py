#!/usr/bin/env python3
"""Extract, grayscale, and count codec keyframes.

stdin JSON schema:
{
  "video_path": "path",
  "templates": {"coins": "path", "enemies": "path", "turtles": "path"},
  "output_dir": "path optional",
  "keyframe_prefix": "basename-prefix optional",
  "frame_id_dir": "path optional",
  "csv_path": "path optional"
}

stdout success schema:
{"ok": true, "codec_keyframes": int, "frames": int, "csv_path": str,
 "calibration": object, "validation": object}
stdout failure schema: {"ok": false, "error": str}
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
except Exception as exc:  # reported through the normal JSON failure contract
    cv2 = None
    np = None
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = None

COLUMNS = ("coins", "enemies", "turtles")
HEADER = ["frame_id", *COLUMNS]


class SkillError(RuntimeError):
    pass


def run_checked(command):
    """Run a subprocess without shell interpolation and return stdout."""
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False,
        )
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % command[0]) from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (command[0], detail))
    return result.stdout


def readable_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is not a readable regular file: %s" % (label, value))
    return path.resolve()


def codec_keyframe_count(video):
    output = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    flags = [line.strip() for line in output.splitlines() if line.strip()]
    if not flags:
        raise SkillError("ffprobe returned no video-frame metadata")
    count = sum(value == "1" for value in flags)
    if not count:
        raise SkillError("ffprobe reported no codec keyframes")
    return count


def numbered_pngs(directory, prefix):
    pattern = re.compile(re.escape(prefix) + r"(\d+)\.png$")
    numbered = []
    for path in directory.glob(prefix + "*.png"):
        match = pattern.fullmatch(path.name)
        if match and path.is_file():
            numbered.append((int(match.group(1)), path))
    numbered.sort(key=lambda item: item[0])
    indices = [index for index, _ in numbered]
    if not numbered or indices != list(range(1, len(numbered) + 1)):
        raise SkillError("extracted keyframe names are not consecutive from 001: %r" % indices)
    return [path for _, path in numbered]


def clear_matching_pngs(directory, prefix):
    for path in directory.glob(prefix + "*.png"):
        if path.is_file():
            path.unlink()


def extract_keyframes(video, stage, prefix, expected_count):
    """Extract all codec keyframes in presentation order in a single FFmpeg pass.

    ``-skip_frame nokey`` asks the video decoder to output only codec keyframes.
    It avoids image-sequence timestamp/vsync duplication and is verified against
    ffprobe afterwards. Some decoder builds handle this option differently, so a
    decoded-frame key-flag selection fallback is included.
    """
    pattern = str(stage / (prefix + "%03d.png"))
    primary = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-skip_frame", "nokey", "-i", str(video), "-map", "0:v:0", "-an",
        "-vf", "format=gray", "-vsync", "0", "-pix_fmt", "gray", pattern,
    ]
    run_checked(primary)
    try:
        paths = numbered_pngs(stage, prefix)
    except SkillError:
        paths = []
    if len(paths) == expected_count:
        return paths

    # Retry from a clean stage using AVFrame's decoded key flag. The escaped comma
    # is retained because FFmpeg's filter-expression parser uses comma separators.
    clear_matching_pngs(stage, prefix)
    fallback = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-map", "0:v:0", "-an",
        "-vf", "select=eq(key\\,1),format=gray", "-vsync", "0",
        "-pix_fmt", "gray", pattern,
    ]
    run_checked(fallback)
    paths = numbered_pngs(stage, prefix)
    if len(paths) != expected_count:
        raise SkillError(
            "codec keyframe metadata/files disagree after extraction: ffprobe=%d, PNGs=%d"
            % (expected_count, len(paths))
        )
    return paths


def read_gray(path, label):
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise SkillError("could not read %s: %s" % (label, path))
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 1:
        gray = image[:, :, 0]
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        raise SkillError("unsupported %s shape %r: %s" % (label, image.shape, path))
    if gray.dtype != np.uint8:
        gray = cv2.convertScaleAbs(gray)
    return gray, image


def ensure_native_grayscale(paths):
    """Reopen and, if necessary, overwrite images as one-channel PNGs."""
    frames = []
    for path in paths:
        gray, original = read_gray(path, "keyframe")
        if original.ndim != 2:
            if not cv2.imwrite(str(path), gray):
                raise SkillError("could not overwrite keyframe as grayscale: %s" % path)
        reopened = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if reopened is None or reopened.ndim != 2:
            raise SkillError("saved keyframe is not native grayscale: %s" % path)
        frames.append(reopened)
    return frames


def load_template(path):
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise SkillError("could not read template: %s" % path)
    gray, _ = read_gray(path, "template")
    mask = None
    if raw.ndim == 3 and raw.shape[2] == 4:
        alpha = raw[:, :, 3]
        if np.any(alpha == 0) and np.any(alpha > 0):
            mask = np.where(alpha > 0, 255, 0).astype(np.uint8)
    if min(gray.shape[:2]) < 2:
        raise SkillError("template is too small: %s" % path)
    return gray, mask


def local_peaks(frame, template, mask):
    height, width = frame.shape[:2]
    template_height, template_width = template.shape[:2]
    if template_height > height or template_width > width:
        raise SkillError("template (%dx%d) exceeds keyframe (%dx%d)" % (
            template_width, template_height, width, height))
    if mask is None:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    else:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCORR_NORMED, mask=mask)
    if not np.isfinite(response).all():
        raise SkillError("template response contains non-finite scores")
    radius = max(1, int(round(min(template_height, template_width) * 0.25)))
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    maxima = response >= cv2.dilate(response, kernel)
    ys, xs = np.where(maxima)
    peaks = [(float(response[y, x]), int(x), int(y)) for y, x in zip(ys, xs)]
    return peaks, max(template_height, template_width)


def calibrate_threshold(all_peaks):
    """Derive a high cutoff from current-template/frame local peak scores."""
    scores = np.asarray([score for peaks in all_peaks for score, _, _ in peaks], dtype=np.float32)
    if scores.size == 0:
        raise SkillError("template matching produced no local peaks")
    # A high observed quantile rejects broad background responses. The floor makes
    # the result conservative if a low-contrast response distribution is present.
    return max(0.65, float(np.quantile(scores, 0.9985)))


def nonmaximum_suppress(peaks, threshold, distance):
    chosen = []
    limit = distance * distance
    for score, x, y in sorted((p for p in peaks if p[0] >= threshold), reverse=True):
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > limit
               for _, old_x, old_y in chosen):
            chosen.append((score, x, y))
    return chosen


def count_all(frames, templates):
    counts = {}
    calibration = {}
    for name in COLUMNS:
        template, mask = templates[name]
        peak_sets = []
        scales = []
        for frame in frames:
            peaks, scale = local_peaks(frame, template, mask)
            peak_sets.append(peaks)
            scales.append(scale)
        threshold = calibrate_threshold(peak_sets)
        distance = max(1, int(round(max(scales) * 0.75)))
        per_frame = [len(nonmaximum_suppress(peaks, threshold, distance)) for peaks in peak_sets]
        counts[name] = per_frame
        calibration[name] = {
            "threshold": threshold,
            "suppression_distance_px": distance,
            "detections": int(sum(per_frame)),
        }
    return counts, calibration


def write_csv(path, records):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def validate(paths, expected_count, csv_path, frame_id_dir):
    if len(paths) != expected_count:
        raise SkillError("final PNG count differs from codec keyframe count")
    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 2:
            raise SkillError("final keyframe is unreadable or not grayscale: %s" % path)
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != HEADER:
        raise SkillError("CSV header is not %r" % HEADER)
    if len(rows) != len(paths) + 1:
        raise SkillError("CSV does not contain exactly one data row per keyframe")
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in paths]
    actual_ids = []
    for row in rows[1:]:
        if len(row) != 4:
            raise SkillError("CSV record does not have four columns: %r" % row)
        if any(not re.fullmatch(r"\d+", value or "") for value in row[1:]):
            raise SkillError("CSV record has an invalid count: %r" % row)
        actual_ids.append(row[0])
    if actual_ids != expected_ids:
        raise SkillError("CSV frame IDs do not match final numbered keyframes in order")
    return {"ok": True, "frames_checked": len(paths), "csv_rows_checked": len(paths)}


def main(config):
    if IMPORT_ERROR:
        raise SkillError("OpenCV and NumPy are required: " + IMPORT_ERROR)
    if not isinstance(config, dict):
        raise SkillError("stdin JSON must be an object")
    video = readable_file(config.get("video_path"), "video")
    templates_value = config.get("templates")
    if not isinstance(templates_value, dict) or set(templates_value) != set(COLUMNS):
        raise SkillError("templates must contain exactly coins, enemies, turtles")
    template_paths = {name: readable_file(templates_value[name], "template " + name)
                      for name in COLUMNS}

    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty filename prefix")
    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    stage = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    fd, csv_temp_name = tempfile.mkstemp(prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent))
    os.close(fd)
    staged_csv = Path(csv_temp_name)
    try:
        expected_count = codec_keyframe_count(video)
        staged_paths = extract_keyframes(video, stage, prefix, expected_count)
        frames = ensure_native_grayscale(staged_paths)
        templates = {name: load_template(path) for name, path in template_paths.items()}
        counts, calibration = count_all(frames, templates)

        records = []
        for index, frame_path in enumerate(staged_paths):
            record = {"frame_id": str((frame_id_dir / frame_path.name).resolve())}
            record.update({name: int(counts[name][index]) for name in COLUMNS})
            records.append(record)
        write_csv(staged_csv, records)
        validate(staged_paths, expected_count, staged_csv, frame_id_dir)

        # Publish only the fully validated staged set. Existing matching images and
        # CSV are replaced together only after extraction/counting has succeeded.
        clear_matching_pngs(output_dir, prefix)
        for source in staged_paths:
            os.replace(source, output_dir / source.name)
        os.replace(staged_csv, csv_path)
        final_paths = numbered_pngs(output_dir, prefix)
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
