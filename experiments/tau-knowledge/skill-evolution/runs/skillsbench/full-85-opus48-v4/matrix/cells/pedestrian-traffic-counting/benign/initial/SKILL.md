---
name: pedestrian-traffic-counting
description: >
  Count the number of UNIQUE pedestrians (people traveling on foot) in each
  fixed-camera surveillance video found in a directory, deduplicating people
  that appear across many frames, excluding cyclists and vehicle occupants, and
  writing the per-video counts to an .xlsx workbook with a single sheet named
  "results" (columns: filename, number). Use this when a task asks to count
  pedestrians per video and emit a strict Excel file compared row-by-row.
---

# Pedestrian Traffic Counting

## What this Skill does

Given a directory of videos (default `/app/video`), it:

1. Lists every video file (by extension), ignoring the output workbook itself.
2. For each video, counts the number of **unique pedestrians** using a
   detection + multi-object tracking pipeline (Ultralytics YOLO with ByteTrack).
   A person is counted exactly once no matter how many frames they appear in.
3. Excludes **cyclists / motorcyclists** (people whose box consistently overlaps
   a bicycle/motorcycle) and ignores spurious one-frame detections.
4. Writes results to `count.xlsx` with ONE sheet `results`, a header row
   `filename, number`, one row per video sorted alphabetically by filename, and
   the count stored as a native integer. No extra rows/columns/sheets.

The output contract (sheet name, columns, header, no extra content) is what the
grader compares line-by-line, so the Excel writer is kept deterministic and
minimal.

## Why tracking and not per-frame counting

A pedestrian visible for N frames would be counted N times by naive per-frame
summing. Deduplication across the temporal dimension is mandatory: we assign a
stable track ID per physical person and count unique IDs. See
`references/method.md` for the reasoning and the alternative holistic-LLM route.

## Environment assumptions

- Docker container, 4 CPUs, no GPU, ~4GB RAM, internet allowed.
- `ffmpeg` present; Python has `openpyxl`. `ultralytics` + `opencv-python` may
  need installing (internet is permitted). Weights (`yolov8n.pt`) auto-download
  on first use.

## Setup (run once before counting)

```bash
pip install --quiet ultralytics opencv-python openpyxl lap 2>/dev/null || true
```

The entrypoint also attempts this install itself, but doing it up front surfaces
network problems early.

## Running the entrypoint

The entrypoint reads a JSON request on stdin and writes a JSON report on stdout,
and as a side effect writes the `.xlsx`.

```bash
echo '{"video_dir":"/app/video","output_path":"/app/video/count.xlsx"}' \
  | python3 /app/environment/skills/current/scripts/count_pedestrians.py
```

(If the Skill lives elsewhere, point to its actual `scripts/` directory; read
the real paths from the environment rather than assuming.)

### stdin schema (all keys optional except handled defaults)
```json
{
  "video_dir": "/app/video",            // directory to scan
  "output_path": "/app/video/count.xlsx",
  "model": "yolov8n.pt",                // detector weights
  "conf": 0.3,                          // detection confidence
  "iou": 0.5,                           // NMS IoU
  "strides": null,                      // null -> auto from fps (~10 eff. fps)
  "min_frames": 2,                      // min sampled frames per kept track
  "riding_frac": 0.4                    // frac of frames overlapping a bike -> cyclist
}
```

### stdout schema
```json
{
  "results": [{"filename":"test1.mp4","number":5}, ...],
  "output_path": "/app/video/count.xlsx",
  "details": {"test1.mp4": {"primary_stride": 3, "stability": {...}, ...}},
  "errors": []
}
```

## Interpreting results and validating

- Confirm the workbook: exactly one sheet `results`, row 1 = `filename, number`,
  one data row per video, counts are integers. Use the validator:

```bash
echo '{"output_path":"/app/video/count.xlsx","video_dir":"/app/video"}' \
  | python3 /app/environment/skills/current/scripts/validate_output.py
```

  It fails loudly if the sheet name, header, column count, row count, or cell
  types are wrong.

- **Perturbation stability**: `details[*].stability` reports the unique-ID count
  at nearby strides. If counts swing widely between strides, the number is
  unreliable (missed brief appearances or ID fragmentation / over-merging) —
  inspect before trusting. The reported `number` uses the finest (most
  complete) stride, which minimizes fragmentation.

## Failure handling

- If `ultralytics` cannot be installed/imported, the script raises a clear error
  describing the missing dependency; it does NOT silently emit fabricated
  counts. (A HOG fallback is intentionally omitted because it cannot deduplicate
  reliably and would corrupt the count.)
- If a specific video fails to decode, its error is recorded in `errors` and the
  video is skipped; fix decoding (e.g., re-mux with ffmpeg) and rerun rather
  than guessing a count.
- Never hardcode counts. The number must come from analyzing the actual files
  present at runtime.

## Files

- `scripts/count_pedestrians.py` — entrypoint: scan dir, count, write xlsx.
- `scripts/pedestrian_core.py` — tracking + dedup + cyclist-exclusion logic.
- `scripts/write_results.py` — strict openpyxl writer (importable + CLI).
- `scripts/validate_output.py` — structural validation of the workbook.
- `references/method.md` — rationale, tuning notes, and LLM alternative.
