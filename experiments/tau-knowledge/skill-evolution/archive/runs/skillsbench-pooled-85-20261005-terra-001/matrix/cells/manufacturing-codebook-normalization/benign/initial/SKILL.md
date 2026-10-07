---
name: manufacturing-defect-codebook-normalizer
description: Normalize manufacturing-test free-text defect reasons from CSV logs into product- and station-constrained codebooks, preserving verbatim evidence spans and producing the required solution.json.
---

# Manufacturing Defect Codebook Normalizer

Use this Skill when an event/log CSV contains handwritten defect reasons and one or more product codebook CSVs define the permitted standardized codes and labels.

## Method

`scripts/normalize.py` discovers CSV columns by semantic header names, loads each codebook, and writes the requested JSON structure. It:

- retains every source record and copies its identifying/source fields;
- selects the record's product codebook only, then rejects station-inapplicable entries when a codebook declares station scope;
- uses Unicode normalization for retrieval only while returning verbatim source spans;
- derives candidate aliases from labels and codebook keyword/synonym/example columns;
- scores character similarity, token overlap, containment, exact normalized aliases, and runner-up separation;
- segments clear independent clauses but keeps likely bilingual restatements together when they map to the same candidate;
- emits `UNKNOWN` with an empty label for weak or ambiguous candidates;
- computes nonconstant confidence from evidence strength and separation. Accepted confidence is always above unknown confidence under the default policy;
- validates record coverage, codebook membership, station scope, segment identifiers, source spans, confidence bounds, unknown representation, and output shape before saving.

The default operating policy (`min_score=0.66`, `min_margin=0.07`) is deliberately explicit and caller-configurable, not a claimed universal fuzzy-match threshold. Calibrate these settings against labeled deployment data when available.

## Runtime invocation

The script receives one JSON object on stdin and emits a compact JSON run summary on stdout. With the supplied task layout, run:

```bash
python3 scripts/normalize.py <<'JSON'
{"events_path":"/app/data/test_center_logs.csv","codebook_paths":["/app/data/codebook_P1_POWER.csv","/app/data/codebook_P2_CTRL.csv","/app/data/codebook_P3_RF.csv"],"output_path":"/app/output/solution.json","min_score":0.66,"min_margin":0.07}
JSON
```

All keys are optional: defaults are `/app/data/test_center_logs.csv`, all `/app/data/codebook_*.csv`, and `/app/output/solution.json`. `codebook_paths` may also be a directory. Codebook CSVs should expose a code and label column; keyword, synonym, example, product, and station columns are discovered when present. The event CSV must expose record ID, product, station, engineer, and raw reason text columns. Ambiguous or missing required roles fail with an actionable error rather than silently guessing.

After execution, use `/app/output/solution.json` as the task artifact. Do not substitute script recommendations for banking or other external actions; this Skill only creates the JSON artifact.
