---
name: employee-pdf-excel-diff
description: Extract an employee table from an older text-based PDF, compare it with a current XLSX workbook by employee ID, and write a deterministic JSON report of deletions and field-level modifications. Use when the PDF is the old source and Excel is the new source.
---

# Employee PDF-to-Excel Difference Report

Use `scripts/diff_employees.py` to create the requested report. The script treats the PDF as the old baseline and the XLSX as the new dataset, preserves IDs as strings, and emits numeric `Salary`, `Years`, and `Score` values as JSON numbers.

## Prerequisites and assumptions

- The PDF must be text-based (not a scanned image) and contain an employee table with an ID header and IDs such as `EMP00002`.
- The runtime needs `pdfplumber` and `openpyxl`.
- The first nonempty worksheet is read, with its first nonempty row used as the header row.
- The PDF and Excel must have a recognizable employee-ID column. The script accepts common variants such as `ID`, `Employee ID`, and `EmployeeID`.
- PDF table extraction is heuristic. The script validates that it found a header, data rows, consistent usable fields, and unique nonempty employee IDs rather than silently reporting from malformed extraction.

## Run

Scripts receive one JSON object on standard input and return the report JSON on standard output. Supply absolute paths for this task:

```sh
printf '%s' '{"pdf_path":"/root/employees_backup.pdf","excel_path":"/root/employees_current.xlsx","output_path":"/root/diff_report.json"}' | python3 /app/environment/skills/current/scripts/diff_employees.py
```

Input schema:

```json
{
  "pdf_path": "/path/to/old.pdf",
  "excel_path": "/path/to/new.xlsx",
  "output_path": "/path/to/diff_report.json"
}
```

`output_path` is optional; it defaults to `diff_report.json` in the current directory. The script creates parent directories when necessary.

Output schema:

```json
{
  "deleted_employees": ["EMP00002"],
  "modified_employees": [
    {"id":"EMP00003","field":"Salary","old_value":50020,"new_value":55010}
  ]
}
```

## Method

1. Extract tables from every PDF page sequentially using `pdfplumber`. Select the table with a recognizable ID header and the most employee-ID rows. Repeated page headers are discarded.
2. Read the Excel sheet with `openpyxl`, locate its first nonblank header row, and normalize whitespace in headers and values.
3. Normalize matching header names without changing their displayed Excel spelling. Normalize IDs to uppercase strings, retaining zero padding. Reject duplicate IDs in either source.
4. Compute deleted IDs as `old_ids - new_ids`. For IDs present in both, compare each mutually available non-ID field. `Salary`, `Years`, and `Score` are parsed as numbers; all other fields are stripped text. A missing value only equals another missing value.
5. Sort deletions and modifications by employee ID (then field), write UTF-8 JSON to `output_path`, and print the same JSON.

## Validation

Before relying on the report, ensure the script exits successfully and that `diff_report.json` parses as JSON with exactly `deleted_employees` and `modified_employees`. If extraction fails, inspect the supplied PDF visually or with a PDF text tool: scanned PDFs require OCR, and unusual layouts may require adapting the table-extraction settings rather than guessing at results.
