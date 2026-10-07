# Implementation notes and pitfalls

These notes capture the frozen background guidance that shaped `scripts/diff.py`.

## Direction of the diff
- PDF is the OLD backup; Excel is the CURRENT (NEW) version.
- Therefore `old_value` is taken from the PDF record and `new_value` from Excel.
- Reversing this swaps every old/new pair (semantically wrong even if the set of
  modified IDs is correct). Do not swap.

## Only deleted + modified are requested
- `deleted_employees` = IDs in PDF but not in Excel.
- `modified_employees` = IDs in both whose any comparable field differs.
- Added employees (in Excel but not PDF) are intentionally NOT reported, because
  the public output contract has no such section.

## Employee IDs are strings
- IDs look like `EMP00002` with significant leading zeros.
- Never parse the numeric suffix to an int: `EMP00002` -> `2` would break the
  cross-source key match and create phantom delete+add pairs.
- The ID column is found by counting values matching `^EMP\d+$`, independent of
  the header label, so differing header names across sources do not matter.

## Multi-page PDF handling
- Every page is read via `pdfplumber`; all tables on all pages are concatenated.
- The first non-empty row is the header. Rows equal to that header on later
  pages are repeated page headers and are dropped so they are not counted as
  data (which would produce phantom deletions/modifications).
- Fully empty rows are removed before diffing.

## Type-aware comparison (false positive/negative avoidance)
- Every PDF value is a string; Excel values are typed (int/float/str).
- For each field value we strip `,`, `$`, `%`; if BOTH old and new parse as
  numbers we compare numerically and emit numbers (int if integral else float);
  otherwise we compare stripped strings and emit strings.
- This makes `"54321"` (PDF) == `54321` (Excel) and `54321` == `54321.0`.
- Known numeric fields in this domain: Salary, Years, Score. Text fields:
  Name, Department. The parse-both-sides rule covers both without hardcoding
  the field list, while still emitting numbers for numeric fields.

## Output JSON
- Numeric fields must be JSON numbers, text fields JSON strings.
- Both lists are sorted by ID (modifications tie-break by field) for
  deterministic output.
- Validate with `scripts/validate.py` before trusting the report.

## Library requirements
- `pdfplumber` for PDF extraction, `openpyxl` for Excel reading. If missing and
  the runtime allows internet, `pip install pdfplumber openpyxl`.
