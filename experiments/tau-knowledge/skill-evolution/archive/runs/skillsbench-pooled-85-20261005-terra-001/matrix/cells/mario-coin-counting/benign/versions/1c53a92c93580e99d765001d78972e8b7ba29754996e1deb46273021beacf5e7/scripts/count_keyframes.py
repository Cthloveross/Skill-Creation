#!/usr/bin/env python3
"""JSON stdin/stdout key-frame extraction and grayscale template counting."""
import csv
import glob
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError as exc:
    raise RuntimeError("NumPy is required for template matching") from exc


KEY_RE = re.compile(r"keyframes_(\d+)\.png$")


def run(command, text=False):
    return subprocess.run(command, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=text)


def probe(path):
    result = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,pix_fmt,avg_frame_rate,nb_frames:format=duration",
        "-of", "json", str(path)
    ], text=True)
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError("No video stream found in %s" % path)
    stream = streams[0]
    if not stream.get("width") or not stream.get("height"):
        raise ValueError("Missing dimensions for %s" % path)
    return stream, data.get("format", {})


def raw_gray(path):
    """Decode a single image through ffmpeg to an HxW uint8 grayscale array."""
    stream, _ = probe(path)
    width, height = int(stream["width"]), int(stream["height"])
    result = run([
        "ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "gray", "-"
    ])
    expected = width * height
    if len(result.stdout) != expected:
        raise ValueError("Could not decode one gray image from %s" % path)
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape((height, width))


def extract_keyframes(video, destination):
    destination.mkdir(parents=True, exist_ok=True)
    # Remove only artifacts owned by this skill, including sequences above 999.
    for path in destination.glob("keyframes_*.png"):
        if KEY_RE.fullmatch(path.name):
            path.unlink()
    pattern = str(destination / "keyframes_%03d.png")
    # select retains the incoming frame order; -vsync 0 prevents duplication.
    run([
        "ffmpeg", "-v", "error", "-y", "-i", str(video),
        "-map", "0:v:0", "-vf", "select=eq(pict_type\\,I)",
        "-vsync", "0", "-start_number", "1", pattern
    ])


def ordered_keyframes(destination):
    pairs = []
    for name in glob.glob(str(destination / "keyframes_*.png")):
        match = KEY_RE.search(name)
        if match:
            pairs.append((int(match.group(1)), Path(name)))
    pairs.sort(key=lambda item: item[0])
    if not pairs:
        raise ValueError("No codec key frames were extracted")
    expected = list(range(1, len(pairs) + 1))
    found = [number for number, _ in pairs]
    if found != expected:
        raise ValueError("Key-frame names are not a contiguous 001-based sequence")
    return [path for _, path in pairs]


def grayscale_in_place(frame_paths):
    for frame in frame_paths:
        temporary = frame.with_name(frame.stem + ".gray.png")
        if temporary.exists():
            temporary.unlink()
        run([
            "ffmpeg", "-v", "error", "-y", "-i", str(frame),
            "-frames:v", "1", "-vf", "format=gray", "-pix_fmt", "gray",
            str(temporary)
        ])
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise ValueError("ffmpeg did not write grayscale replacement for %s" % frame)
        os.replace(temporary, frame)


def validate_grayscale_frames(frame_paths):
    dimensions = None
    for frame in frame_paths:
        image = raw_gray(frame)
        stream, _ = probe(frame)
        if stream.get("pix_fmt") != "gray":
            raise ValueError("Written key frame is not grayscale: %s" % frame)
        if dimensions is None:
            dimensions = image.shape
        elif image.shape != dimensions:
            raise ValueError("Key-frame dimensions changed within one video")


def ncc_map(image, template):
    """Valid-window normalized cross correlation, without third-party CV modules."""
    image = image.astype(np.float64, copy=False)
    template = template.astype(np.float64, copy=False)
    h, w = template.shape
    H, W = image.shape
    if h > H or w > W:
        return np.empty((0, 0), dtype=np.float64)
    count = float(h * w)
    t_sum = template.sum()
    t_var = (template * template).sum() - (t_sum * t_sum / count)
    if t_var <= 1e-9:
        raise ValueError("Template has no grayscale variance")

    # Linear convolution with reversed template yields valid cross-correlation.
    full_shape = (H + h - 1, W + w - 1)
    correlation = np.fft.irfft2(
        np.fft.rfft2(image, full_shape) *
        np.fft.rfft2(template[::-1, ::-1], full_shape), full_shape
    )
    cross = correlation[h - 1:H, w - 1:W]

    integral = np.pad(image, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    integral_sq = np.pad(image * image, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    sums = integral[h:, w:] - integral[:-h, w:] - integral[h:, :-w] + integral[:-h, :-w]
    sums_sq = (integral_sq[h:, w:] - integral_sq[:-h, w:] -
               integral_sq[h:, :-w] + integral_sq[:-h, :-w])
    variance = np.maximum(sums_sq - (sums * sums / count), 0.0)
    denominator = np.sqrt(variance * t_var)
    score = np.full(cross.shape, -1.0, dtype=np.float64)
    valid = denominator > 1e-8
    score[valid] = (cross[valid] - sums[valid] * t_sum / count) / denominator[valid]
    return np.clip(score, -1.0, 1.0)


def local_peak_values(score, minimum=-0.25):
    """Return (y, x, score) local maxima in a 3x3 response neighborhood."""
    if score.size == 0:
        return np.empty((0, 3), dtype=np.float64)
    H, W = score.shape
    padded = np.pad(score, 1, mode="constant", constant_values=-np.inf)
    mask = score >= minimum
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            neighbor = padded[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
            mask &= score >= neighbor
    ys, xs = np.nonzero(mask)
    return np.column_stack((ys, xs, score[ys, xs]))


def otsu(values):
    values = values[np.isfinite(values)]
    if values.size < 2:
        return float(values[0]) if values.size else 1.0
    low, high = float(values.min()), float(values.max())
    if high - low < 1e-10:
        return high
    hist, edges = np.histogram(values, bins=256, range=(low, high))
    probability = hist.astype(np.float64) / hist.sum()
    omega = np.cumsum(probability)
    centers = (edges[:-1] + edges[1:]) / 2.0
    mean = np.cumsum(probability * centers)
    total_mean = mean[-1]
    denominator = omega * (1.0 - omega)
    between = np.zeros_like(denominator)
    valid = denominator > 1e-15
    between[valid] = ((total_mean * omega[valid] - mean[valid]) ** 2 /
                      denominator[valid])
    return float(centers[int(np.argmax(between))])


def calibrate(peaks):
    """Derive a threshold from the current template's local-peak distribution."""
    values = peaks[:, 2] if peaks.size else np.array([], dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < 8:
        raise ValueError("Too few template-response peaks to calibrate")
    split = otsu(values)
    # Estimate the repetitive/background response from its lower 90 percent.
    background = values[values <= np.quantile(values, 0.90)]
    median = float(np.median(background))
    mad = float(np.median(np.abs(background - median)))
    robust_bound = median + 8.0 * 1.4826 * mad
    # The upper-tail guard prevents a broad background mode from being accepted.
    tail_bound = float(np.quantile(values, 0.995))
    threshold = float(max(split, robust_bound, tail_bound))
    # Correlation cannot be meaningfully above one; tolerate numerical edges.
    threshold = min(threshold, 0.999999)
    return threshold, {
        "otsu": round(split, 6),
        "background_bound": round(robust_bound, 6),
        "tail_bound": round(tail_bound, 6),
        "peak_samples": int(values.size)
    }


def nms(peaks, template_shape, threshold):
    """Greedy IoU NMS over response peaks; return accepted (y,x,score) rows."""
    candidates = peaks[peaks[:, 2] >= threshold]
    if candidates.size == 0:
        return []
    candidates = candidates[np.argsort(candidates[:, 2])[::-1]]
    h, w = template_shape
    accepted = []
    for candidate in candidates:
        y, x, score = float(candidate[0]), float(candidate[1]), float(candidate[2])
        keep = True
        for ay, ax, _ in accepted:
            inter_w = max(0.0, min(x + w, ax + w) - max(x, ax))
            inter_h = max(0.0, min(y + h, ay + h) - max(y, ay))
            intersection = inter_w * inter_h
            union = 2.0 * h * w - intersection
            if union and intersection / union > 0.25:
                keep = False
                break
        if keep:
            accepted.append((y, x, score))
    return accepted


def main(config):
    required = ("video", "keyframe_dir", "templates", "csv_path")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError("Missing required input fields: " + ", ".join(missing))
    video = Path(config["video"])
    frame_dir = Path(config["keyframe_dir"])
    templates_config = config["templates"]
    if not isinstance(templates_config, dict) or not templates_config:
        raise ValueError("templates must be a nonempty object of column names to paths")
    if not video.is_file():
        raise FileNotFoundError("Video not found: %s" % video)
    for label, path in templates_config.items():
        if not isinstance(label, str) or not label or not Path(path).is_file():
            raise ValueError("Missing or invalid template for %r" % label)

    video_stream, video_format = probe(video)
    if config.get("extract", True):
        extract_keyframes(video, frame_dir)
    frames = ordered_keyframes(frame_dir)
    grayscale_in_place(frames)
    validate_grayscale_frames(frames)

    overrides = config.get("threshold_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("threshold_overrides must be an object when supplied")
    counts = {str(frame): {label: 0 for label in templates_config} for frame in frames}
    diagnostics = {}

    for label, template_path in templates_config.items():
        template = raw_gray(Path(template_path))
        peak_sets = []
        for frame in frames:
            peaks = local_peak_values(ncc_map(raw_gray(frame), template))
            peak_sets.append(peaks)
        all_peaks = np.vstack([p for p in peak_sets if p.size]) if any(p.size for p in peak_sets) else np.empty((0, 3))
        if label in overrides:
            threshold = float(overrides[label])
            if not -1.0 <= threshold <= 1.0:
                raise ValueError("Threshold override for %s must be in [-1, 1]" % label)
            calibration = {"override": threshold, "peak_samples": int(all_peaks.shape[0])}
        else:
            threshold, calibration = calibrate(all_peaks)
        calibration["selected_threshold"] = round(threshold, 6)
        calibration["template_shape"] = [int(template.shape[0]), int(template.shape[1])]
        diagnostics[label] = calibration
        for frame, peaks in zip(frames, peak_sets):
            counts[str(frame)][label] = len(nms(peaks, template.shape, threshold))

    output = Path(config["csv_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    fields = ["frame_id"] + list(templates_config.keys())
    with open(temporary, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for frame in frames:
            row = {"frame_id": str(frame)}
            row.update(counts[str(frame)])
            writer.writerow(row)
    os.replace(temporary, output)

    # Reopen and structurally validate the delivered artifact.
    with open(output, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        if len(rows) != len(frames) or (rows and list(rows[0].keys()) != fields):
            raise ValueError("CSV schema or one-row-per-frame validation failed")
        if [row["frame_id"] for row in rows] != [str(frame) for frame in frames]:
            raise ValueError("CSV frame order does not match extracted timeline order")
        for row in rows:
            for label in templates_config:
                if int(row[label]) < 0:
                    raise ValueError("CSV contains a negative count")

    return {
        "ok": True,
        "csv_path": str(output),
        "keyframe_count": len(frames),
        "keyframes": [str(frame) for frame in frames],
        "video_metadata": {"stream": video_stream, "format": video_format},
        "calibration": diagnostics
    }


if __name__ == "__main__":
    try:
        configuration = json.load(sys.stdin)
        result = main(configuration)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        sys.exit(2)
