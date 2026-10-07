---
name: clinical-lab-unit-harmonization
description: Harmonize a rectangular clinical-laboratory CSV with decimal-comma and scientific-notation values to US conventional units. Use when a feature-description file identifies analytes and individual values may be in common SI or scale-only alternatives.
---

# Clinical laboratory unit harmonization

This Skill produces a new CSV; it never modifies the source artifact. It is intended for numeric laboratory tables whose feature descriptions identify the analyte. It drops rows with missing values, strictly parses decimal comma and scientific notation, resolves columns through a reusable analyte registry, selectively converts plausible alternate-unit values to US conventional units, and writes fixed two-decimal output.

## Method and safeguards

1. Read the description file and match each data column against its code/name and description. The registry is analyte-specific and deliberately distinguishes, for example, direct from total bilirubin.
2. Drop a row if any input field is blank or an accepted missing token (`NA`, `N/A`, `NULL`, `NONE`, `.`).
3. Parse numerical fields strictly. A comma is accepted only as a decimal separator, not as a thousands separator. Non-finite numbers and malformed values are errors.
4. For a recognized analyte, retain an in-range conventional value (identity is preferred). An out-of-range value is converted only when exactly one documented alternate-unit factor places it in that analyte's broad clinical plausibility interval. This avoids applying a generic factor merely because a number is large or small.
5. Round only after conversion, using decimal half-up rounding, and serialize numeric values as `X.XX` without exponent notation or decimal commas.

The included intervals are deliberately broad clinical plausibility bounds, not reference intervals and not a dataset-specific answer table. They support conservative unit disambiguation. A value that is neither conventionally plausible nor uniquely convertible is reported as unresolved. In strict mode this is an error rather than silently inventing a conversion. Review the source unit, specimen, and assay for such fields; do not use this Skill to force semantically ambiguous data through a conversion.

## Run

The script receives one JSON object on standard input and emits a JSON summary on standard output.

```sh
python /app/environment/skills/current/scripts/harmonize.py <<'JSON'
{
  "input_path": "/root/environment/data/ckd_lab_data.csv",
  "descriptions_path": "/root/environment/data/ckd_feature_descriptions.csv",
  "output_path": "/root/ckd_lab_data_harmonized.csv",
  "strict_ranges": true
}
JSON
```

### Input schema

- `input_path` (required): CSV laboratory table.
- `descriptions_path` (optional): CSV containing feature codes/names and descriptions. It is used for analyte resolution; columns may have varying heading names.
- `output_path` (required): destination CSV.
- `strict_ranges` (optional, default `true`): fail if a recognized analyte remains outside its plausibility interval or has competing conversion candidates. Set false only to create a review artifact; inspect the returned `unresolved` list before delivery.

### Output summary schema

The JSON result contains `input_rows`, `written_rows`, `dropped_missing_rows`, `converted_cells`, `recognized_columns`, `unresolved`, and `output_path`. `unresolved` entries contain column names and reasons, never fabricated replacements.

## Validation before delivery

The script validates that the output has the original header and column count, contains only retained complete rows, has no non-finite numeric output, and renders every numeric cell with exactly two fractional digits. In strict mode it additionally validates the resolved-unit decision for every recognized analyte. Confirm `written_rows` is sensible, `unresolved` is empty, and the output file is at the requested path.

Common conventional conversion provenance used by the registry: SI-prefix scale relations; creatinine 88.4 µmol/L per mg/dL; glucose 18.0182 mmol/L per mg/dL; calcium 4.008 mmol/L per mg/dL; bilirubin 17.104 µmol/L per mg/dL; cholesterol 38.67 mmol/L per mg/dL; triglyceride 88.57 mmol/L per mg/dL. These are conversion factors, not clinical reference intervals.
