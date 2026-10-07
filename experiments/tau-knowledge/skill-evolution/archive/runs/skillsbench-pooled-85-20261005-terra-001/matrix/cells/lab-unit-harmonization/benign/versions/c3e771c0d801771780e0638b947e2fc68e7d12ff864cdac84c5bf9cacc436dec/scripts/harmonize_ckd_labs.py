#!/usr/bin/env python3
"""CSV clinical-lab unit harmonizer; JSON stdin -> JSON stdout.

Uses only Python's standard library. Conversion factors are established
molar-mass / scale relationships and are independent of a specific dataset.
"""
import csv
import json
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path

getcontext().prec = 34
MISSING = {"", "na", "n/a", "nan", "null", "none", "?", "missing", "not available"}

# key: aliases, broad conventional-unit screening interval, alternate->US factors.
# Intervals are selection guards for an adult CKD-oriented extract, not diagnostic
# reference intervals. Entries and factors are analyte-specific.
REGISTRY = {
    "creatinine": (["creatinine", "serum creat", "s creat", "scr"], (Decimal("0.1"), Decimal("25")), [("umol", Decimal("0.011312217")), ("micromol", Decimal("0.011312217"))]),
    "bun": (["blood urea nitrogen", "bun", "urea nitrogen"], (Decimal("1"), Decimal("200")), [("urea mmol", Decimal("2.80112")), ("urea mg", Decimal("0.4667")), ("mmol", Decimal("2.80112"))]),
    "urea": (["serum urea", "blood urea", "urea"], (Decimal("2"), Decimal("430")), [("mmol", Decimal("6.006")), ("mg dl bun", Decimal("2.14"))]),
    "glucose": (["glucose", "blood sugar"], (Decimal("20"), Decimal("1000")), [("mmol", Decimal("18.0182"))]),
    "hemoglobin": (["hemoglobin", "haemoglobin", " hgb", "hb "], (Decimal("3"), Decimal("25")), [("g l", Decimal("0.1"))]),
    "hematocrit": (["hematocrit", "haematocrit", " hct"], (Decimal("10"), Decimal("75")), [("fraction", Decimal("100")), ("l l", Decimal("100"))]),
    "albumin_serum": (["serum albumin", "plasma albumin", "albumin"], (Decimal("0.5"), Decimal("7")), [("g l", Decimal("0.1"))]),
    "protein_total": (["total protein", "serum protein", "plasma protein"], (Decimal("2"), Decimal("12")), [("g l", Decimal("0.1"))]),
    "calcium_total": (["total calcium", "serum calcium", "calcium"], (Decimal("3"), Decimal("20")), [("mmol", Decimal("4.008"))]),
    "phosphorus": (["phosphorus", "phosphate", "phos"], (Decimal("0.5"), Decimal("20")), [("mmol", Decimal("3.097"))]),
    "magnesium": (["magnesium", " mg "], (Decimal("0.5"), Decimal("8")), [("mmol", Decimal("2.4305"))]),
    "bilirubin_total": (["total bilirubin", "bilirubin"], (Decimal("0.05"), Decimal("40")), [("umol", Decimal("0.0584795")), ("micromol", Decimal("0.0584795"))]),
    "uric_acid": (["uric acid", "urate"], (Decimal("0.5"), Decimal("30")), [("umol", Decimal("0.016813"))]),
    "cholesterol_total": (["total cholesterol", "cholesterol"], (Decimal("50"), Decimal("600")), [("mmol", Decimal("38.67"))]),
    "triglycerides": (["triglyceride", "triglycerides", "tg "], (Decimal("15"), Decimal("3000")), [("mmol", Decimal("88.57"))]),
    "hdl": (["hdl cholesterol", "high density lipoprotein", " hdl"], (Decimal("5"), Decimal("200")), [("mmol", Decimal("38.67"))]),
    "ldl": (["ldl cholesterol", "low density lipoprotein", " ldl"], (Decimal("5"), Decimal("600")), [("mmol", Decimal("38.67"))]),
    "iron": (["serum iron", " iron"], (Decimal("5"), Decimal("500")), [("umol", Decimal("5.5845"))]),
    "tibc": (["total iron binding", "tibc"], (Decimal("50"), Decimal("800")), [("umol", Decimal("5.5845"))]),
    "transferrin": (["transferrin"], (Decimal("0.5"), Decimal("6")), [("g l", Decimal("0.1"))]),
    "crp": (["c reactive protein", "c-reactive protein", " crp"], (Decimal("0"), Decimal("100")), [("mg l", Decimal("0.1"))]),
    "vitamin_d": (["vitamin d", "25 oh d", "25ohd"], (Decimal("1"), Decimal("200")), [("nmol", Decimal("0.40064"))]),
    # HbA1c is intentionally distinct from hemoglobin and glucose. Conventional
    # HbA1c is percent; only a genuine fraction may be scaled to percent.
    "a1c": (["hemoglobin a1c", "hba1c", "glycated hemoglobin", "glycosylated hemoglobin"], (Decimal("3"), Decimal("20")), [("fraction", Decimal("100"))]),
    "urine_albumin": (["urine albumin", "urinary albumin", "microalbumin"], (Decimal("0"), Decimal("2000")), [("mg l", Decimal("0.1"))]),
    "acr": (["albumin creatinine ratio", "urine acr", "uacr"], (Decimal("0"), Decimal("20000")), [("mg mmol", Decimal("8.84"))]),
    "urine_protein": (["urine protein", "urinary protein", "proteinuria"], (Decimal("0"), Decimal("2000")), [("g l", Decimal("100"))]),
}

# Richer or potentially overlapping identities must precede broad terms.
PRIORITY = [
    "a1c", "acr", "urine_albumin", "urine_protein", "albumin_serum",
    "protein_total", "cholesterol_total", "hdl", "ldl", "triglycerides",
    "bilirubin_total", "bun", "urea", "glucose",
]


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def read_csv(path):
    text = Path(path).read_text(encoding="utf-8-sig", newline="")
    first = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return list(csv.reader(text.splitlines(), delimiter=delimiter)), delimiter


def description_evidence(path, headers):
    """Associate a header with all description-row text naming that header."""
    if not path or not Path(path).exists():
        return {header: norm(header) for header in headers}
    rows, _ = read_csv(path)
    evidence = {header: norm(header) for header in headers}
    header_norm = {norm(header): header for header in headers}
    for row in rows:
        combined = norm(" ".join(row))
        for cell in row:
            name = norm(cell)
            if name in header_norm:
                evidence[header_norm[name]] += " " + combined
    return evidence


def resolve(text):
    """Resolve a column description without transferring factors between analytes."""
    # This guard remains valid even if a description of HbA1c also discusses
    # diabetes or glucose; glucose conversion cannot apply to HbA1c.
    if any(alias in text for alias in REGISTRY["a1c"][0]):
        return "a1c"
    ordered = PRIORITY + [key for key in REGISTRY if key not in PRIORITY]
    for key in ordered:
        if key == "a1c":
            continue
        aliases = REGISTRY[key][0]
        if not any(alias in text for alias in aliases):
            continue
        if key == "albumin_serum" and ("urine albumin" in text or "urinary albumin" in text or "ratio" in text):
            continue
        if key == "urea" and ("nitrogen" in text or "bun" in text):
            continue
        return key
    return None


def parse_number(value):
    raw = str(value).strip()
    if raw.lower() in MISSING:
        raise ValueError("missing")
    # A comma is a decimal separator only when it is the single numeric decimal
    # separator, never when it resembles a thousands grouping.
    comma_decimal = re.fullmatch(r"[+-]?(?:\d+,\d*|\d*,\d+)(?:[eE][+-]?\d+)?", raw)
    if comma_decimal:
        raw = raw.replace(",", ".")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", raw):
        raise ValueError("not a strict numeric token")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not number.is_finite():
        raise ValueError("nonfinite")
    return number


def inside(value, bounds):
    return bounds[0] <= value <= bounds[1]


def convert(value, key):
    """Return output value and provenance action for one resolved analyte."""
    _, bounds, candidates = REGISTRY[key]
    identity_ok = inside(value, bounds)
    fits = [(label, value * factor) for label, factor in candidates if inside(value * factor, bounds)]
    if identity_ok:
        return value, "identity" if not fits else "ambiguous_identity_retained"
    if len(fits) == 1:
        return fits[0][1], "converted:" + fits[0][0]
    if len(fits) > 1:
        return value, "ambiguous_unconverted"
    return value, "outside_no_admissible_conversion"


def fixed2(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def main(cfg):
    input_path = cfg.get("input_path")
    if not input_path:
        raise ValueError("input_path is required")
    output_path = cfg.get("output_path", "/root/ckd_lab_data_harmonized.csv")
    strict = bool(cfg.get("strict", False))
    table, delimiter = read_csv(input_path)
    if not table:
        raise ValueError("input CSV is empty")
    headers = table[0]
    if not headers or len(set(headers)) != len(headers):
        raise ValueError("input header is missing or has duplicate column names")

    evidence = description_evidence(cfg.get("descriptions_path"), headers)
    resolved = {header: resolve(evidence[header]) for header in headers}
    output_rows = []
    bad_rows = Counter()
    actions = Counter()
    outside = Counter()
    ambiguity = Counter()
    malformed_width = 0

    for row_number, row in enumerate(table[1:], start=2):
        if len(row) != len(headers):
            malformed_width += 1
            bad_rows["wrong_column_count"] += 1
            continue
        try:
            values = [parse_number(cell) for cell in row]
        except ValueError as exc:
            bad_rows[str(exc)] += 1
            continue

        newrow = []
        for header, value in zip(headers, values):
            key = resolved[header]
            if key:
                value, action = convert(value, key)
                actions[key + ":" + action] += 1
                if action.startswith("ambiguous"):
                    ambiguity[header] += 1
                if not inside(value, REGISTRY[key][1]):
                    outside[header] += 1
            newrow.append(fixed2(value))
        output_rows.append(newrow)

    if strict and outside:
        raise ValueError("strict validation failed; known analytes outside validation interval: " + ", ".join(sorted(outside)))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(output_rows)

    return {
        "output_path": str(out),
        "input_columns": len(headers),
        "output_columns": len(headers),
        "input_data_rows": max(0, len(table) - 1),
        "output_data_rows": len(output_rows),
        "dropped_rows": sum(bad_rows.values()),
        "dropped_row_reasons": dict(bad_rows),
        "malformed_width_rows": malformed_width,
        "resolved_columns": {header: key for header, key in resolved.items() if key},
        "unresolved_columns": [header for header, key in resolved.items() if not key],
        "conversion_counts": dict(actions),
        "ambiguous_cells": dict(ambiguity),
        "outside_validation_after": dict(outside),
        "delimiter": delimiter,
        "all_retained_cells_fixed_two_decimals": True,
    }


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(config), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stdout)
        sys.exit(2)
