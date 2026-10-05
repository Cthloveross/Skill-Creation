---
name: invoice-fraud-detection
version: 1.0.0
description: Analyze one-invoice-per-page PDF invoices against an XLSX vendor master and CSV purchase-order register, then write the required priority-ordered fraud report JSON. Use when vendor-name fuzzy resolution, exact normalized IBAN/PO matching, and Decimal amount checks are required.
---

# Invoice Fraud Detection

Use `scripts/detect_invoice_fraud.py` to create the required report. It reads every PDF page, loads the authoritative vendor and PO sources, resolves vendor names, applies the required single-reason priority order, and writes only flagged invoices.

## Prerequisites

The default runtime inputs are `/root/invoices.pdf`, `/root/vendors.xlsx`, and `/root/purchase_orders.csv`. The script uses `openpyxl` for XLSX files and either `pypdf` or `PyPDF2` for text-layer PDF extraction. Before execution, ensure those Python packages are available.

The supplied invoice PDF is expected to have a usable text layer. If pages are scanned or extraction yields no text, enable `ocr_if_no_text`; that mode additionally requires `pdf2image`, `pytesseract`, the Tesseract executable, and a PDF rasterizer such as Poppler. OCR is only used for pages without extractable text and extraction failures are reported rather than silently inventing fields.

## Run

The script receives one JSON object on stdin and emits one JSON status object on stdout. All paths are configurable; this command uses the task defaults and produces the required artifact.

```bash
python3 scripts/detect_invoice_fraud.py <<'JSON'
{
  "invoices_pdf": "/root/invoices.pdf",
  "vendors_xlsx": "/root/vendors.xlsx",
  "purchase_orders_csv": "/root/purchase_orders.csv",
  "output_path": "/root/fraud_report.json",
  "fuzzy_threshold": 80,
  "ambiguity_margin": 3,
  "ocr_if_no_text": false
}
JSON
```

The output status has this schema:

```json
{"ok": true, "output_path": "/root/fraud_report.json", "invoice_pages": 0, "flagged_invoices": 0}
```

On a prerequisite, input-schema, duplicate-key, or extraction error it instead emits `{"ok": false, "error": "..."}` and does not claim a completed report.

## Method and decision rules

1. Vendor and PO headers are located case/whitespace-insensitively. Required logical columns are Vendor ID, vendor Name, IBAN, PO Number, and Amount. The script rejects absent required columns and duplicate normalized PO numbers because either condition makes authoritative lookup ambiguous.
2. Invoice text is processed page by page. It recognizes common labeled forms of vendor, invoice total, IBAN, and PO number, preserving the extracted display values in report records. Empty and conventional missing PO placeholders (`N/A`, `NA`, `NONE`, `NULL`, or `-`) become JSON `null`.
3. Vendor matching first compares canonicalized names, including common legal-suffix expansions and token reordering. It then uses a deterministic token-sort `SequenceMatcher` score. A best score below `fuzzy_threshold`, or a close runner-up within `ambiguity_margin`, is unresolved and therefore `Unknown Vendor`. These knobs can be raised for conservative matching or adjusted using labeled data; they are not identifiers and do not relax IBAN or PO matching.
4. IBANs and PO numbers are matched strictly after removal of whitespace and conversion to uppercase. Monetary amounts are parsed as `Decimal`; an absolute difference is an `Amount Mismatch` only when it is greater than `0.01`.
5. For each page, exactly the first applicable reason is retained: `Unknown Vendor`, `IBAN Mismatch`, `Invalid PO`, `Amount Mismatch`, then `Vendor Mismatch`. Clean invoices are omitted. Human-facing page numbering is one-based.

If an invoice amount cannot be parsed while its PO is valid, it is treated as an `Amount Mismatch`; a missing invoice IBAN for a resolved vendor is an `IBAN Mismatch`. This makes missing required payment/amount evidence fail closed while retaining the source value as `null`.

## Validate the produced artifact

After detection, validate the JSON contract and deterministic ordering:

```bash
python3 scripts/validate_fraud_report.py <<'JSON'
{"report_path": "/root/fraud_report.json"}
JSON
```

A successful validation returns an `ok: true` JSON object. Validation confirms that the report is a list, records have exactly the required keys, page numbers are positive integers and increasing, reasons are allowed, PO absence is JSON null, and JSON types are appropriate. It does not replace the source-data matching performed by the detector.
