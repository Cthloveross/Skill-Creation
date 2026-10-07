#!/usr/bin/env python3
"""Extract codec keyframes, convert them to grayscale, count templates, and write CSV.

Input JSON:
{
  "video_path": "/path/video.mp4",
  "templates": {"coins": "/path/coin.png", "enemies": "/path/enemy.png", "turtles": "/path/turtle.png"},
  "output_dir": "/optional/output-dir",
  "keyframe_prefix": "optional_prefix_",
  "frame_id_dir": "/optional/csv-frame-id-dir",
  "csv_path": "/optional/counting_results.csv"
}

Output JSON is either a success report with ok=true or {"ok": false, "error": "..."}.
"""
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

COLUMNS = ("coins", "enemies", "turtles")
HEADER = ["frame_id", *COLUMNS]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class SkillError(RuntimeError):
    pass


def run(argv, binary=False):
    """Run a command without a shell, returning stdout or a useful failure."""
    try:
        completed = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % argv[0]) from exc
    if completed.returncode:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        stdout = completed.stdout.decode("utf-8", "replace").strip()
        raise SkillError(
            "command failed (%s): %s" % (argv[0], stderr or stdout or "no diagnostic supplied")
        )
    return completed.stdout if binary else completed.stdout.decode("utf-8", "replace")


def require_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is not a readable regular file: %s" % (label, value))
    return path.resolve()


def codec_keyframe_positions(video):
    """Return presentation-order decoded-frame indexes whose metadata flag is key_frame."""
    text = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    flags = [line.strip() for line in text.splitlines() if line.strip()]
    if not flags or any(flag not in ("0", "1") for flag in flags):
        raise SkillError("ffprobe returned invalid or empty frame keyframe metadata")
    positions = [index for index, flag in enumerate(flags) if flag == "1"]
    if not positions:
        raise SkillError("ffprobe reported no codec keyframes")
    return positions


def png_color_type(path):
    data = path.read_bytes()
    if len(data) < 29 or not data.startswith(PNG_SIGNATURE):
        raise SkillError("not a readable PNG: %s" % path)
    if data[8:12] != b"\x00\x00\x00\x0d" or data[12:16] != b"IHDR":
        raise SkillError("PNG lacks a valid IHDR: %s" % path)
    return data[25]


def numbered_frames(directory, prefix, allow_empty=False):
    matcher = re.compile(re.escape(prefix) + r"(\d+)\.png$")
    found = []
    for path in directory.glob(prefix + "*.png"):
        match = matcher.fullmatch(path.name)
        if match and path.is_file():
            found.append((int(match.group(1)), path))
    found.sort(key=lambda item: item[0])
    indexes = [index for index, _ in found]
    if (not allow_empty and not found) or indexes != list(range(1, len(found) + 1)):
        raise SkillError("keyframe names are not consecutive from 001: %r" % indexes)
    return [path for _, path in found]


def remove_stale_outputs(output_dir, prefix, csv_path):
    matcher = re.compile(re.escape(prefix) + r"\d+\.png$")
    for path in output_dir.glob(prefix + "*.png"):
        if path.is_file() and matcher.fullmatch(path.name):
            path.unlink()
    if csv_path.exists():
        if not csv_path.is_file():
            raise SkillError("CSV output path exists but is not a regular file: %s" % csv_path)
        csv_path.unlink()


def extract_one_codec_keyframe(video, decoded_index, output_path):
    """Write exactly one known decoded frame as an intrinsically grayscale PNG.

    Separate one-image operations avoid the partial multi-image extraction that can
    otherwise leave a prefix of the requested keyframe sequence on disk.
    """
    selector = "select=eq(n\\,%d),format=gray" % decoded_index
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-map", "0:v:0", "-an",
        "-vf", selector, "-frames:v", "1",
        "-c:v", "png", "-pix_fmt", "gray", "-threads", "1",
        "-update", "1", str(output_path),
    ])
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise SkillError("FFmpeg did not write selected keyframe %d" % decoded_index)
    if png_color_type(output_path) not in (0, 4):
        raise SkillError("FFmpeg did not write a native grayscale PNG: %s" % output_path)


def extract_all_codec_keyframes(video, stage, prefix, positions):
    paths = []
    for output_index, decoded_index in enumerate(positions, start=1):
        path = stage / (prefix + "%03d.png" % output_index)
        extract_one_codec_keyframe(video, decoded_index, path)
        paths.append(path)
    checked = numbered_frames(stage, prefix)
    if checked != paths or len(checked) != len(positions):
        raise SkillError("staged extraction does not contain every expected codec keyframe")
    return checked


def image_dimensions(path):
    text = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path),
    ])
    match = re.search(r"(\d+)x(\d+)", text)
    if not match:
        raise SkillError("could not determine image dimensions: %s" % path)
    width, height = int(match.group(1)), int(match.group(2))
    if width < 1 or height < 1:
        raise SkillError("invalid image dimensions: %s" % path)
    return width, height


def gray_bytes(path):
    """Decode an image through the same 8-bit grayscale representation used for all images."""
    width, height = image_dimensions(path)
    raw = run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ], binary=True)
    if len(raw) != width * height:
        raise SkillError("could not decode a single grayscale image: %s" % path)
    return width, height, raw


def template_anchors(template, width, height):
    """Choose separated, high-contrast template pixels for candidate screening."""
    mean = sum(template) / float(len(template))
    ranked = sorted(range(len(template)), key=lambda i: abs(template[i] - mean), reverse=True)
    anchors = []
    minimum_spacing2 = max(1, min(width, height) // 4) ** 2
    for index in ranked:
        x, y = index % width, index // width
        if x == 0 or y == 0 or x == width - 1 or y == height - 1:
            continue
        if all((x - old_x) ** 2 + (y - old_y) ** 2 >= minimum_spacing2
               for old_x, old_y, _ in anchors):
            anchors.append((x, y, template[index]))
        if len(anchors) >= 6:
            break
    if not anchors:
        x, y = width // 2, height // 2
        anchors = [(x, y, template[y * width + x])]
    return anchors


def template_parameters(template):
    mean = sum(template) / float(len(template))
    variance = sum((value - mean) ** 2 for value in template) / float(len(template))
    contrast = math.sqrt(variance)
    # Adapt tolerances to the contrast of the current reference patch. Bounds
    # prevent very flat or very sharp templates from creating degenerate values.
    anchor_tolerance = int(max(5, min(18, round(4 + contrast * 0.12))))
    confirmation_tolerance = int(max(anchor_tolerance + 2, min(26, round(7 + contrast * 0.16))))
    mean_difference_limit = max(10.0, min(35.0, 10.0 + contrast * 0.20))
    return anchor_tolerance, confirmation_tolerance, mean_difference_limit, round(contrast, 3)


def patch_mean_absolute_difference(frame, fw, left, top, template, tw, th):
    total = 0
    for row in range(th):
        frame_start = (top + row) * fw + left
        template_start = row * tw
        total += sum(abs(frame[frame_start + column] - template[template_start + column])
                     for column in range(tw))
    return total / float(tw * th)


def occurrences(frame, fw, fh, template, tw, th):
    """Count confirmed template occurrences with anchor filtering and spatial NMS."""
    if tw > fw or th > fh:
        return 0
    anchors = template_anchors(template, tw, th)
    anchor_tol, confirm_tol, mean_limit, _ = template_parameters(template)
    ax, ay, anchor_value = anchors[0]
    candidates = set()
    for value in range(max(0, anchor_value - anchor_tol), min(255, anchor_value + anchor_tol) + 1):
        position = frame.find(bytes((value,)))
        while position >= 0:
            x, y = position % fw, position // fw
            left, top = x - ax, y - ay
            if 0 <= left <= fw - tw and 0 <= top <= fh - th:
                candidates.add((left, top))
            position = frame.find(bytes((value,)), position + 1)

    confirmed = []
    for left, top in candidates:
        # Several independent anchors reject background responses before the
        # more expensive full-patch comparison.
        if any(abs(frame[(top + y) * fw + left + x] - value) > confirm_tol
               for x, y, value in anchors[1:]):
            continue
        score = patch_mean_absolute_difference(frame, fw, left, top, template, tw, th)
        if score <= mean_limit:
            confirmed.append((left, top, score))

    kept = []
    x_distance = max(1, int(math.ceil(tw * 0.60)))
    y_distance = max(1, int(math.ceil(th * 0.60)))
    for left, top, score in sorted(confirmed, key=lambda candidate: candidate[2]):
        if all(abs(left - old_left) >= x_distance or abs(top - old_top) >= y_distance
               for old_left, old_top, _ in kept):
            kept.append((left, top, score))
    return len(kept)


def count_templates(frame_paths, template_paths):
    decoded_templates = {name: gray_bytes(template_paths[name]) for name in COLUMNS}
    counts = {name: [] for name in COLUMNS}
    calibration = {"method": "grayscale anchor screening, full-patch MAD confirmation, spatial NMS",
                   "templates": {}}
    for name, (_, _, patch) in decoded_templates.items():
        anchor_tol, confirm_tol, mean_limit, contrast = template_parameters(patch)
        calibration["templates"][name] = {
            "contrast": contrast,
            "anchor_tolerance": anchor_tol,
            "confirmation_anchor_tolerance": confirm_tol,
            "max_patch_mean_absolute_difference": round(mean_limit, 3),
        }
    for frame_path in frame_paths:
        fw, fh, image = gray_bytes(frame_path)
        for name in COLUMNS:
            tw, th, patch = decoded_templates[name]
            counts[name].append(occurrences(image, fw, fh, patch, tw, th))
    return counts, calibration


def write_csv(path, records):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def validate(final_paths, expected_count, csv_path=None, frame_id_dir=None):
    if len(final_paths) != expected_count:
        raise SkillError("published frame count differs from codec-keyframe metadata")
    for path in final_paths:
        if not path.is_file() or png_color_type(path) not in (0, 4):
            raise SkillError("published frame is not a native grayscale PNG: %s" % path)
    if csv_path is None:
        return {"frames_checked": len(final_paths)}

    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != HEADER:
        raise SkillError("CSV header is not exactly %r" % HEADER)
    if len(rows) != len(final_paths) + 1:
        raise SkillError("CSV does not contain exactly one data row per final keyframe")
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in final_paths]
    actual_ids = []
    for row in rows[1:]:
        if len(row) != 4:
            raise SkillError("CSV row does not have four columns: %r" % row)
        if any(not re.fullmatch(r"\d+", value or "") for value in row[1:]):
            raise SkillError("CSV has a non-integer or negative count row: %r" % row)
        actual_ids.append(row[0])
    if actual_ids != expected_ids:
        raise SkillError("CSV frame IDs do not match final keyframes in order")
    return {"frames_checked": len(final_paths), "csv_rows_checked": len(final_paths)}


def main(config):
    if not isinstance(config, dict):
        raise SkillError("stdin JSON must be an object")
    video = require_file(config.get("video_path"), "video")
    supplied = config.get("templates")
    if not isinstance(supplied, dict) or set(supplied) != set(COLUMNS):
        raise SkillError("templates must contain exactly coins, enemies, turtles")
    template_paths = {name: require_file(supplied[name], "template " + name) for name in COLUMNS}

    prefix = config.get("keyframe_prefix", "keyframes_")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix:
        raise SkillError("keyframe_prefix must be a nonempty filename prefix")
    output_dir = Path(config.get("output_dir", "/root")).expanduser().resolve()
    frame_id_dir = Path(config.get("frame_id_dir", str(output_dir))).expanduser().resolve()
    csv_path = Path(config.get("csv_path", "/root/counting_results.csv")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    remove_stale_outputs(output_dir, prefix, csv_path)

    stage = Path(tempfile.mkdtemp(prefix=".mario-keyframes-", dir=str(output_dir)))
    temporary_csv = None
    try:
        positions = codec_keyframe_positions(video)
        expected = len(positions)
        staged_paths = extract_all_codec_keyframes(video, stage, prefix, positions)
        validate(staged_paths, expected)
        counts, calibration = count_templates(staged_paths, template_paths)

        # Publish only the complete validated staging set. Records are derived
        # afterwards from this exact published list, preventing stale CSV rows.
        for source in staged_paths:
            os.replace(source, output_dir / source.name)
        final_paths = numbered_frames(output_dir, prefix)
        validate(final_paths, expected)

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
        validation = validate(final_paths, expected, temporary_csv, frame_id_dir)
        os.replace(temporary_csv, csv_path)
        temporary_csv = None
        validation = validate(final_paths, expected, csv_path, frame_id_dir)
        return {
            "ok": True,
            "codec_keyframes": expected,
            "frames": len(final_paths),
            "csv_path": str(csv_path),
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
