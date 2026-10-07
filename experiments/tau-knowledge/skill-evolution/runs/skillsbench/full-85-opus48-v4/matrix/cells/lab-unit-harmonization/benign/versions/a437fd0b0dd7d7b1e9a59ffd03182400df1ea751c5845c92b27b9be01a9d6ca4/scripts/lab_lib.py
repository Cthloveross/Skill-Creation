"""Shared helpers for lab unit harmonization.

No dataset-specific answers are stored here. Plausibility ranges and conversion
factors are loaded from references/lab_registry.json.
"""
import csv
import io
import json
import os

MISSING_TOKENS = {"", "?", "na", "nan", "null", "none", "n/a", "-"}


def registry_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "references", "lab_registry.json")


def load_registry(path=None):
    path = path or registry_path()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("analytes", data) if isinstance(data, dict) else data


def is_missing(cell):
    return cell is None or str(cell).strip().lower() in MISSING_TOKENS


def parse_num(cell):
    """Parse a cell to float, applying decimal-comma and scientific notation.
    Returns float or None if not numeric."""
    if cell is None:
        return None
    s = str(cell).strip()
    if s == "":
        return None
    s = s.replace(" ", "")
    # decimal comma -> dot (task states ',' means '.'). Only safe when there is
    # no dot already acting as decimal separator alongside the comma.
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        # ambiguous mixed; drop the one that looks like a thousands separator
        # (left of the rightmost separator). Keep rightmost as decimal.
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def detect_delimiter(path, candidates=(",", ";", "\t", "|")):
    with open(path, "r", newline="", encoding="utf-8", errors="replace") as f:
        sample = "".join([f.readline() for _ in range(50)])
    best, best_score = ",", -1.0
    for d in candidates:
        try:
            rows = list(csv.reader(io.StringIO(sample), delimiter=d))
        except csv.Error:
            continue
        rows = [r for r in rows if r]
        if not rows:
            continue
        counts = [len(r) for r in rows]
        modal = max(set(counts), key=counts.count)
        if modal <= 1:
            continue
        consistency = counts.count(modal) / len(counts)
        score = consistency * modal
        if score > best_score:
            best, best_score = d, score
    return best


def read_csv(path):
    delim = detect_delimiter(path)
    with open(path, "r", newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f, delimiter=delim))
    if not rows:
        return [], []
    header = rows[0]
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    width = len(header)
    norm = []
    for r in body:
        if len(r) < width:
            r = r + [""] * (width - len(r))
        elif len(r) > width:
            r = r[:width]
        norm.append(r)
    return header, norm


def load_descriptions(path):
    """Return {short_name_lower: description_lower}. Takes the first two columns."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    header, rows = read_csv(path)
    for r in rows:
        if not r:
            continue
        key = r[0].strip().lower()
        desc = r[1].strip().lower() if len(r) > 1 else ""
        if key:
            out[key] = desc
    return out


def column_match_text(colname, descriptions):
    name = str(colname).strip().lower()
    desc = descriptions.get(name, "")
    return (name + " " + desc).strip()


def resolve_analyte(text, registry):
    """Longest-keyword wins; honor exclude keywords."""
    best, best_len = None, 0
    for entry in registry:
        excl = [x.lower() for x in entry.get("exclude", [])]
        if any(x in text for x in excl):
            continue
        for kw in entry.get("keywords", []):
            k = kw.lower()
            if k in text and len(k) > best_len:
                best, best_len = entry, len(k)
    return best


def is_numeric_column(values, threshold=0.8):
    present = [v for v in values if not is_missing(v)]
    if not present:
        return False
    ok = sum(1 for v in present if parse_num(v) is not None)
    return (ok / len(present)) >= threshold


def in_range(v, entry):
    lo = entry.get("min")
    hi = entry.get("max")
    if lo is not None and v < lo:
        return False
    if hi is not None and v > hi:
        return False
    return True


def harmonize_value(v, entry):
    """Return (new_value, converted_bool).
    Convert only when v is out of range and exactly one factor lands in range."""
    if entry is None:
        return v, False
    if in_range(v, entry):
        return v, False
    factors = entry.get("alt_factors", []) or []
    hits = [v * f for f in factors if in_range(v * f, entry)]
    if len(hits) >= 1:
        return hits[0], True
    return v, False


def fmt2(v):
    return "{:.2f}".format(v + 0.0)
