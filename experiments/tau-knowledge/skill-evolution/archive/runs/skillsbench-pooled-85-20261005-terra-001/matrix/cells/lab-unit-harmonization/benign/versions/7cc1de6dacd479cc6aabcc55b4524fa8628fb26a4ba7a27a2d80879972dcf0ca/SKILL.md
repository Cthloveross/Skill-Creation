---
name: clinical-lab-unit-harmonization
description: Harmonize a numeric clinical laboratory CSV containing mixed conventional/SI units. Use when a feature-description file is available, incomplete patient records must be dropped, decimal commas and scientific notation must be normalized, and the resulting CSV must retain its input columns while using two-decimal US-conventional values.
---

# Clinical laboratory unit harmonization

Use `scripts/harmonize_ckd_labs.py` for laboratory extracts whose columns are numeric laboratory features. The script resolves each column to an analyte from the column name plus all matching text in the supplied description file, parses each value strictly, drops rows with missing or invalid numeric cells, and applies only analyte-specific SI-to-conventional conversion candidates.

The packaged registry intentionally contains clinical analyte aliases, dimensions, unit conversion equations, and broad validation intervals. It does **not** contain source-dataset rows, source identifiers, row assignments, or benchmark-derived thresholds. Its intervals are screening/selection guards, not diagnostic reference intervals.

## Runtime interface

The script reads one JSON object from standard input and writes one JSON report to standard output.

Input schema:

```json
{
  "input_path": "/root/environment/data/ckd_lab_data.csv",
  "descriptions_path": "/root/environment/data/ckd_feature_descriptions.csv",
  "output_path": "/root/ckd_lab_data_harmonized.csv",
  "strict": true
}
```

- `input_path` is required.
- `descriptions_path` is optional but strongly recommended. It may use any ordinary CSV layout; all cells in a matching description row are used as evidence.
- `output_path` defaults to `/root/ckd_lab_data_harmonized.csv`.
- `strict` defaults to `false`. With `true`, the script exits nonzero rather than write an artifact if a known analyte remains outside its broad harmonized validation interval. It does not invent a conversion for an unresolved column.

Example executor invocation:

```bash
python3 scripts/harmonize_ckd_labs.py <<'JSON'
{"input_path":"/root/environment/data/ckd_lab_data.csv","descriptions_path":"/root/environment/data/ckd_feature_descriptions.csv","output_path":"/root/ckd_lab_data_harmonized.csv","strict":true}
JSON
```

## Method and interpretation

1. Inspect the JSON report before treating the output as final. In particular, check `dropped_rows`, `resolved_columns`, `conversion_counts`, `unresolved_columns`, `ambiguous_cells`, and `outside_validation_after`.
2. The CSV reader preserves quoted decimal commas, recognizes decimal comma only for a token that is otherwise a valid decimal-comma number, accepts scientific notation, and rejects non-finite values. Blank strings, NA-like tokens, malformed numbers, and incomplete CSV rows cause the entire patient row to be dropped, as required by this task.
3. For each resolved analyte, identity is preferred when it already falls in the conventional validation interval. A conversion is selected only when identity is outside that interval and exactly one admissible SI/alternative conversion produces a valid conventional value. Thus a value that could plausibly be either unit is retained and recorded as ambiguous rather than being forced by distribution smoothing.
4. Values are converted at `Decimal` precision and rounded only when writing. Every retained data cell is written as fixed-point `X.XX`; no cell is emitted in scientific notation or with a decimal comma. The header and column count are preserved.
5. If strict validation fails, investigate the report and input/description semantics rather than blindly broadening thresholds or applying another analyte's factor. In particular, total versus ionized calcium, serum versus urine measurements, direct versus total bilirubin, and BUN versus urea require distinct semantic resolution.

The script’s JSON report is also the validation record. A successful report should show equal input/output column counts, zero bad retained cells, no non-finite values, and (in strict mode) zero post-harmonization validation failures.
