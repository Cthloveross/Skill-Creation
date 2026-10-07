"""Load vendor master (xlsx) and PO register (csv) with header-meaning column
resolution. Reusable: discovers roles from header text, not fixed positions.
"""
import csv
import re


def _norm_header(h):
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _pick(headers, *candidates):
    """Return index of first header whose normalized form matches/contains a
    candidate normalized token."""
    norm = [_norm_header(h) for h in headers]
    cand = [_norm_header(c) for c in candidates]
    # exact match first
    for c in cand:
        for i, h in enumerate(norm):
            if h == c:
                return i
    # contains match
    for c in cand:
        for i, h in enumerate(norm):
            if c and c in h:
                return i
    return None


def load_vendors(path):
    """Return list of dicts: {vendor_id, name, iban} (raw strings)."""
    try:
        import openpyxl
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("openpyxl required to read .xlsx: " + str(e))
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(c) if c is not None else "" for c in rows[0]]
    i_id = _pick(headers, "vendorid", "vendor id", "id")
    i_name = _pick(headers, "name", "vendorname", "vendor name")
    i_iban = _pick(headers, "iban", "authorizediban", "bankaccount", "account")
    if i_name is None:
        raise RuntimeError(f"Could not find vendor Name column in {headers}")
    out = []
    for r in rows[1:]:
        if r is None:
            continue
        def g(i):
            return "" if (i is None or i >= len(r) or r[i] is None) else str(r[i]).strip()
        name = g(i_name)
        if not name:
            continue
        out.append({"vendor_id": g(i_id), "name": name, "iban": g(i_iban)})
    return out


def load_purchase_orders(path):
    """Return dict keyed by normalized PO number -> {po_number, amount, vendor_id}."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return {}
    headers = rows[0]
    i_po = _pick(headers, "ponumber", "po number", "po", "purchaseorder")
    i_amt = _pick(headers, "amount", "total", "poamount")
    i_vid = _pick(headers, "vendorid", "vendor id", "id")
    if i_po is None:
        raise RuntimeError(f"Could not find PO Number column in {headers}")
    out = {}
    for r in rows[1:]:
        if not r or all((c or "").strip() == "" for c in r):
            continue
        def g(i):
            return "" if (i is None or i >= len(r)) else (r[i] or "").strip()
        po_raw = g(i_po)
        if not po_raw:
            continue
        key = norm_exact(po_raw)
        out[key] = {
            "po_number": po_raw,
            "amount_raw": g(i_amt),
            "vendor_id": g(i_vid),
        }
    return out


def norm_exact(value):
    """Normalize an exact-match field (IBAN/PO): strip internal whitespace,
    upper-case. Returns '' for None."""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).upper()
