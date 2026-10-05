---
name: mars-cloud-dbscan-pareto
version: 1.0.0
description: Exhaustively optimize weighted-distance DBSCAN for per-image point annotations, evaluate it against expert points with global-minimum greedy matching, and write the full-precision Pareto frontier as the required CSV. Use for the Mars cloud clustering task or equivalent annotation-to-expert clustering searches.
---

# Weighted DBSCAN Pareto Search

Use `scripts/optimize_pareto.py` to load the citizen-science and expert CSV files, evaluate every required hyperparameter tuple, and create the requested Pareto-frontier CSV.

## Method implemented

For every expert `file_rad` (including those absent from citizen data), the script:

1. Runs `sklearn.cluster.DBSCAN` on citizen points after scaling coordinates to `(w*x, (2-w)*y)`. Euclidean distance in this scaled space is exactly the specified weighted distance.
2. Computes each non-noise cluster centroid in the original, unscaled `(x, y)` coordinate system.
3. Greedily matches centroids to expert points by repeatedly selecting the globally smallest remaining **standard Euclidean** distance, accepting it only when it is strictly below 100 pixels.
4. Computes image F1 as `2*TP/(number_of_centroids + number_of_experts)`. Images without points, clusters, or matches receive F1 0 and no delta contribution.
5. Averages F1 over every expert image and averages per-image mean matched distance only over images having a match.

It searches all 847 tuples: `min_samples=3..9`, `epsilon=4..24` by 2, and `shape_weight=0.9..1.9` by 0.1. It retains only finite-delta results with F1 strictly greater than 0.5, finds Pareto-optimal rows using unrounded values (maximize F1 and minimize delta), and only then formats the output values.

The input CSVs must contain `file_rad`, `x`, and `y`; coordinates and image identifiers must be non-missing and coordinates finite. The script reports such malformed input as an error rather than silently changing the dataset.

## Run

The script receives one JSON object on standard input and emits one JSON status object on standard output. With no fields, it uses the task paths and creates `/root/pareto_frontier.csv`.

```bash
python scripts/optimize_pareto.py <<'JSON'
{"citsci_path":"/root/data/citsci_train.csv","expert_path":"/root/data/expert_train.csv","output_path":"/root/pareto_frontier.csv","n_jobs":4}
JSON
```

Input fields:

- `citsci_path` (optional string): citizen CSV path; default `/root/data/citsci_train.csv`.
- `expert_path` (optional string): expert CSV path; default `/root/data/expert_train.csv`.
- `output_path` (optional string): destination CSV path; default `/root/pareto_frontier.csv`.
- `n_jobs` (optional positive integer): number of process workers, default 4. Set to 1 when process parallelism is unavailable.

Required Python packages are `numpy`, `pandas`, and `scikit-learn`. The script limits each worker's DBSCAN neighbor-search threading to avoid oversubscribing the supplied CPU allocation.

## Validate completion

A successful JSON response has `ok: true`, reports `evaluated_combinations: 847`, and supplies the number of filtered and frontier rows. The script internally verifies that the grid is complete, that every written candidate passes the F1/delta filter, and that no reported row is dominated using the original full-precision metrics. Inspect `/root/pareto_frontier.csv` afterward: it must have exactly this header:

```text
F1,delta,min_samples,epsilon,shape_weight
```

Each data row has F1 and delta formatted to five decimal places, integer `min_samples` and `epsilon`, and a one-decimal-place shape weight. An empty data section is still a valid outcome if no configuration passes the stated filter.
