---
name: pdf-excel-employee-diff
description: >-
  Extract an employee table from an "old" backup PDF, read the "current" Excel
  (.xlsx) workbook, and produce a row-level diff report (deleted and modified
  employees) as JSON. Use when a task supplies a backup PDF plus a current Excel
  of the same employee dataset keyed by an EMP##### style employee ID and asks
  for deleted_employees and modified_employees (field, old_value, new_value)
  with old=PDF and new=Excel. Handles multi-page PDF tables, repeated headers,
  type-aware numeric vs text comparison, and string-preserving IDs.
---

# PDF → Excel Employee Diff

## When to use
A task gives two versions of the same employee table:
- an **old** backup as a PDF (e.g. `/root/employees_backup.pdf`), and
- a **current** version as an Excel workbook (e.g. `/root/employees_current.xlsx`).

It asks which employees were **deleted** (present in PDF, absent in Excel) and which
records were **modified** (same ID in both, a field value differs), reporting the
changed field with its old (PDF) and new (Excel) value, written to a JSON file
(default `/root/diff_report.json`).

Output contract (from the public request):
```json
{
  "deleted_employees": ["EMP00002", "EMP00004"],
  "modified_employees": [
    {"id": "EMP00003", "field": "Salary", "old_value": 50020, "new_value": 55010}
  ]
}
```
Rules enforced by this Skill:
- **old_value comes from the PDF, new_value from the Excel.** Do not swap.
- Numeric fields (Salary, Years, Score, and any field whose values parse as
  numbers on both sides) are serialized as JSON **numbers** (int when integral,
  else float). Text fields stay JSON **strings**.
- Employee IDs are kept as **strings** throughout (leading zeros preserved,
  e.g. `EMP00002`). The numeric suffix is never parsed to an int.
- `deleted_employees` and `modified_employees` are **sorted by ID** for
  determinism (modifications tie-break by field name).
- The PDF table may span many pages; **all** pages are read and repeated header
  rows are dropped so they do not become phantom data.

## Method
1. **Extract PDF rows** with `pdfplumber`, iterating every page and calling
   `page.extract_tables()`. The first non-empty row becomes the header; any later
   row equal to that header (a repeated page header) is discarded.
2. **Read Excel** with `openpyxl` (`data_only=True`) so typed cells keep their
   values; the first row is the header, the rest are data.
3. **Detect the ID column independently in each source** by counting which column
   holds the most values matching `^EMP\d+$`. The key is `str(value).strip()`.
   This is robust even when the PDF and Excel header labels for the ID differ.
4. **Match comparable fields** by normalized (stripped, lower-cased) header name;
   compare the intersection of fields except the ID. The output label uses the
   PDF's original header text.
5. **Type-aware comparison** per field value: strip commas / `$` / `%`; if **both**
   old and new parse as numbers, compare numerically and emit numbers; otherwise
   compare as stripped strings and emit strings. This avoids `"54321"` vs `54321`
   and `54321` vs `54321.0` false mismatches.
6. **Diff**: deleted = PDF keys not in Excel; modified = common keys whose any
   comparable field differs (one entry per changed field).
7. **Write** the sorted result to the output path as JSON.

## Running it
The entrypoint `scripts/diff.py` reads a JSON object on **stdin** and writes a
JSON summary to **stdout**, and writes the report file to disk.

Input JSON (all keys optional; shown with defaults):
```json
{
  "pdf_path": "/root/employees_backup.pdf",
  "excel_path": "/root/employees_current.xlsx",
  "output_path": "/root/diff_report.json"
}
```

Example call (defaults are fine for this task):
```bash
echo '{}' | python3 /app/environment/skills/current/scripts/diff.py
```
or with explicit paths:
```bash
echo '{"pdf_path":"/root/employees_backup.pdf","excel_path":"/root/employees_current.xlsx","output_path":"/root/diff_report.json"}' \
  | python3 /app/environment/skills/current/scripts/diff.py
```

Stdout schema:
```json
{
  "status": "ok",
  "output_path": "/root/diff_report.json",
  "deleted_count": 2,
  "modified_count": 1,
  "warnings": [],
  "deleted_employees": [...],
  "modified_employees": [...]
}
```
On failure `status` is `"error"` and `error` describes the problem
(e.g. missing library, missing file, ID column not found). The executor should
read stdout, confirm `status == "ok"`, and then verify the on-disk file.

## Executor checklist / validation
After running:
1. Confirm stdout `status == "ok"` and `output_path` exists.
2. `python3 -c "import json;d=json.load(open('/root/diff_report.json'));print(sorted(d))"`
   must show exactly `deleted_employees` and `modified_employees`.
3. Spot-check: every ID is a string like `EMP#####`; each modified entry has
   `id`, `field`, `old_value`, `new_value`; numeric fields are JSON numbers,
   text fields are JSON strings; both lists are sorted by ID.
4. `scripts/validate.py` performs these structural checks: pipe the produced
   report path in and confirm `valid == true`:
   ```bash
   echo '{"report_path":"/root/diff_report.json"}' | python3 /app/environment/skills/current/scripts/validate.py
   ```

## Assumptions and failure handling
- Requires `pdfplumber` and `openpyxl`. If `pdfplumber` is unavailable the script
  reports an error; install it (`pip install pdfplumber`) if the runtime allows
  (`allow_internet` is true for this task) and rerun.
- If the detected columns differ in count between pages, rows are matched by the
  header-length of the first page; shorter rows are padded with empty strings.
- If no column with EMP-pattern values is found in a source, the script errors
  rather than guessing a key.
- Rows whose values exactly equal the header (repeated multi-page headers) and
  fully empty rows are skipped before diffing.
- The script never adds an "added_employees" section because the public contract
  asks only for deleted and modified; added keys are ignored.
