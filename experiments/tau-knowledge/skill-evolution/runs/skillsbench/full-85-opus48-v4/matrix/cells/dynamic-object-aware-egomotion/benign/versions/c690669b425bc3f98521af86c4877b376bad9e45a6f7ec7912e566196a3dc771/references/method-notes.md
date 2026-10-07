# Method notes and conventions

These notes capture the decisions baked into `scripts/common.py` so they can be
audited and corrected independently.

## Frame sampling and output correspondence
- `interval = round(orig_fps / target_fps)`, keep every `interval`-th decoded
  frame, convert to grayscale. `N` sampled frames -> `N-1` adjacent pairs.
- Transition `t` (frames t->t+1) labels sampled frame `t`.
- The final frame `N-1` reuses the **last** transition (N-2 -> N-1): its label
  and its mask duplicate that pair's result. This yields exactly `N` per-frame
  labels and `N` masks `f_0 .. f_{N-1}`.
- Intervals are half-open `start->end`; `0->1` labels frame 0 only; the final
  interval ends at `N`; expanded indices cover `0 .. N-1` exactly once.

## Egomotion sign conventions (image coordinates)
Apparent scene motion is opposite to camera motion.
- Image-center horizontal displacement `dx > 0` (scene shifts right) => **Pan
  Left**; `dx < 0` => **Pan Right**.
- Vertical `dy > 0` (scene shifts down) => **Tilt Up**; `dy < 0` => **Tilt
  Down**. Tilt uses a higher threshold than pan.
- Quadrant-point mean distance ratio from center `> 1` => **Dolly In**; `< 1`
  => **Dolly Out** (radial expansion vs contraction).
- Homography rotation `angle = atan2(h21, h11)`. Current mapping: `angle > thr`
  => **Roll Right**, `angle < -thr` => **Roll Left**. This roll sign is the
  least-certain convention; if a reference clip disagrees, flip it here and in
  `common.classify_motion` rather than changing unrelated thresholds.
- Each axis is independent; multiple labels can co-occur (compound motion).
  Only when no axis fires is the frame `Stay`.

## Thresholds (defaults in `common.DEFAULT_PARAMS`, some set in run.py)
- `pan_thr = max(1.5, 0.004*W)` px, `tilt_thr = max(2.0, 0.006*H)` px.
- `scale_thr = 0.02` (2% distance change), `roll_thr_deg = 1.0`.
- These are resolution-relative noise-floor estimates, not tuned to any class
  distribution. Re-estimate from the data or validation if available; do not
  bias toward an assumed majority class or suppress a rare class.

## Dynamic masks (flow-residual)
- Expected flow from `H` is computed by projecting the full pixel grid; residual
  = Farneback flow - expected flow. Without a homography, the global model is
  the pure-translation median flow (robust to the moving-object minority).
- Adaptive threshold `max(min_residual, mean + k_std*std)` of residual
  magnitude, then edge-margin suppression, morphological open+close, and
  connected-component area filtering (`min_area_frac` of the frame).
- Residuals are seeds, not full silhouettes: morphology/area filtering keep
  coherent regions. If recall of weakly textured objects is poor, prefer
  object-aware filling over aggressive erosion. If a warp-based temporal fuse
  is added later, respect the inverse-mapping convention of resampling APIs
  (a forward flow map passed to an inverse-mapping remap moves evidence the
  wrong way; verify with a synthetic single-blob translation).

## CSR storage
- `shape = [H, W]`. Per frame `i`: `f_{i}_data` (True values), `f_{i}_indices`
  (sorted column indices per row), `f_{i}_indptr` (length `H+1`, cumulative
  True-per-row, `indptr[0]==0`, `indptr[-1]==len(indices)`).
- Reconstruct by slicing `indices[indptr[r]:indptr[r+1]]` for each row `r`.
