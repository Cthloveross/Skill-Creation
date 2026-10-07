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


def probe_codec_keyframe_flags(video):
    """Return one key-frame flag per decoded video frame in presentation order."""
    raw = run_checked([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    flags = [line.strip() == "1" for line in raw.splitlines() if line.strip()]
    if not flags:
        raise SkillError("ffprobe returned no video-frame metadata")
    if not any(flags):
        raise SkillError("ffprobe found no codec keyframes in the video")
    return flags


def frame_number(path, prefix):
    match = re.fullmatch(re.escape(prefix) + r"(\d+)\.png", path.name)
    if not match:
        raise SkillError("unexpected keyframe filename: %s" % path)
    return int(match.group(1))


def list_keyframes(output_dir, prefix):
    paths = list(output_dir.glob(prefix + "*.png"))
    if not paths:
        raise SkillError("ffmpeg wrote no keyframe PNG files")
    paths.sort(key=lambda item: frame_number(item, prefix))
    numbers = [frame_number(path, prefix) for path in paths]
    if numbers != list(range(1, len(paths) + 1)):
        raise SkillError("keyframes are not consecutively numbered from 001: %r" % numbers)
    return paths


def clear_keyframes(output_dir, prefix):
    for path in output_dir.glob(prefix + "*.png"):
        if path.is_file():
            path.unlink()


def ffmpeg_extract(video, output_dir, prefix, selector):
    """Extract selected decoded frames without rate conversion or duplication."""
    pattern = str(output_dir / (prefix + "%03d.png"))
    run_checked([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-map", "0:v:0", "-an", "-vf", selector, "-vsync", "0",
        "-start_number", "1", pattern,
    ])
    return list_keyframes(output_dir, prefix)


def extract_codec_keyframes(video, output_dir, prefix, flags):
    """Extract the exact set reported by ffprobe's codec key-frame flags.

    The primary filter examines decoded frame key flags directly. A positional
    fallback is deliberately retained for FFmpeg builds whose filter key flag
    differs from their ffprobe reporting; the fallback positions come from the
    same metadata stream used to define the required output count.
    """
    expected_count = sum(flags)
    try:
        paths = ffmpeg_extract(video, output_dir, prefix, r"select=eq(key\,1)")
    except SkillError:
        clear_keyframes(output_dir, prefix)
        raise
    if len(paths) == expected_count:
        return paths

    clear_keyframes(output_dir, prefix)
    positions = [index for index, flag in enumerate(flags) if flag]
    expression = "+".join("eq(n\\,%d)" % index for index in positions)
    try:
        paths = ffmpeg_extract(video, output_dir, prefix, "select=" + expression)
    except SkillError:
        clear_keyframes(output_dir, prefix)
        raise
    if len(paths) != expected_count:
        clear_keyframes(output_dir, prefix)
        raise SkillError(
            "keyframe metadata/files disagree after key-flag and positional extraction: "
            "ffprobe=%d, PNGs=%d" % (expected_count, len(paths))
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
    radius = max(1, int(round(min(th, tw) * 0.45)))
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    local = response >= cv2.dilate(response, kernel)
    ys, xs = np.where(local)
    return [(float(response[y, x]), int(x), int(y)) for y, x in zip(ys, xs)], radius


def calibrate_threshold(peak_sets):
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
    counts = {}
    calibration = {}
    for name in COUNT_COLUMNS:
        template, mask = templates[name]
        peak_sets, radii = [], []
        for frame in frames:
            peaks, radius = response_peaks(frame, template, mask)
            peak_sets.append(peaks)
            radii.append(radius)
        threshold, otsu, tail = calibrate_threshold(peak_sets)
        per_frame = [len(suppress(peaks, threshold, radius))
                     for peaks, radius in zip(peak_sets, radii)]
        counts[name] = per_frame
        calibration[name] = {
            "threshold": threshold,
            "otsu_peak_threshold": otsu,
            "peak_tail_threshold": tail,
            "suppression_radius_px": radii[0],
            "detections": int(sum(per_frame)),
        }
    return counts, calibration


def write_csv(csv_path, records):
    columns = ["frame_id"] + list(COUNT_COLUMNS)
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


def remove_final_outputs(output_dir, prefix, csv_path):
    clear_keyframes(output_dir, prefix)
    if csv_path.exists():
        if not csv_path.is_file():
            raise SkillError("CSV destination exists but is not a regular file: %s" % csv_path)
        csv_path.unlink()


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
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    stage_dir = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    descriptor, csv_temp_name = tempfile.mkstemp(
        prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent)
    )
    os.close(descriptor)
    staged_csv = Path(csv_temp_name)
    try:
        flags = probe_codec_keyframe_flags(video)
        codec_count = sum(flags)
        staged_paths = extract_codec_keyframes(video, stage_dir, prefix, flags)
        frames = grayscale_frames_in_place(staged_paths)
        templates = {name: gray_and_mask(path) for name, path in template_paths.items()}
        counts, calibration = count_templates(frames, templates)
        records = []
        for index, path in enumerate(staged_paths):
            row = {"frame_id": str((frame_id_dir / path.name).resolve())}
            for name in COUNT_COLUMNS:
                row[name] = counts[name][index]
            records.append(row)
        write_csv(staged_csv, records)
        validate(staged_paths, codec_count, staged_csv, frame_id_dir)

        remove_final_outputs(output_dir, prefix, csv_path)
        final_paths = []
        for staged_path in staged_paths:
            final_path = output_dir / staged_path.name
            os.replace(staged_path, final_path)
            final_paths.append(final_path)
        os.replace(staged_csv, csv_path)
        validation = validate(final_paths, codec_count, csv_path, frame_id_dir)
        return {"ok": True, "codec_keyframes": codec_count, "frames": len(final_paths),
                "csv_path": str(csv_path), "calibration": calibration, "validation": validation}
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
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
