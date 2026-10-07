---
name: invoice-fraud-detection
description: >-
  Detect fraudulent invoices in an accounts-payable three-way match. Given a
  multi-page PDF of invoices (one invoice per page), a vendor master file
  (Vendor ID, Name, authorized IBAN) and a purchase-order register (PO Number,
  Amount, Vendor ID), extract each invoice's fields, run priority-ordered fraud
  checks (Unknown Vendor > IBAN Mismatch > Invalid PO > Amount Mismatch >
  Vendor Mismatch) and write a JSON report of only the flagged invoices with
  1-based page numbers. Use when asked to analyze invoices/vendors/POs for
  fraud and produce fraud_report.json.
---

# Invoice Fraud Detection

## When to use

Use this Skill when the task supplies an invoices PDF, a vendor master
(spreadsheet) and a purchase-order register (CSV), and asks for a structured
fraud report. The current task's concrete paths are:

- `/root/invoices.pdf` — one invoice per page
- `/root/vendors.xlsx` — approved vendors: Vendor ID, Name, authorized IBAN
- `/root/purchase_orders.csv` — valid POs: PO Number, Amount, Vendor ID
- output: `/root/fraud_report.json`

Always read the actual supplied files at runtime; do not assume column order,
vendor names, counts or answers. The script discovers columns by header meaning.

## Detection method (fixed priority order)

For every page, extract `vendor_name`, `invoice_amount`, `iban`, `po_number`
and apply the checks below, stopping at the FIRST that matches. Report only one
reason per flagged invoice. Clean invoices (all checks pass) are omitted.

1. **Unknown Vendor** — the invoice vendor name does not resolve to any name in
   the vendor master via fuzzy matching above the confidence threshold.
   Short-circuits all later checks (no authoritative record to compare against).
2. **IBAN Mismatch** — vendor resolved, but the invoice IBAN (normalized:
   whitespace removed, upper-cased) differs from the master IBAN by exact match.
   IBAN comparison is strict, never fuzzy.
3. **Invalid PO** — the referenced PO number is absent from the invoice OR not
   found in the PO register (both are "Invalid PO"). Normalize PO (strip
   whitespace, upper-case) before the exact lookup.
4. **Amount Mismatch** — the PO exists; `abs(invoice_amount - po_amount) > 0.01`.
   Parse monetary strings to float; compare with tolerance, never `==`.
5. **Vendor Mismatch** — PO valid and amount matches, but the PO's Vendor ID
   differs from the Vendor ID of the resolved invoice vendor.

Reasons in the report use exactly these strings: `"Unknown Vendor"`,
`"IBAN Mismatch"`, `"Invalid PO"`, `"Amount Mismatch"`, `"Vendor Mismatch"`.

### Field conventions
- **Page numbers are 1-based** in the report (PDF libraries index from 0;
  add 1).
- **po_number is `null`** only when the invoice references no PO at all. When a
  (possibly invalid) PO value is present on the invoice, preserve it verbatim.
- Preserve extracted `vendor_name` and `iban` exactly as read. `invoice_amount`
  is a JSON number (float). Never emit placeholder strings like "N/A".

### Fuzzy vendor resolution
Match the invoice vendor name against the vendor master **Name** column only
(not IDs). Compute a 0–100 similarity (rapidfuzz token_sort_ratio/ratio if
available, else difflib). Take the best-scoring master row; if its score is at
or above the threshold, treat the vendor as known and use that row's Vendor ID
and IBAN for later checks; otherwise it is an Unknown Vendor. The threshold is a
configuration parameter (default 80). There is no universal cutoff — if the
executor observes mis-resolutions, adjust `--threshold` / the `threshold` field
and re-inspect best vs. runner-up scores rather than hardcoding answers.

## Running

`scripts/detect_fraud.py` is the end-to-end entrypoint. It reads a JSON config
object from stdin and writes the report JSON to stdout AND to the output path.

Input schema (all keys optional; defaults match the current task):
```json
{
  "invoices_pdf": "/root/invoices.pdf",
  "vendors_xlsx": "/root/vendors.xlsx",
  "purchase_orders_csv": "/root/purchase_orders.csv",
  "output": "/root/fraud_report.json",
  "threshold": 80,
  "amount_tolerance": 0.01
}
```

Output schema (also written to `output`): a JSON array of objects with
`invoice_page_number` (int, 1-based), `vendor_name` (string), `invoice_amount`
(number), `iban` (string|null), `po_number` (string|null), `reason` (string).

Example invocation (executor, from any directory):
```bash
echo '{}' | python3 /app/environment/skills/current/scripts/detect_fraud.py
cat /root/fraud_report.json
```
or with explicit paths:
```bash
echo '{"invoices_pdf":"/root/invoices.pdf","vendors_xlsx":"/root/vendors.xlsx","purchase_orders_csv":"/root/purchase_orders.csv","output":"/root/fraud_report.json"}' \
  | python3 /app/environment/skills/current/scripts/detect_fraud.py
```

### Inspecting extraction first (recommended during evolution)
The script also accepts `{"debug_extract": true}` which, instead of running the
full pipeline, prints the raw per-page text and the parsed fields so the
executor can confirm the PDF's actual field labels/format before trusting the
report:
```bash
echo '{"debug_extract": true}' | python3 .../scripts/detect_fraud.py
```
If a field label in the real PDF is not among the recognized prefixes, add it to
the prefix lists / regexes in `scripts/extract.py` (a reusable fix), rather than
patching one output file.

## Dependencies & fallbacks
- PDF text: tries `pdfplumber`, then `pypdf`/`PyPDF2`, then `pdfminer.six`.
- Excel: `openpyxl`.
- Fuzzy: `rapidfuzz` if present, else stdlib `difflib`.
If a required library for the supplied formats is missing, the script fails with
a clear message naming the missing package; install it with pip in the terminal
and rerun. If a page yields no extractable text (scanned image), the script
still emits the page with whatever was parsed (nulls) so no page is silently
dropped — every page is evaluated.

## Validation before trusting output
After running, verify (see `scripts/validate_report.py`, which reads the report
path from stdin as `{"report":"/root/fraud_report.json"}`):
- output parses as a JSON array;
- every `invoice_page_number` is an int in `[1, num_pages]` and unique;
- every `reason` is one of the five allowed strings;
- flagged pages are a subset of all pages; clean pages are absent;
- `po_number` is `null` or a string; `invoice_amount` is a number.
These checks derive from the public request, not from any expected answer set.
