# Operational notes

## Key-frame extraction
- Primary: `ffmpeg -skip_frame nokey -i VIDEO -an -vsync vfr keyframes_%03d.png`
  writes only codec key (I) frames in presentation order; `%03d` starts at 001.
- Fallback if the primary yields nothing (unusual codecs):
  `ffmpeg -i VIDEO -an -vf "select=eq(pict_type\,I)" -vsync vfr keyframes_%03d.png`.
- Always re-glob `keyframes_*.png` and confirm contiguous numbering and that
  the count matches what ffmpeg reported.

## Grayscale in place
- Read color, `cvtColor(BGR2GRAY)`, overwrite the SAME path. The saved PNG is
  single channel. Verify with `imread(..., IMREAD_UNCHANGED).ndim == 2`.
- Both frame and template are matched in grayscale: identical pipeline.

## Thresholds and scales (calibrate, do not assume)
- `TM_CCOEFF_NORMED` peaks near 1.0 for strong matches. 0.7 is a starting
  default only. Run `scripts/calibrate.py` to see per-frame peak scores for
  each template, then set a threshold that separates object peaks from
  background clutter.
- Templates may not be at the video's sprite scale, so a scale sweep
  (0.5..2.0) is used. If detections are missed, widen the sweep; if the same
  object is double-counted, raise the IoU threshold or trim overlapping scales.
- Confirm stability: re-run with threshold +/-0.05 and check that counts do
  not swing wildly. For repetitive backgrounds consider confirming candidates
  with extra evidence (edges/color) before trusting a low threshold.

## CSV contract
- Header exactly `frame_id` followed by the requested count columns.
- `frame_id` is the absolute frame path (e.g. `/root/keyframes_001.png`).
- Counts are integers. One data row per key frame, sorted by index.
- No blank rows, summary rows, or extra columns.
- Output path and column names come from the live public request; for this
  task the opening names `/root/counting_results.csv` and columns
  `frame_id,coins,enemies,turtles`.
