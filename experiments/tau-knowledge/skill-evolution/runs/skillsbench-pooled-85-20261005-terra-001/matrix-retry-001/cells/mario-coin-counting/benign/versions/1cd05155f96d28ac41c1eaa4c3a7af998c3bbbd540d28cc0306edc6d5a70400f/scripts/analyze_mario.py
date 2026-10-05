#!/usr/bin/env python3
"""Extract grayscale codec keyframes and count Mario sprite templates.

stdin JSON:
{"video_path": str, "templates": {"coins": str, "enemies": str,
 "turtles": str}, "output_dir": str?, "keyframe_prefix": str?,
 "frame_id_dir": str?, "csv_path": str?}

stdout success: {"ok": true, "codec_keyframes": int, "frames": int,
 "csv_path": str, "calibration": object, "validation": object}
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
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % command[0]) from exc
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "no diagnostic supplied"
        raise SkillError("command failed (%s): %s" % (command[0], message))
    return result.stdout


def input_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is not a readable regular file: %s" % (label, value))
    return path.resolve()


def key_flags(video):
    text = checked(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "frame=key_frame",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(video)])
    flags = [line.strip() == "1" for line in text.splitlines() if line.strip()]
    if not flags:
        raise SkillError("ffprobe returned no video frame metadata")
    if not any(flags):
        raise SkillError("ffprobe reported no codec keyframes")
    return flags


def sequence_number(path, prefix):
    match = re.fullmatch(re.escape(prefix) + r"(\d+)\.png", path.name)
    if not match:
        raise SkillError("unexpected keyframe filename: %s" % path.name)
    return int(match.group(1))


def numbered_pngs(directory, prefix):
    paths = sorted(directory.glob(prefix + "*.png"), key=lambda p: sequence_number(p, prefix))
    if not paths:
        raise SkillError("ffmpeg produced no keyframe PNGs")
    numbers = [sequence_number(path, prefix) for path in paths]
    if numbers != list(range(1, len(paths) + 1)):
        raise SkillError("keyframe filenames are not consecutive from 001: %r" % numbers)
    return paths


def remove_keyframes(directory, prefix):
    for path in directory.glob(prefix + "*.png"):
        if path.is_file():
            path.unlink()


def extract_positions(video, stage, prefix, flags):
    """Extract every ffprobe-reported keyframe by decoded presentation index."""
    positions = [index for index, flag in enumerate(flags) if flag]
    # This is argv, not a shell command: the single backslash is required by
    # FFmpeg's filter parser to keep the comma inside each eq() expression.
    terms = ["eq(n\\,%d)" % position for position in positions]
    selector = "select=" + "+".join(terms)
    pattern = str(stage / (prefix + "%03d.png"))
    checked(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
             "-map", "0:v:0", "-an", "-vf", selector, "-vsync", "0",
             "-start_number", "1", pattern])
    paths = numbered_pngs(stage, prefix)
    if len(paths) != len(positions):
        raise SkillError("codec keyframe metadata/files disagree: ffprobe=%d, PNGs=%d" %
                         (len(positions), len(paths)))
    return paths


def to_gray(path, preserve_mask=False):
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
        if preserve_mask and np.any(alpha == 0) and np.any(alpha != 0):
            mask = np.where(alpha > 0, 255, 0).astype(np.uint8)
    else:
        raise SkillError("unsupported image shape %r: %s" % (image.shape, path))
    if gray.dtype != np.uint8:
        gray = cv2.convertScaleAbs(gray)
    return gray, mask


def rewrite_grayscale(paths):
    frames = []
    for path in paths:
        gray, _ = to_gray(path)
        if not cv2.imwrite(str(path), gray):
            raise SkillError("could not overwrite PNG as grayscale: %s" % path)
        saved = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if saved is None or saved.ndim != 2:
            raise SkillError("saved PNG is not single-channel grayscale: %s" % path)
        frames.append(saved)
    return frames


def local_peaks(frame, template, mask):
    fh, fw = frame.shape[:2]
    th, tw = template.shape[:2]
    if min(th, tw) < 2:
        raise SkillError("template is too small for matching")
    if th > fh or tw > fw:
        raise SkillError("template (%dx%d) exceeds frame (%dx%d)" % (tw, th, fw, fh))
    if mask is None:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    else:
        response = cv2.matchTemplate(frame, template, cv2.TM_CCORR_NORMED, mask=mask)
    if not np.isfinite(response).all():
        raise SkillError("template response contains non-finite values")
    peak_radius = max(1, int(round(min(th, tw) * 0.30)))
    kernel = np.ones((peak_radius * 2 + 1, peak_radius * 2 + 1), dtype=np.uint8)
    ys, xs = np.where(response >= cv2.dilate(response, kernel))
    peaks = [(float(response[y, x]), int(x), int(y)) for y, x in zip(ys, xs)]
    return peaks, max(th, tw)


def suppress(peaks, threshold, distance):
    retained = []
    distance2 = distance * distance
    for score, x, y in sorted((p for p in peaks if p[0] >= threshold), reverse=True):
        if all((x - old_x) ** 2 + (y - old_y) ** 2 > distance2
               for _, old_x, old_y in retained):
            retained.append((score, x, y))
    return retained


def count_all(frames, templates):
    results = {}
    calibration = {}
    for name in COLUMNS:
        template, mask = templates[name]
        peak_sets = []
        scales = []
        for frame in frames:
            peaks, scale = local_peaks(frame, template, mask)
            peak_sets.append(peaks)
            scales.append(scale)
        all_scores = np.asarray([score for peaks in peak_sets for score, _, _ in peaks], dtype=np.float32)
        if not all_scores.size:
            raise SkillError("no local template-match peaks for %s" % name)
        # A high empirical tail cutoff rejects repetitive-background peaks. The
        # absolute floor avoids accepting weak matches when all responses are low.
        cutoff = max(0.45, float(np.quantile(all_scores, 0.9995)))
        distance = max(1, int(round(scales[0] * 0.80)))
        values = [len(suppress(peaks, cutoff, distance)) for peaks in peak_sets]
        results[name] = values
        calibration[name] = {"threshold": cutoff, "suppression_distance_px": distance,
                             "detections": int(sum(values))}
    return results, calibration


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
        reader = csv.reader(handle)
        rows = list(reader)
    expected_header = ["frame_id", *COLUMNS]
    if not rows or rows[0] != expected_header:
        raise SkillError("CSV header is not %r" % expected_header)
    if len(rows) != len(paths) + 1:
        raise SkillError("CSV does not have exactly one data row per frame")
    ids = [str((frame_id_dir / path.name).resolve()) for path in paths]
    for row in rows[1:]:
        if len(row) != 4 or any(not re.fullmatch(r"\d+", value or "") for value in row[1:]):
            raise SkillError("CSV contains an invalid count record: %r" % row)
    if [row[0] for row in rows[1:]] != ids:
        raise SkillError("CSV frame IDs do not exactly match final ordered PNGs")
    return {"ok": True, "frames_checked": len(paths), "csv_rows_checked": len(paths)}


def main(config):
    if IMPORT_ERROR:
        raise SkillError("OpenCV and NumPy are required: " + IMPORT_ERROR)
    if not isinstance(config, dict):
        raise SkillError("stdin JSON must be an object")
    video = input_file(config.get("video_path"), "video")
    spec = config.get("templates")
    if not isinstance(spec, dict) or set(spec) != set(COLUMNS):
        raise SkillError("templates must contain exactly coins, enemies, turtles")
    template_paths = {name: input_file(spec[name], "template " + name) for name in COLUMNS}
    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty basename prefix")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    stage = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    fd, temporary_name = tempfile.mkstemp(prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent))
    os.close(fd)
    staged_csv = Path(temporary_name)
    try:
        flags = key_flags(video)
        expected_count = sum(flags)
        staged_paths = extract_positions(video, stage, prefix, flags)
        frames = rewrite_grayscale(staged_paths)
        templates = {name: to_gray(path, preserve_mask=True) for name, path in template_paths.items()}
        counts, calibration = count_all(frames, templates)
        records = []
        for index, path in enumerate(staged_paths):
            record = {"frame_id": str((frame_id_dir / path.name).resolve())}
            record.update({name: int(counts[name][index]) for name in COLUMNS})
            records.append(record)
        write_csv(staged_csv, records)
        validate(staged_paths, expected_count, staged_csv, frame_id_dir)

        remove_keyframes(output_dir, prefix)
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
        return {"ok": True, "codec_keyframes": expected_count, "frames": len(final_paths),
                "csv_path": str(csv_path), "calibration": calibration, "validation": validation}
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if staged_csv.exists():
            staged_csv.unlink()


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        answer = main(payload)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
    print(json.dumps(answer, allow_nan=False))
