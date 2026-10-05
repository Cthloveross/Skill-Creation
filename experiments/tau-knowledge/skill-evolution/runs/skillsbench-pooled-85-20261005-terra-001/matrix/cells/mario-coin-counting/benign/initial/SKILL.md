---
name: mario-keyframe-template-counting
description: Extract codec key frames from an MP4 in presentation order, replace those frame files with grayscale PNGs, and count one or more templated game objects per frame using calibrated normalized template matching and non-maximum suppression. Use for frame-level object-count CSV tasks where templates and the source video are supplied locally.
---

# Key-frame template counting

This Skill creates the required grayscale key-frame artifacts and a strict CSV result. It is intended for fixed-resolution game/screen footage where supplied templates are representative of objects at their displayed scale.

## Preconditions

* `ffmpeg` and `ffprobe` must be available. They are used for key-frame extraction, image conversion, and validation.
* Python must provide NumPy (MoviePy installations normally include it). The matching implementation otherwise has no OpenCV dependency.
* The video and every template must exist and be decodable. Template dimensions must be smaller than the extracted frames and templates must have nonzero visual variance.

## Execution

Run the packaged script with JSON on standard input. For the supplied Mario task, use:

```json
{
  "video": "/root/super-mario.mp4",
  "keyframe_dir": "/root",
  "templates": {
    "coins": "/root/coin.png",
    "enemies": "/root/enemy.png",
    "turtles": "/root/turtle.png"
  },
  "csv_path": "/root/counting_results.csv"
}
```

For example, an executor can pipe that JSON to `python3 scripts/count_keyframes.py`.

### JSON input schema

* `video` (string, required): input MP4 or other ffmpeg-readable video.
* `keyframe_dir` (string, required): directory for `keyframes_001.png`, `keyframes_002.png`, and so on.
* `templates` (object, required): CSV count-column names mapped to template image paths.
* `csv_path` (string, required): output CSV path.
* `extract` (boolean, optional, default `true`): extract and replace any previous matching key-frame names. Set false only when a contiguous existing key-frame sequence is already present.
* `threshold_overrides` (object, optional): a mapping of template names to explicitly reviewed normalized-correlation thresholds. Normally omit this so calibration is based on the current frames and template.

The script emits one JSON object on stdout. On success it includes `ok`, the ordered key-frame paths, result count, and per-template calibration thresholds. On failure it emits `{"ok": false, "error": ...}` and exits nonzero.

## Method

1. The script selects video I/key frames with ffmpeg's frame-type selector. It writes them in decoder/presentation sequence using a zero-free, contiguous 001-based filename sequence.
2. Each extracted PNG is converted through ffmpeg to `gray` pixel format and atomically replaces its original RGB file. Templates are decoded through the same grayscale conversion path before comparison.
3. It computes normalized cross-correlation maps using NumPy FFT correlation and local image normalization. Calibration uses the distribution of local response peaks for the supplied template across the supplied frames: an Otsu split and a robust high-background bound establish the threshold. This avoids assuming that a fixed correlation threshold works for all templates or videos. The selected values are reported for review.
4. Candidate response peaks are greedily reduced by bounding-box IoU non-maximum suppression, so clustered responses from one object are not counted multiple times.
5. The output is CSV with exactly `frame_id` followed by template mapping keys in their supplied order. Values are native decimal integers. Frame IDs are absolute paths to the actual grayscale files.

## Validation and limitations

Before writing the CSV, the script verifies that filenames are contiguous and timeline-ordered, every output image can be decoded as a one-channel grayscale image, and each output frame has exactly one row. It also probes video metadata and reports it in the JSON result.

Inspect the returned thresholds and counts when the scene has repeated sprites or strong visual repetition. If a reviewed threshold must be changed, rerun from extraction with a `threshold_overrides` value for that template; do not edit the CSV independently. This skill does not perform scale-invariant matching: if the templates and rendered objects have different scales, provide scale-matched templates or use a detector designed for scale variation.
