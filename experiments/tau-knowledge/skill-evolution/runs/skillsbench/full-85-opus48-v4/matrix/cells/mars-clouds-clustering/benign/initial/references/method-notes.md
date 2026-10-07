# Method notes — correctness-critical distinctions

These are the subtle points that most often cause wrong F1/delta/Pareto output.

1. **Two different distances.**
   - Clustering (DBSCAN) uses the WEIGHTED metric
     `sqrt((w*dx)^2 + ((2-w)*dy)^2)` via a precomputed matrix.
   - Centroid-to-expert matching AND the delta metric use STANDARD Euclidean.
   Mixing them yields wrong results.

2. **w=1 is standard Euclidean.** w>1 amplifies x and attenuates y (2-w<1);
   w<1 does the reverse. Generate w as `round(0.9+0.1*i,1)`.

3. **Always run DBSCAN.** When an image has fewer points than `min_samples`,
   DBSCAN labels all points noise (`-1`) and yields zero clusters. Do not
   short-circuit; the zero-cluster outcome is a real result -> F1=0, delta=NaN.
   Centroids exclude noise points.

4. **Greedy matching = global nearest first.** At each step pick the single
   globally smallest remaining (centroid, expert) distance; if < 100, match and
   remove both; otherwise stop. Do NOT iterate centroids in order.

5. **F1 counts.** TP = matches, FP = centroids-TP, FN = experts-TP.
   F1 = 2PR/(P+R). TP=0 => F1=0, delta=NaN.

6. **Averaging asymmetry.**
   - Iterate over ALL unique `file_rad` in the EXPERT dataset (even those with
     no citizen points). F1 average divides by the total expert-image count;
     F1=0 images are included.
   - delta average is a `nanmean`: NaN (no-match) images are excluded.

7. **Filter before Pareto.** Keep only average F1 > 0.5 and finite average
   delta (drop inf/undefined delta).

8. **Pareto on full precision.** Dominance: A dominates B if A.F1>=B.F1 and
   A.delta<=B.delta with at least one strict inequality (maximize F1, minimize
   delta). Round only for output: F1,delta to 5 decimals; shape_weight to 1;
   min_samples,epsilon as ints. Rounding before dominance can merge distinct
   points and change the frontier.

9. **Grouping.** `file_rad` is already the base image id in this task's data;
   group directly, no suffix stripping needed.

10. **Performance.** Reuse `dx^2`,`dy^2` across the 11 w values per image;
    parallelize over images. Pairwise matrices are O(n^2) per image.
