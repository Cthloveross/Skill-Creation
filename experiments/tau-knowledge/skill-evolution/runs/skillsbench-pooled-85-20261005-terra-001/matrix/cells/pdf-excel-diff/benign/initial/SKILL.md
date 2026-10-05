---
name: employee-pdf-excel-diff
description: Extract a text-based employee table from an old multi-page PDF, compare it with a current XLSX workbook by employee ID, and write a deterministic JSON report of deleted employees and field-level modifications. Use when the PDF is the baseline and the Excel file is the newer version.
---

# Employee PDF-to-Excel Difference Report

Use `scripts/create_diff_report.py` to create the required report. It reads all supplied paths at runtime and does not contain employee records or expected differences.

## Prerequisites

- The PDF must contain extractable text arranged as a table (not only scanned images).
- Python packages `pdfplumber` and `openpyxl` must be available to the execution environment.
- Both sources must have a header row containing an ID column named `ID`, `Employee ID`, or `EmployeeID` (case and whitespace insensitive).
- Employee IDs must follow the `EMP` plus five-digit convention. The workbook's first worksheet is used.

The script tries PDF line-based/default and whitespace-based table extraction across every page, removes repeated headers by recognizing header rows, and selects the extraction with the most valid employee rows. It rejects ambiguous duplicate IDs, malformed IDs, missing comparable columns, malformed numeric values, and non-tabular/scanned PDFs rather than producing a potentially misleading report.

## Runtime interface

The script receives one JSON object on standard input:

```json
{
  "pdf_path": "/absolute/path/to/old_records.pdf",
  "xlsx_path": "/absolute/path/to/current_records.xlsx",
  "output_path": "/absolute/path/to/diff_report.json"
}
```

It writes `output_path` and emits a small JSON status object on standard output. A nonzero exit status and `{"ok": false, "error": ...}` indicate that input extraction or validation failed.

Run it through the supplied script runtime with the task's PDF as `pdf_path`, the task's Excel workbook as `xlsx_path`, and the required report destination as `output_path`.

## Semantics and validation

- PDF records are **old** records; workbook records are **new** records.
- A deleted employee is present in the PDF and absent from the workbook.
- Modifications are reported for every changed common field for IDs present in both sources. `old_value` is always from PDF and `new_value` always from Excel.
- `Salary`, `Years`, and `Score` are parsed into JSON numbers. Other fields are stripped text strings.
- IDs preserve the `EMP00000` representation.
- The output validator checks the exact top-level structure, ID ordering, modification ordering (ID then field), required modification keys, and numeric/text JSON types before the report is committed atomically.

After a successful run, use the created JSON file as the requested artifact; do not reverse old and new values or manually reformat numeric values as strings.
