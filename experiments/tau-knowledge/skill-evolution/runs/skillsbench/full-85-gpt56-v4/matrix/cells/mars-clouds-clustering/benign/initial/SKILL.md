---
name: mars-cloud-dbscan-pareto
version: 1.0.0
description: Perform a reproducible DBSCAN grid search on citizen-science point annotations, score it against expert points with specified greedy Euclidean matching, and write the full-precision Pareto frontier as the required CSV. Use for Mars/cloud-style annotation aggregation tasks with file_rad, x, and y columns.
---

# Mars Cloud DBSCAN Pareto Search

Use `scripts/run_pareto.py` to evaluate all requested `min_samples`, `epsilon`, and `shape_weight` values and create the frontier CSV.

The program:

1. Reads only `file_rad`, `x`, and `y` from the citizen and expert CSVs and validates those values.
2. Iterates over every image occurring in the expert data. A missing citizen group has no centroids and therefore contributes F1 zero.
3. Runs DBSCAN for every nonempty citizen group, including groups with fewer points than `min_samples`. The weighted metric is implemented exactly by scaling coordinates to `(w*x, (2-w)*y)` and using Euclidean DBSCAN; this is algebraically identical to the required custom distance while allowing sklearn's spatial neighbor search.
4. Computes non-noise centroids, then greedily matches the globally closest remaining centroid/expert pair using **ordinary** Euclidean distance and a strict `< 100` pixel cutoff.
5. Averages image F1 over all expert images; averages per-image mean match distance only over images with at least one match.
6. Filters at `F1 > 0.5`, removes non-finite deltas, determines dominance using unrounded values, then rounds only for CSV presentation.

## Run

The defaults are the paths and output required by this task:

```sh
python /app/environment/skills/current/scripts/run_pareto.py
```

For the script JSON interface, pass one object on standard input. All keys are optional:

```sh
printf '%s' '{"citizen_csv":"/root/data/citsci_train.csv","expert_csv":"/root/data/expert_train.csv","output_csv":"/root/pareto_frontier.csv","workers":4}' | python /app/environment/skills/current/scripts/run_pareto.py
```

Input schema:

- `citizen_csv` and `expert_csv`: CSV paths, defaulting to `/root/data/citsci_train.csv` and `/root/data/expert_train.csv`.
- `output_csv`: destination path, defaulting to `/root/pareto_frontier.csv`.
- `workers`: positive integer worker count; default is up to 4 available CPUs.

The script writes one JSON object to stdout with `output_csv`, `evaluated`, `filtered`, and `pareto_rows`. Diagnostics and failures go to stderr. It requires Python packages `numpy`, `pandas`, and `scikit-learn`.

## Validation

On successful completion, inspect the output with:

```sh
head -n 2 /root/pareto_frontier.csv
```

It must have exactly this header:

```text
F1,delta,min_samples,epsilon,shape_weight
```

Every row has five-decimal F1/delta formatting, integer `min_samples` and `epsilon`, and one-decimal `shape_weight`. The script itself reopens the atomically written CSV and validates the header and row count before reporting success. An empty eligible frontier is represented by the header alone.
