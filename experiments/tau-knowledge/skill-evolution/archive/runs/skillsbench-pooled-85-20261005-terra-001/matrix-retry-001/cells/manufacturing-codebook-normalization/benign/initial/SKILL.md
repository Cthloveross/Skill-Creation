---
name: manufacturing-defect-codebook-normalizer
description: Normalize free-text manufacturing test reasons from CSV logs to product-specific controlled codebooks, including noisy English/Chinese text, abbreviations, station constraints, multi-mention notes, review routing, and creation of the required solution.json artifact.
---

# Manufacturing defect codebook normalizer

Use this Skill when a CSV event log contains handwritten defect/reason text and one or more CSV controlled vocabularies define the allowed code and label pairs. It discovers common column roles at runtime rather than relying on a particular export's headers.

## Method

1. Read the log and codebook CSVs using their headers. Required log roles are record identifier, product, station, engineer, and raw reason. Required codebook roles are code and label. Product, keyword, and station columns in a codebook are used when present.
2. Select only the current record's product codebook. Filter candidates by declared station applicability before textual ranking.
3. Preserve original source evidence. Split on unambiguous reason separators; split conjunctions only when both sides independently have codebook evidence. Every emitted `span_text` is a stripped verbatim substring of the source text.
4. Rank labels and keyword fields using Unicode-normalized character similarity, token overlap, substring evidence, and a small reusable bilingual/abbreviation expansion lexicon. Compare the best result to the runner-up.
5. Accept only candidates meeting configurable score and separation requirements. Otherwise emit `pred_code: "UNKNOWN"` and an empty label. Scores are an explicit engineering review policy, not claimed universal or statistically calibrated thresholds.
6. Build evidence-based, varying confidence values. Accepted predictions are always above review predictions under the default policy. Rationale text records the observed span, matching codebook evidence, score, runner-up separation, and station condition.
7. Validate the full artifact before writing: record coverage, schema fields, segment identifiers and ordering, verbatim spans, code/label membership, station scope, confidence range, unknown fields, and nonempty rationales.

## Run

The packaged script uses `/app/data/test_center_logs.csv`, `/app/data/codebook_*.csv`, and writes `/app/output/solution.json` by default:

```bash
python scripts/normalize.py <<'JSON'
{}
JSON
```

Its JSON stdin schema is:

```json
{
  "logs_path": "/app/data/test_center_logs.csv",
  "codebook_paths": ["/app/data/codebook_example.csv"],
  "output_path": "/app/output/solution.json",
  "config": {
    "accept_score": 0.58,
    "min_margin": 0.08
  },
  "dry_run": false
}
```

All path fields are optional. `codebook_paths` defaults to `/app/data/codebook_*.csv`. `dry_run: true` performs normalization and validation but does not create the artifact. The script emits a JSON summary on stdout; it raises an actionable error for ambiguous/missing schema roles, missing product codebooks, malformed rows, or invalid output.

Tune `accept_score` and `min_margin` only using labeled deployment data or a documented review-cost policy. If empirical calibration is available, retain the decision evidence in output rationales and replace the confidence transform in `scripts/normalize.py` with a held-out calibrated model; do not simply add a constant to accepted confidences.
