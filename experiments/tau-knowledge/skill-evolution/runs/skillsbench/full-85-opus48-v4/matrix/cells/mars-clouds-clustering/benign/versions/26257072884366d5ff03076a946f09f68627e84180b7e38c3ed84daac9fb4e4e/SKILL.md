---
name: mars-clouds-clustering
description: >
  Optimize DBSCAN hyperparameters to cluster citizen-science Mars-cloud
  annotations against expert labels, then extract the two-objective Pareto
  frontier (maximize F1, minimize mean matched Euclidean delta). Use this Skill
  when given citsci/expert CSVs with file_rad,x,y columns and asked to grid
  search (min_samples, epsilon, shape_weight), score each combination, and write
  a pareto_frontier.csv. Covers the custom weighted distance metric, greedy
  centroid-to-expert matching, F1/delta averaging rules, filtering, and Pareto
  dominance exactly as specified.
---

# Mars Cloud Clustering Optimization

## What this Skill does

Given two CSV files (citizen-science annotations and expert annotations), it:

1. Groups both datasets by `file_rad` (base image id).
2. Runs an exhaustive grid search over DBSCAN hyperparameters.
3. For each `(min_samples, epsilon, shape_weight)` combination, clusters each
   image's citizen points, computes centroids, greedily matches them to expert
   points, and scores F1 and delta per image, then averages across images.
4. Keeps only combinations with average F1 > 0.5 and a finite average delta.
5. Extracts all Pareto-optimal points (maximize F1, minimize delta).
6. Writes `/root/pareto_frontier.csv` with the required columns and rounding.

## Exact method (do not deviate)

### Grid
- `min_samples`: integers 3..9 inclusive (7 values).
- `epsilon`: integers 4,6,8,...,24 (step 2, 11 values).
- `shape_weight` (`w`): 0.9,1.0,...,1.9 (step 0.1, 11 values); generate with
  `round(0.9 + 0.1*i, 1)` to avoid IEEE-754 artifacts.

### Clustering distance (weighted) — clustering step ONLY
`d(a,b) = sqrt((w*dx)^2 + ((2-w)*dy)^2)`. Equivalently
`sqrt(w^2*dx^2 + (2-w)^2*dy^2)`. Precompute the symmetric pairwise matrix per
image and run `DBSCAN(eps=epsilon, min_samples=min_samples,
metric='precomputed')`. Always invoke DBSCAN even when an image has very few
points; its noise labelling (all `-1` -> zero clusters) is the authoritative
result. Centroids are the arithmetic mean of each cluster's `(x,y)` (exclude
noise label `-1`).

### Matching + delta — standard Euclidean ONLY
Greedy bipartite matching between centroids and expert points: repeatedly take
the globally closest remaining `(centroid, expert)` pair; if its STANDARD
Euclidean distance < 100, record a match and remove both points; stop when no
remaining pair is below 100. Never use the weighted metric here. The recorded
match distances feed the delta metric.

### Per-image F1 / delta
- TP = number of matches; FP = centroids - TP; FN = experts - TP.
- Precision = TP/(TP+FP), Recall = TP/(TP+FN), F1 = 2PR/(P+R).
- If TP == 0 (no clusters, no matches, or no citizen points): F1 = 0.0 and
  delta = NaN for that image.
- delta (per image) = mean of matched standard-Euclidean distances.

### Averaging across images (asymmetric, by design)
- Iterate over **every unique `file_rad` in the EXPERT dataset**, including
  images that have no citizen annotations (those contribute F1 = 0, delta NaN).
- Average F1: include all images (F1 = 0 values count) -> divide the F1 sum by
  the total number of expert images.
- Average delta: `nanmean` across images — exclude NaN (only images with at
  least one match contribute).

### Filter then Pareto
- Keep combinations with average F1 > 0.5 AND finite (non-inf/non-NaN) average
  delta.
- Compute the Pareto frontier on FULL-PRECISION F1/delta: a point is kept
  unless some other point has F1 >= and delta <= with at least one strict
  inequality (maximize F1, minimize delta). Round only afterwards for output.

### Output
Write `/root/pareto_frontier.csv` with header exactly:
`F1,delta,min_samples,epsilon,shape_weight`.
Round F1 and delta to 5 decimals, `shape_weight` to 1 decimal; `min_samples`
and `epsilon` are integers.

## How to run

The end-to-end entrypoint is `scripts/run_clustering.py`. It reads an optional
JSON config object on stdin and writes a JSON summary on stdout.

Input JSON (all keys optional; defaults match the task):
```
{
  "citsci_path": "/root/data/citsci_train.csv",
  "expert_path": "/root/data/expert_train.csv",
  "output_path": "/root/pareto_frontier.csv",
  "n_jobs": 4
}
```

Output JSON:
```
{"status":"ok","output_path":"...","n_images":N,"n_filtered":K,
 "n_pareto":P,"rows":[{"F1":..,"delta":..,"min_samples":..,
 "epsilon":..,"shape_weight":..}, ...]}
```

Example call:
```
echo '{}' | python3 /app/environment/skills/current/scripts/run_clustering.py
```
(If the Skill directory differs, call the script by its actual path. With `{}`
it uses the task defaults and writes `/root/pareto_frontier.csv`.)

## Validation

After running, verify the artifact with `scripts/validate_output.py`:
```
echo '{"output_path":"/root/pareto_frontier.csv"}' | \
  python3 .../scripts/validate_output.py
```
It checks the header/columns, dtypes (int min_samples/epsilon, 1-dp
shape_weight, 5-dp rounding), that F1 values are > 0.5, and that no row in the
output dominates another (internal Pareto consistency). It reports
`{"ok":true,...}` or a list of problems. Running these checks is the
executor's job; design them from this request and B*, not from grader internals.

## Failure handling / notes
- Missing input files -> the entrypoint returns `{"status":"error",...}`; verify
  `/root/data/*.csv` exist with columns `file_rad,x,y`.
- `file_rad` is already the base id (no suffix stripping required per the task).
- Pairwise matrices are O(n^2) per image; the implementation reuses `dx^2`,
  `dy^2` across the 11 `w` values and parallelizes over images with joblib
  (falls back to sequential if joblib is absent).
- If the filtered set is empty, the output CSV is written with only the header;
  investigate the data/metric rather than lowering the 0.5 threshold.
- See `references/method-notes.md` for the subtle distinctions that most often
  break correctness.
