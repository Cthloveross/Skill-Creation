#!/usr/bin/env python3
"""Validate a fraud_report.json against the public request's structural rules.

stdin JSON: {"report": "/root/fraud_report.json", "invoices_pdf": "/root/invoices.pdf"}
Both keys optional (defaults match the task). Prints a JSON object with
"ok" (bool) and "problems" (list). Derives checks from the request only, not
from any expected answer set.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

ALLOWED_REASONS = {
    "Unknown Vendor", "IBAN Mismatch", "Invalid PO",
    "Amount Mismatch", "Vendor Mismatch",
}


def main():
    raw = sys.stdin.read().strip()
    cfg = {"report": "/root/fraud_report.json", "invoices_pdf": "/root/invoices.pdf"}
    if raw:
        try:
            u = json.loads(raw)
            if isinstance(u, dict):
                cfg.update({k: v for k, v in u.items() if v})
        except json.JSONDecodeError:
            pass

    problems = []
    num_pages = None
    try:
        import extract as ex
        num_pages = len(ex.read_pdf_pages(cfg["invoices_pdf"]))
    except Exception as e:  # noqa: BLE001
        problems.append(f"could not count pages: {e}")

    try:
        with open(cfg["report"], encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "problems": [f"cannot load report: {e}"]}))
        return

    if not isinstance(data, list):
        problems.append("report top-level is not a JSON array")
        data = []

    seen = set()
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            problems.append(f"entry {idx} is not an object")
            continue
        pg = item.get("invoice_page_number")
        if not isinstance(pg, int):
            problems.append(f"entry {idx}: invoice_page_number not int")
        else:
            if pg in seen:
                problems.append(f"duplicate page {pg}")
            seen.add(pg)
            if pg < 1 or (num_pages is not None and pg > num_pages):
                problems.append(f"page {pg} out of range 1..{num_pages}")
        if item.get("reason") not in ALLOWED_REASONS:
            problems.append(f"entry {idx}: bad reason {item.get('reason')!r}")
        po = item.get("po_number")
        if not (po is None or isinstance(po, str)):
            problems.append(f"entry {idx}: po_number must be null or string")
        amt = item.get("invoice_amount")
        if not (amt is None or isinstance(amt, (int, float))):
            problems.append(f"entry {idx}: invoice_amount must be a number")
        for key in ("vendor_name", "iban"):
            if key not in item:
                problems.append(f"entry {idx}: missing {key}")

    print(json.dumps({"ok": not problems, "problems": problems}, indent=2))


if __name__ == "__main__":
    main()
