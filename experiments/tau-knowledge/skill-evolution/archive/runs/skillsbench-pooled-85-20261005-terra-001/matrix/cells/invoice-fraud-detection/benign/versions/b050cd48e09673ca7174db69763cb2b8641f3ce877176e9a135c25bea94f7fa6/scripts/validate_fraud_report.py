#!/usr/bin/env python3
"""Validate fraud_report.json structure. stdin: {"report_path": str?}."""
import json
import math
import sys

REQUIRED_KEYS = {
    "invoice_page_number", "vendor_name", "invoice_amount", "iban", "po_number", "reason"
}
REASONS = {
    "Unknown Vendor", "IBAN Mismatch", "Invalid PO", "Amount Mismatch", "Vendor Mismatch"
}


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    return 1


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            return fail("stdin must contain a JSON object")
        path = config.get("report_path", "/root/fraud_report.json")
        with open(path, "r", encoding="utf-8") as handle:
            report = json.load(handle)
    except Exception as exc:
        return fail(str(exc))
    if not isinstance(report, list):
        return fail("report root must be a JSON array")
    previous_page = 0
    for index, record in enumerate(report):
        if not isinstance(record, dict) or set(record) != REQUIRED_KEYS:
            return fail("record %d must have exactly the required keys" % index)
        page = record["invoice_page_number"]
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            return fail("record %d has invalid invoice_page_number" % index)
        if page <= previous_page:
            return fail("records must be in strictly increasing page order")
        previous_page = page
        if record["reason"] not in REASONS:
            return fail("record %d has an unsupported reason" % index)
        if record["po_number"] is not None and not isinstance(record["po_number"], str):
            return fail("record %d po_number must be a string or null" % index)
        for key in ("vendor_name", "iban"):
            if record[key] is not None and not isinstance(record[key], str):
                return fail("record %d %s must be a string or null" % (index, key))
        amount = record["invoice_amount"]
        if amount is not None:
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                return fail("record %d invoice_amount must be a JSON number or null" % index)
            if not math.isfinite(amount):
                return fail("record %d invoice_amount must be finite" % index)
    print(json.dumps({"ok": True, "report_path": path, "flagged_invoices": len(report)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
