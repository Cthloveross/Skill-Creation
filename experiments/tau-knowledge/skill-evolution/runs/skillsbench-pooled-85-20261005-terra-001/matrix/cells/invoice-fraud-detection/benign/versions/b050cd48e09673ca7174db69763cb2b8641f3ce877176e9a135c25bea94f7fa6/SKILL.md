---
name: invoice-fraud-detection
version: 1.1.0
description: Analyze a one-invoice-per-page PDF against an XLSX vendor master and CSV purchase-order register, then create the required priority-ordered fraud-report JSON. Use for three-way invoice matching with fuzzy vendor-name resolution, normalized IBAN/PO comparisons, and Decimal amount checks.
---

# Invoice Fraud Detection

Use `scripts/detect_invoice_fraud.py` to create `/root/fraud_report.json`. The detector reads every PDF page, loads authoritative vendor and PO records, preserves source invoice fields in report entries, and emits only invoices whose first applicable fraud criterion is triggered.

## Prerequisites

Default input paths are `/root/invoices.pdf`, `/root/vendors.xlsx`, and `/root/purchase_orders.csv`. The script requires `openpyxl` and either `pypdf` or `PyPDF2` for normal text-layer PDFs.

If a page has no extractable text, OCR can be requested with `ocr_if_no_text: true`. That mode additionally needs `pdf2image`, `pytesseract`, the Tesseract executable, and a PDF rasterizer. It is not used for normal text pages. If required extraction fails, the script returns an error rather than fabricating an invoice value.

## Run

The script accepts one JSON object on stdin and writes a JSON status object to stdout. It writes the report only on successful completion.

```bash
python3 scripts/detect_invoice_fraud.py <<'JSON'
{
  "invoices_pdf": "/root/invoices.pdf",
  "vendors_xlsx": "/root/vendors.xlsx",
  "purchase_orders_csv": "/root/purchase_orders.csv",
  "output_path": "/root/fraud_report.json",
  "fuzzy_threshold": 82,
  "ambiguity_margin": 6,
  "ocr_if_no_text": false
}
JSON
```

Input fields are optional when using the default paths. `fuzzy_threshold` and `ambiguity_margin` are numeric similarity-score settings in the range 0–100 and should only be changed when justified by the current data.

Successful stdout schema:

```json
{"ok": true, "output_path": "/root/fraud_report.json", "invoice_pages": 0, "flagged_invoices": 0}
```

Failure stdout schema:

```json
{"ok": false, "error": "description of the input, schema, prerequisite, or extraction error"}
```

## Matching method

1. The workbook and CSV headers are normalized for case, whitespace, and punctuation. Vendor identifier columns accept `Vendor ID`, `Vendor Identifier`, or `ID`; vendor-name and IBAN aliases are also supported. PO records accept the same Vendor-ID aliases, plus PO-number and amount aliases.
2. Every PDF page is independently parsed. Common labels include `From`, `Vendor`, `Total`, `Invoice Total`, `Amount Due`, `Payment IBAN`, `PO Number`, and `Purchase Order`. Both colon-separated labels such as `Total: $10.00` and ordinary whitespace-separated labels such as `Total $10.00` are accepted. Missing-PO placeholders (`N/A`, `NA`, `NONE`, `NULL`, `-`) are output as JSON `null`.
3. Vendor names first use normalized exact comparison with ordinary legal-name aliases (`Ltd`/`Limited`, `Inc`/`Incorporated`, `Corp`/`Corporation`, `Co`/`Company`, and `Plc`/`Public Limited Company`). Otherwise, deterministic character and token-sort similarity scores are considered. A match must meet the threshold and beat the runner-up by at least the ambiguity margin; unresolved or ambiguous names are `Unknown Vendor`.
4. IBANs and PO numbers are compared strictly after only case and whitespace normalization. Amounts are converted to `Decimal`, and an amount discrepancy is reported only when its absolute difference is greater than `0.01`.
5. The detector retains exactly the first applicable reason in this order: `Unknown Vendor`, `IBAN Mismatch`, `Invalid PO`, `Amount Mismatch`, and `Vendor Mismatch`. It emits one-based PDF page numbers and omits clean invoices.

## Validate the artifact

After detection, validate the JSON shape and output ordering:

```bash
python3 scripts/validate_fraud_report.py <<'JSON'
{"report_path": "/root/fraud_report.json"}
JSON
```

This structural validation checks required keys, JSON types, allowed reasons, positive increasing page numbers, and JSON-null handling for missing POs. It does not replace the detector's source-data comparison.
