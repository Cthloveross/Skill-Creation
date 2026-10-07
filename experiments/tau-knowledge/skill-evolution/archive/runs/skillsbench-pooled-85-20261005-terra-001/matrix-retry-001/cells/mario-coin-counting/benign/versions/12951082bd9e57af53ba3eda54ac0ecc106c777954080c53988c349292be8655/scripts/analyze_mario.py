#!/usr/bin/env python3
"""Dependency-free codec-keyframe extraction, grayscale conversion, and counting.

stdin JSON:
{
  "video_path": "/path/video.mp4",
  "templates": {"coins": "/path/a.png", "enemies": "/path/b.png", "turtles": "/path/c.png"},
  "output_dir": "/optional/output",
  "keyframe_prefix": "optional_prefix_",
  "frame_id_dir": "/optional/frame-id-directory",
  "csv_path": "/optional/counting_results.csv"
}

stdout: a JSON success object, or {"ok": false, "error": "..."}.
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

COLUMNS = ("coins", "enemies", "turtles")
HEADER = ["frame_id", *COLUMNS]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class SkillError(RuntimeError):
    pass


def run(argv, binary=False):
    """Run an argv command without a shell and return stdout or raise SkillError."""
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as exc:
        raise SkillError("required executable is unavailable: %s" % argv[0]) from exc
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        if not message:
            message = result.stdout.decode("utf-8", "replace").strip()
        raise SkillError("command failed (%s): %s" % (argv[0], message or "no diagnostic supplied"))
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


def require_file(value, label):
    if not isinstance(value, str) or not value:
        raise SkillError("%s path is missing" % label)
    path = Path(value).expanduser()
    if not path.is_file():
        raise SkillError("%s is not a readable regular file: %s" % (label, value))
    return path.resolve()


def frame_metadata_count(video):
    text = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=key_frame",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ])
    values = [line.strip() for line in text.splitlines() if line.strip()]
    if not values or any(value not in ("0", "1") for value in values):
        raise SkillError("ffprobe returned invalid or empty frame keyframe metadata")
    count = sum(value == "1" for value in values)
    if count < 1:
        raise SkillError("ffprobe reported no codec keyframes")
    return count


def numbered_frames(directory, prefix, allow_empty=False):
    expression = re.compile(re.escape(prefix) + r"(\d+)\.png$")
    found = []
    for candidate in directory.glob(prefix + "*.png"):
        match = expression.fullmatch(candidate.name)
        if match and candidate.is_file():
            found.append((int(match.group(1)), candidate))
    found.sort(key=lambda item: item[0])
    indexes = [item[0] for item in found]
    if (not allow_empty and not found) or indexes != list(range(1, len(found) + 1)):
        raise SkillError("keyframe names are not consecutive from 001: %r" % indexes)
    return [item[1] for item in found]


def remove_stale_outputs(directory, prefix, csv_path):
    expression = re.compile(re.escape(prefix) + r"\d+\.png$")
    for candidate in directory.glob(prefix + "*.png"):
        if candidate.is_file() and expression.fullmatch(candidate.name):
            candidate.unlink()
    if csv_path.exists():
        if not csv_path.is_file():
            raise SkillError("CSV output path exists but is not a regular file: %s" % csv_path)
        csv_path.unlink()


def extract_attempt(video, stage, prefix, selector):
    target = str(stage / (prefix + "%03d.png"))
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-map", "0:v:0", "-vf", selector, "-vsync", "0", "-start_number", "1", target,
    ])
    return numbered_frames(stage, prefix)


def extract_all_codec_keyframes(video, stage_root, prefix, expected):
    attempts = (
        ("ffmpeg_select_key", r"select=eq(key\,1)"),
        ("ffmpeg_select_i_picture_fallback", r"select=eq(pict_type\,I)"),
    )
    notes = []
    for method, selector in attempts:
        attempt = stage_root / method
        attempt.mkdir()
        try:
            paths = extract_attempt(video, attempt, prefix, selector)
        except SkillError as exc:
            notes.append("%s failed: %s" % (method, exc))
            shutil.rmtree(attempt, ignore_errors=True)
            continue
        if len(paths) == expected:
            return paths, method
        notes.append("%s wrote %d frames, expected %d" % (method, len(paths), expected))
        shutil.rmtree(attempt, ignore_errors=True)
    raise SkillError("could not extract every codec keyframe; " + "; ".join(notes))


def png_color_type(path):
    data = path.read_bytes()
    if len(data) < 29 or not data.startswith(PNG_SIGNATURE):
        raise SkillError("not a readable PNG: %s" % path)
    if data[8:12] != b"\x00\x00\x00\x0d" or data[12:16] != b"IHDR":
        raise SkillError("PNG lacks valid IHDR: %s" % path)
    return data[25]


def convert_one_to_grayscale(path):
    temporary = path.with_name(".gray-" + path.name)
    try:
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
            "-frames:v", "1", "-vf", "format=gray", "-pix_fmt", "gray", str(temporary),
        ])
        if png_color_type(temporary) not in (0, 4):
            raise SkillError("FFmpeg did not write a native grayscale PNG: %s" % path)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def grayscale_all(paths):
    for path in paths:
        convert_one_to_grayscale(path)
        if png_color_type(path) not in (0, 4):
            raise SkillError("final keyframe is not grayscale: %s" % path)


def image_dimensions(path):
    text = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x", str(path),
    ])
    match = re.search(r"(\d+)x(\d+)", text)
    if not match:
        raise SkillError("could not determine image dimensions: %s" % path)
    width, height = int(match.group(1)), int(match.group(2))
    if width < 2 or height < 2:
        raise SkillError("image is too small: %s" % path)
    return width, height


def gray_bytes(path):
    width, height = image_dimensions(path)
    raw = run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ], binary=True)
    if len(raw) != width * height:
        raise SkillError("could not decode a single grayscale image: %s" % path)
    return width, height, raw


def anchors(template, width, height):
    """Return high-contrast template anchor offsets for fast candidate screening."""
    mean = sum(template) / float(len(template))
    ranked = sorted(range(len(template)), key=lambda i: abs(template[i] - mean), reverse=True)
    chosen = []
    for index in ranked:
        x, y = index % width, index // width
        if x == 0 or y == 0 or x == width - 1 or y == height - 1:
            continue
        if all((x - ox) ** 2 + (y - oy) ** 2 >= 9 for ox, oy, _ in chosen):
            chosen.append((x, y, template[index]))
        if len(chosen) == 5:
            break
    if not chosen:
        chosen = [(width // 2, height // 2, template[(height // 2) * width + width // 2])]
    return chosen


def occurrences(frame, fw, fh, template, tw, th):
    """Anchor-screen and confirm template patches, then apply spatial NMS."""
    if tw > fw or th > fh:
        return 0
    points = anchors(template, tw, th)
    ax, ay, av = points[0]
    # H.264 compression can alter source pixel values; use a small range for the
    # first anchor and a tighter set of confirmation anchors.
    tolerance = 10
    candidates = set()
    for value in range(max(0, av - tolerance), min(255, av + tolerance) + 1):
        needle = bytes((value,))
        offset = frame.find(needle)
        while offset >= 0:
            x, y = offset % fw, offset // fw
            left, top = x - ax, y - ay
            if 0 <= left <= fw - tw and 0 <= top <= fh - th:
                candidates.add((left, top))
            offset = frame.find(needle, offset + 1)
    confirmed = []
    max_mean_difference = 18.0
    for left, top in candidates:
        good = True
        for x, y, value in points[1:]:
            if abs(frame[(top + y) * fw + left + x] - value) > 14:
                good = False
                break
        if not good:
            continue
        total = 0
        for row in range(th):
            a = (top + row) * fw + left
            b = row * tw
            total += sum(abs(frame[a + col] - template[b + col]) for col in range(tw))
        if total / float(tw * th) <= max_mean_difference:
            confirmed.append((left, top, total))
    # Lowest patch difference first; one nearby response represents one sprite.
    distance2 = max(1, min(tw, th) // 2) ** 2
    kept = []
    for left, top, score in sorted(confirmed, key=lambda value: value[2]):
        if all((left - old_x) ** 2 + (top - old_y) ** 2 > distance2 for old_x, old_y, _ in kept):
            kept.append((left, top, score))
    return len(kept)


def count_templates(frame_paths, template_paths):
    templates = {name: gray_bytes(template_paths[name]) for name in COLUMNS}
    output = {name: [] for name in COLUMNS}
    for frame_path in frame_paths:
        fw, fh, image = gray_bytes(frame_path)
        for name in COLUMNS:
            tw, th, patch = templates[name]
            output[name].append(occurrences(image, fw, fh, patch, tw, th))
    calibration = {
        "method": "grayscale anchor screening, patch mean-absolute-difference confirmation, spatial NMS",
        "anchor_tolerance": 10,
        "confirmation_anchor_tolerance": 14,
        "max_patch_mean_absolute_difference": 18.0,
    }
    return output, calibration


def write_csv(path, records):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def validate(paths, expected, csv_path=None, frame_id_dir=None):
    if len(paths) != expected:
        raise SkillError("published frame count differs from codec-keyframe metadata")
    for path in paths:
        if not path.is_file() or png_color_type(path) not in (0, 4):
            raise SkillError("published frame is not a native grayscale PNG: %s" % path)
    if csv_path is None:
        return {"frames_checked": len(paths)}
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != HEADER:
        raise SkillError("CSV header is not exactly %r" % HEADER)
    if len(rows) != len(paths) + 1:
        raise SkillError("CSV does not contain exactly one data row per final keyframe")
    expected_ids = [str((frame_id_dir / path.name).resolve()) for path in paths]
    actual_ids = []
    for row in rows[1:]:
        if len(row) != 4 or any(not re.fullmatch(r"\d+", value or "") for value in row[1:]):
            raise SkillError("CSV has invalid count row: %r" % row)
        actual_ids.append(row[0])
    if actual_ids != expected_ids:
        raise SkillError("CSV frame IDs do not match final keyframes in order")
    return {"frames_checked": len(paths), "csv_rows_checked": len(paths)}


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
        expected = frame_metadata_count(video)
        staged, method = extract_all_codec_keyframes(video, stage, prefix, expected)
        grayscale_all(staged)
        validate(staged, expected)
        counts, calibration = count_templates(staged, template_paths)

        # Publish from the complete validated staging set; derive records only
        # from the paths actually published.
        for source in staged:
            os.replace(source, output_dir / source.name)
        final_paths = numbered_frames(output_dir, prefix)
        validate(final_paths, expected)
        records = []
        for index, path in enumerate(final_paths):
            row = {"frame_id": str((frame_id_dir / path.name).resolve())}
            row.update({name: int(counts[name][index]) for name in COLUMNS})
            records.append(row)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".counting-results-", suffix=".csv", dir=str(csv_path.parent))
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
