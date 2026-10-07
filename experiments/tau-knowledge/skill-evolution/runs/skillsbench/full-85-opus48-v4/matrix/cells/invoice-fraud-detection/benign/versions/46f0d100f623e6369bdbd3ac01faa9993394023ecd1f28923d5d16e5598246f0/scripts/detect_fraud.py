#!/usr/bin/env python3
"""End-to-end invoice fraud detection.

Reads a JSON config object from stdin, writes the fraud report (array of
flagged invoices) to stdout and to the configured output path.

Config keys (all optional; defaults match the current task):
  invoices_pdf, vendors_xlsx, purchase_orders_csv, output,
  threshold (fuzzy, 0-100, default 80), amount_tolerance (default 0.01),
  debug_extract (bool) -> print raw text + parsed fields instead of running.

Priority order of reasons (first applicable wins):
  Unknown Vendor > IBAN Mismatch > Invalid PO > Amount Mismatch > Vendor Mismatch
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import extract as ex  # noqa: E402
import masters as ms  # noqa: E402

DEFAULTS = {
    "invoices_pdf": "/root/invoices.pdf",
    "vendors_xlsx": "/root/vendors.xlsx",
    "purchase_orders_csv": "/root/purchase_orders.csv",
    "output": "/root/fraud_report.json",
    "threshold": 80.0,
    "amount_tolerance": 0.01,
}


def _fuzzy_scorer():
    try:
        from rapidfuzz import fuzz

        def score(a, b):
            return max(fuzz.token_sort_ratio(a, b), fuzz.ratio(a, b))
        return score
    except Exception:  # noqa: BLE001
        import difflib

        def score(a, b):
            return difflib.SequenceMatcher(None, a, b).ratio() * 100.0
        return score


def resolve_vendor(name, vendors, scorer, threshold):
    """Return (best_vendor_dict_or_None, best_score). None if below threshold."""
    if not name:
        return None, 0.0
    q = name.strip().lower()
    best = None
    best_score = -1.0
    for v in vendors:
        s = scorer(q, v["name"].strip().lower())
        if s > best_score:
            best_score = s
            best = v
    if best is not None and best_score >= threshold:
        return best, best_score
    return None, best_score


def classify(fields, vendors, pos, scorer, threshold, tol):
    """Return reason string or None (clean). fields: parsed invoice dict."""
    vendor, _ = resolve_vendor(fields.get("vendor_name"), vendors, scorer, threshold)
    # 1. Unknown Vendor
    if vendor is None:
        return "Unknown Vendor"
    # 2. IBAN Mismatch (exact match after normalization)
    inv_iban = ms.norm_exact(fields.get("iban"))
    mas_iban = ms.norm_exact(vendor.get("iban"))
    if inv_iban != mas_iban:
        return "IBAN Mismatch"
    # 3. Invalid PO (absent or not in register)
    po_raw = fields.get("po_number")
    po_key = ms.norm_exact(po_raw)
    if not po_key or po_key not in pos:
        return "Invalid PO"
    po = pos[po_key]
    # 4. Amount Mismatch
    inv_amt = fields.get("invoice_amount")
    po_amt = ex.parse_amount(po.get("amount_raw"))
    if inv_amt is None or po_amt is None or abs(inv_amt - po_amt) > tol:
        return "Amount Mismatch"
    # 5. Vendor Mismatch
    if ms.norm_exact(po.get("vendor_id")) != ms.norm_exact(vendor.get("vendor_id")):
        return "Vendor Mismatch"
    return None


def build_report(cfg):
    pages = ex.read_pdf_pages(cfg["invoices_pdf"])
    vendors = ms.load_vendors(cfg["vendors_xlsx"])
    pos = ms.load_purchase_orders(cfg["purchase_orders_csv"])
    scorer = _fuzzy_scorer()
    threshold = float(cfg["threshold"])
    tol = float(cfg["amount_tolerance"])

    report = []
    for i, text in enumerate(pages):
        fields = ex.extract_fields(text)
        reason = classify(fields, vendors, pos, scorer, threshold, tol)
        if reason is None:
            continue
        report.append({
            "invoice_page_number": i + 1,  # 1-based
            "vendor_name": fields.get("vendor_name"),
            "invoice_amount": fields.get("invoice_amount"),
            "iban": fields.get("iban"),
            "po_number": fields.get("po_number") if fields.get("po_number") else None,
            "reason": reason,
        })
    return report


def debug_extract(cfg):
    pages = ex.read_pdf_pages(cfg["invoices_pdf"])
    out = []
    for i, text in enumerate(pages):
        out.append({
            "page": i + 1,
            "raw_text": text,
            "parsed": ex.extract_fields(text),
        })
    return out


def main():
    raw = sys.stdin.read().strip()
    cfg = dict(DEFAULTS)
    if raw:
        try:
            user = json.loads(raw)
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if v is not None})
        except json.JSONDecodeError:
            pass

    if cfg.get("debug_extract"):
        print(json.dumps(debug_extract(cfg), indent=2, ensure_ascii=False))
        return

    report = build_report(cfg)
    out_path = cfg["output"]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
