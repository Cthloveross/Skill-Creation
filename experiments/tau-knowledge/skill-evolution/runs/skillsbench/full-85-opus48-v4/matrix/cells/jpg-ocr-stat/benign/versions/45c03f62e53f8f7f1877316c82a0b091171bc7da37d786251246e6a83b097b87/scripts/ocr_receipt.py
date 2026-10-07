"""Reusable helpers for receipt OCR -> (date, total_amount) extraction.

All functions are task-independent and operate on text/paths supplied at
runtime. No instance-specific answers are embedded.
"""
import os
import re

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")

# Keyword tiers, most specific first (see references/field_rules.md).
AMOUNT_TIERS = [
    ["GRAND TOTAL"],
    ["TOTAL RM", "TOTAL: RM"],
    ["TOTAL AMOUNT"],
    ["TOTAL", "AMOUNT", "TOTAL DUE", "AMOUNT DUE", "BALANCE DUE",
     "NETT TOTAL", "NET TOTAL"],
]
EXCLUSION_KEYWORDS = [
    "SUBTOTAL", "SUB TOTAL", "TAX", "GST", "SST",
    "DISCOUNT", "CHANGE", "CASH TENDERED",
]

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# number token possibly with comma grouping and optional decimals
NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2}|\d+")


def list_images(img_dir):
    """Return image basenames in img_dir sorted ascending."""
    names = []
    for n in os.listdir(img_dir):
        if n.lower().endswith(IMAGE_EXTS) and os.path.isfile(os.path.join(img_dir, n)):
            names.append(n)
    return sorted(names)


def ocr_lines(path):
    """Run Tesseract with a couple of PSM modes; return list of raw text lines.

    Lightweight preprocessing: grayscale, autocontrast, moderate upscale.
    Falls back gracefully if a pass errors.
    """
    from PIL import Image, ImageOps
    import pytesseract

    img = Image.open(path)
    try:
        img = img.convert("L")
        img = ImageOps.autocontrast(img)
        w, h = img.size
        scale = 1
        if max(w, h) < 1600:
            scale = 2
        if scale != 1:
            img = img.resize((w * scale, h * scale), Image.LANCZOS)
    except Exception:
        img = Image.open(path)

    texts = []
    for cfg in ("--psm 6", "--psm 4", "--psm 3"):
        try:
            texts.append(pytesseract.image_to_string(img, config=cfg))
        except Exception:
            pass
    lines = []
    for t in texts:
        for ln in t.splitlines():
            ln = ln.strip()
            if ln:
                lines.append(ln)
    return lines


def _parse_amount_tokens(line):
    """Return list of float values found in line (commas stripped).
    Keeps a flag whether each had an explicit decimal."""
    out = []
    for m in NUM_RE.finditer(line):
        tok = m.group(0)
        has_dec = "." in tok
        try:
            val = float(tok.replace(",", ""))
        except ValueError:
            continue
        out.append((val, has_dec))
    return out


def _best_amount_from_tokens(tokens):
    """Prefer tokens that have an explicit decimal point; take the last such.
    Otherwise take the last token."""
    if not tokens:
        return None
    dec = [v for (v, d) in tokens if d]
    if dec:
        return dec[-1]
    return tokens[-1][0]


def extract_amount(lines):
    """Apply keyword priority tiers to recognized lines.
    Returns a float or None."""
    upper = [ln.upper() for ln in lines]
    for tier in AMOUNT_TIERS:
        found = []  # amounts in document order for this tier
        for i, up in enumerate(upper):
            if any(ex in up for ex in EXCLUSION_KEYWORDS):
                continue
            if not any(kw in up for kw in tier):
                continue
            toks = _parse_amount_tokens(lines[i])
            val = _best_amount_from_tokens(toks)
            if val is None and i + 1 < len(lines):
                nxt = _parse_amount_tokens(lines[i + 1])
                val = _best_amount_from_tokens(nxt)
            if val is not None:
                found.append(val)
        if found:
            return found[-1]
    return None


def format_amount(val):
    """Format a float as a two-decimal string, or None."""
    if val is None:
        return None
    try:
        return "{:.2f}".format(float(val))
    except (TypeError, ValueError):
        return None


def _valid_ymd(y, m, d):
    if not (1 <= m <= 12):
        return False
    mdays = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not (1 <= d <= mdays[m - 1]):
        return False
    if y < 1900 or y > 2100:
        return False
    return True


def _norm_year(y):
    if y < 100:
        return 2000 + y
    return y


def _try_numeric_date(a, b, c):
    """a,b,c are integer strings. Resolve to (y,m,d) or None."""
    la, lc = len(a), len(c)
    try:
        ia, ib, ic = int(a), int(b), int(c)
    except ValueError:
        return None
    # Year-first form
    if la == 4:
        y, m, d = ia, ib, ic
        if _valid_ymd(y, m, d):
            return (y, m, d)
        return None
    # Day/Month ... Year form
    y = _norm_year(ic) if lc <= 4 else ic
    # decide which of ia/ib is day vs month
    cand = []
    # day-first preference
    cand.append((ia, ib))  # (day, month)
    cand.append((ib, ia))  # (month, day) -> i.e. ia=month
    # evidence overrides: if ia>12 it must be day; if ib>12 it must be day
    if ia > 12 and ib <= 12:
        order = [(ia, ib)]
    elif ib > 12 and ia <= 12:
        order = [(ib, ia)]
    else:
        order = cand
    for day, month in order:
        if _valid_ymd(y, month, day):
            return (y, month, day)
    return None


NUM_DATE_RE = re.compile(r"(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,4})")
MONTH_DATE_RE = re.compile(
    r"(\d{1,2})\s*[-/ ]\s*([A-Za-z]{3,9})\s*[-/ ,]*\s*(\d{2,4})")
MONTH_FIRST_RE = re.compile(
    r"([A-Za-z]{3,9})\s*[-/ ]\s*(\d{1,2})\s*[-/ ,]*\s*(\d{2,4})")


def extract_date(lines):
    """Return ISO YYYY-MM-DD string or None, from recognized lines."""
    for ln in lines:
        for m in NUM_DATE_RE.finditer(ln):
            res = _try_numeric_date(m.group(1), m.group(2), m.group(3))
            if res:
                y, mo, d = res
                return "{:04d}-{:02d}-{:02d}".format(y, mo, d)
    for ln in lines:
        for m in MONTH_DATE_RE.finditer(ln):
            mon = MONTHS.get(m.group(2)[:4].upper()) or MONTHS.get(m.group(2)[:3].upper())
            if not mon:
                continue
            try:
                d = int(m.group(1)); y = _norm_year(int(m.group(3)))
            except ValueError:
                continue
            if _valid_ymd(y, mon, d):
                return "{:04d}-{:02d}-{:02d}".format(y, mon, d)
        for m in MONTH_FIRST_RE.finditer(ln):
            mon = MONTHS.get(m.group(1)[:4].upper()) or MONTHS.get(m.group(1)[:3].upper())
            if not mon:
                continue
            try:
                d = int(m.group(2)); y = _norm_year(int(m.group(3)))
            except ValueError:
                continue
            if _valid_ymd(y, mon, d):
                return "{:04d}-{:02d}-{:02d}".format(y, mon, d)
    return None


def extract_record(path):
    """OCR one image, return dict with filename, date, total_amount, _lines."""
    name = os.path.basename(path)
    try:
        lines = ocr_lines(path)
    except Exception as e:  # OCR failure -> nulls
        return {"filename": name, "date": None, "total_amount": None,
                "_lines": [], "_error": str(e)}
    date = extract_date(lines)
    amount = format_amount(extract_amount(lines))
    return {"filename": name, "date": date, "total_amount": amount,
            "_lines": lines}
