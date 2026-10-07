---
name: invoice-fraud-report
description: Analyze one-invoice-per-page PDFs against an XLSX vendor master and CSV purchase-order register, then create the required priority-ordered JSON fraud report. Use when invoice fields are text-extractable and the report must contain only flagged pages.
---

# Invoice fraud report

Run `scripts/generate_fraud_report.py` from the Skill directory. It reads a JSON configuration from standard input, writes the report file, and emits a JSON execution summary on standard output.

Default configuration uses the task paths, so this produces the required deliverable:

```sh
printf '{}' | python3 scripts/generate_fraud_report.py
```

Optional input schema:

```json
{
  "invoices_pdf": "/root/invoices.pdf",
  "vendors_xlsx": "/root/vendors.xlsx",
  "purchase_orders_csv": "/root/purchase_orders.csv",
  "output_path": "/root/fraud_report.json",
  "fuzzy_threshold": 85
}
```

All path values are optional. `fuzzy_threshold` is a 0--100 name-similarity threshold; keep it high enough that only minor spelling or legal-suffix variations resolve. The script first recognizes normalized exact names (including common company suffix variants), then uses a token-aware edit similarity score. A tied or near-tied fuzzy result is deliberately unresolved and is reported as `Unknown Vendor` rather than silently associating it with an arbitrary vendor.

The script discovers common header spelling variants in the master files and rejects missing required columns or duplicate Vendor IDs/PO numbers, since those make an authoritative comparison impossible. It extracts every PDF page, reports pages using 1-based numbering, and normalizes only whitespace/case for IBAN and PO comparisons. The displayed invoice fields are extracted source values (outer whitespace removed); an absent/blank/N/A PO is serialized as JSON `null`.

Reasons are evaluated exactly once in this order: `Unknown Vendor`, `IBAN Mismatch`, `Invalid PO`, `Amount Mismatch`, then `Vendor Mismatch`. Amounts use `Decimal` and are flagged only when the absolute difference is greater than `0.01`. Clean invoices are omitted.

## Validation

After execution, inspect the emitted summary and parse the report as JSON. Confirm it is an array and every item has exactly these keys:

- `invoice_page_number`, `vendor_name`, `invoice_amount`, `iban`, `po_number`, `reason`

Also confirm page numbers are positive and unique, reasons are from the five allowed strings, and all referenced page numbers are no greater than `pages_processed` in the summary. If the PDF has no extractable text, the script exits with an error rather than manufacturing invoice fields; use an OCR-capable extraction process first, preserving one page per invoice, then rerun against a text-extractable PDF.
