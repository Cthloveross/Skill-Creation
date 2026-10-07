---
name: clinical-lab-unit-harmonization
description: Harmonize a numeric clinical laboratory CSV containing mixed conventional/SI units. Use when a feature-description file is available, incomplete patient records must be dropped, decimal commas and scientific notation must be normalized, and the resulting CSV must retain its input columns while using two-decimal US-conventional values.
---

# Clinical laboratory unit harmonization

Use `scripts/harmonize_ckd_labs.py` for laboratory extracts whose columns are numeric laboratory features. The script resolves each column to an analyte from the column name plus matching text in the supplied description file, parses each value strictly, drops rows with missing or invalid numeric cells, and applies only analyte-specific SI-to-conventional conversion candidates.

The packaged registry contains reusable clinical analyte aliases, dimensions, conversion equations, and broad selection intervals. It does not contain source-dataset rows, identifiers, row assignments, or expected output values. Analytes with related wording are resolved separately: for example, HbA1c is a percentage/fraction measurement and is never treated as blood glucose.

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
- `descriptions_path` is optional but strongly recommended. It may use an ordinary CSV layout; all cells in a matching description row are used as semantic evidence.
- `output_path` defaults to `/root/ckd_lab_data_harmonized.csv`.
- `strict` defaults to `false`. With `true`, the script exits nonzero rather than write an artifact if a known analyte remains outside its broad harmonized validation interval. It does not invent a conversion for an unresolved column.

Example executor invocation:

```bash
python3 scripts/harmonize_ckd_labs.py <<'JSON'
{"input_path":"/root/environment/data/ckd_lab_data.csv","descriptions_path":"/root/environment/data/ckd_feature_descriptions.csv","output_path":"/root/ckd_lab_data_harmonized.csv","strict":true}
JSON
```

## Method and validation

1. Inspect the JSON report before treating the output as final. Check `dropped_rows`, `resolved_columns`, `conversion_counts`, `unresolved_columns`, `ambiguous_cells`, and `outside_validation_after`.
2. The parser accepts ordinary decimals, decimal commas, and scientific notation, rejects non-finite values, and treats blank/NA-like/malformed cells or incomplete CSV rows as reasons to drop the whole patient row.
3. Resolve analyte identity before considering value scale. Identity is retained when already within the conventional screening interval. A conversion is selected only when identity is outside the interval and exactly one conversion valid for that same analyte yields a valid conventional value. HbA1c remains a percent value (or a fraction multiplied by 100), not a glucose value.
4. Values are converted at `Decimal` precision and rounded only when writing. Every retained data cell is emitted as fixed-point `X.XX`; no scientific notation or decimal comma is emitted. The header, order, and input column count are preserved.
5. In strict mode, investigate semantic resolution or source units if validation fails. Do not fix failures by applying a factor belonging to a related but different analyte, such as glucose versus HbA1c, total versus ionized calcium, or BUN versus urea.

A successful report should show equal input/output column counts, no malformed retained cells, and, in strict mode, zero post-harmonization validation failures.
