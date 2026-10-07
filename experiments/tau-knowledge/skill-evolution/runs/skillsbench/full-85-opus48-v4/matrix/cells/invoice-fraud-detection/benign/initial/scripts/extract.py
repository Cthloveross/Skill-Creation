"""PDF invoice field extraction helpers (reusable, task-independent method).

Parses one invoice per PDF page into {vendor_name, invoice_amount_raw, iban,
po_number} preserving raw source values. Extraction is label-driven with
regex fallbacks; add labels here if a real PDF uses different wording.
"""
import re

# Candidate line prefixes for each field (lower-cased comparison).
VENDOR_PREFIXES = [
    "from:", "vendor:", "vendor name:", "bill from:", "billed by:",
    "supplier:", "company:", "seller:", "from",
]
AMOUNT_PREFIXES = [
    "total amount due:", "total amount:", "amount due:", "total due:",
    "grand total:", "total:", "amount:", "invoice total:", "total",
]
IBAN_PREFIXES = [
    "payment iban:", "iban:", "bank account:", "account iban:",
    "account:", "iban",
]
PO_PREFIXES = [
    "po number:", "p.o. number:", "purchase order:", "purchase order no:",
    "po no:", "po#:", "po #:", "po:", "po number", "purchase order",
]

# Generic value regexes used as fallbacks when scanning whole page text.
IBAN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{10,32})\b")
PO_RE = re.compile(r"\b(P\.?O\.?[-\s]?[A-Za-z0-9][A-Za-z0-9-]*)\b", re.IGNORECASE)
MONEY_RE = re.compile(r"[-+]?[0-9][0-9,\.]*")


def _value_after_prefix(line, prefix):
    low = line.lower()
    idx = low.find(prefix)
    if idx < 0:
        return None
    return line[idx + len(prefix):].strip(" :\t")


def _first_match(lines, prefixes):
    # Longer, more specific prefixes first.
    for pref in sorted(prefixes, key=len, reverse=True):
        for line in lines:
            if pref in line.lower():
                val = _value_after_prefix(line, pref)
                if val:
                    return val
    return None


def parse_amount(raw):
    """Parse a monetary string to float, or None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = MONEY_RE.search(str(raw).replace(" ", ""))
    if not m:
        return None
    token = m.group(0).replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def extract_fields(page_text):
    """Return dict of raw extracted fields for one page."""
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]

    vendor = _first_match(lines, VENDOR_PREFIXES)

    amount_raw = _first_match(lines, AMOUNT_PREFIXES)

    iban = _first_match(lines, IBAN_PREFIXES)
    if iban:
        # Keep only the alphanumeric token if label line has extra words.
        m = IBAN_RE.search(iban.upper())
        iban = m.group(1) if m else iban.strip()
    else:
        m = IBAN_RE.search(page_text.upper())
        iban = m.group(1) if m else None

    po = _first_match(lines, PO_PREFIXES)
    if po:
        m = PO_RE.search(po)
        po = m.group(1) if m else po.strip()
    else:
        m = PO_RE.search(page_text)
        po = m.group(1) if m else None

    return {
        "vendor_name": vendor.strip() if vendor else None,
        "invoice_amount_raw": amount_raw,
        "invoice_amount": parse_amount(amount_raw),
        "iban": iban.strip() if isinstance(iban, str) else iban,
        "po_number": po.strip() if isinstance(po, str) else po,
    }


def read_pdf_pages(path):
    """Return list of page text strings. Tries several PDF backends."""
    errors = []
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(path) as pdf:
            for pg in pdf.pages:
                pages.append(pg.extract_text() or "")
        return pages
    except Exception as e:  # noqa: BLE001
        errors.append(f"pdfplumber: {e}")
    for modname in ("pypdf", "PyPDF2"):
        try:
            mod = __import__(modname)
            reader = mod.PdfReader(path)
            return [(pg.extract_text() or "") for pg in reader.pages]
        except Exception as e:  # noqa: BLE001
            errors.append(f"{modname}: {e}")
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.layout import LAParams  # noqa: F401
        import pdfminer.high_level as hl  # noqa: F401
        # pdfminer has no simple per-page split here; use form feed if present.
        text = extract_text(path)
        if "\x0c" in text:
            parts = text.split("\x0c")
            # trailing empty from final form feed
            if parts and parts[-1].strip() == "":
                parts = parts[:-1]
            return parts
        return [text]
    except Exception as e:  # noqa: BLE001
        errors.append(f"pdfminer: {e}")
    raise RuntimeError(
        "Could not read PDF with any backend. Install one of pdfplumber, "
        "pypdf, or pdfminer.six. Details: " + " | ".join(errors)
    )
