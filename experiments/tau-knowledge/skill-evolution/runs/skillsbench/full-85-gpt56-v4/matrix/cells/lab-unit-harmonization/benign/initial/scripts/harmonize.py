#!/usr/bin/env python3
"""CSV clinical-lab harmonizer. Reads one JSON object from stdin and prints JSON."""
import csv
import json
import math
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MISSING = {"", "na", "n/a", "null", "none", "."}
NUMBER = re.compile(r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$")

# Each entry is (aliases, broad US-conventional plausibility range, alternate-to-US factors).
# Factors are only considered after identity is outside the stated range.
REGISTRY = {
 "creatinine": (["creatinine", "serum creat", "scr"], ("0.05", "30"), ["0.0113122171946"]),
 "bun": (["blood urea nitrogen", "bun", "urea nitrogen"], ("1", "250"), ["2.801"]),
 "urea": (["serum urea", "urea"], ("2", "500"), ["6.006"]),
 "glucose": (["glucose", "blood sugar"], ("15", "1200"), ["18.0182"]),
 "hba1c": (["hemoglobin a1c", "glycated hemoglobin", "hba1c", "hb a1c"], ("3", "20"), ["1"]),
 "calcium": (["ionized calcium"], ("2", "8"), ["4.008"]),
 "calcium_total": (["total calcium", "serum calcium", "calcium"], ("4", "16"), ["4.008"]),
 "phosphorus": (["phosphorus", "phosphate"], ("0.3", "25"), ["3.097"]),
 "magnesium": (["magnesium"], ("0.3", "10"), ["2.43"]),
 "sodium": (["sodium", "na+"], ("100", "200"), ["1"]),
 "potassium": (["potassium", "k+"], ("1", "12"), ["1"]),
 "chloride": (["chloride", "cl-"], ("60", "150"), ["1"]),
 "bicarbonate": (["bicarbonate", "total co2", "carbon dioxide", "co2"], ("3", "50"), ["1"]),
 "albumin": (["serum albumin", "albumin"], ("0.5", "7"), ["0.1"]),
 "total_protein": (["total protein", "serum protein"], ("2", "12"), ["0.1"]),
 "hemoglobin": (["hemoglobin", "haemoglobin", "hgb", "hb"], ("2", "26"), ["0.1"]),
 "hematocrit": (["hematocrit", "haematocrit", "hct", "pcv"], ("8", "80"), ["100"]),
 "rbc": (["red blood cell", "erythrocyte", "rbc"], ("0.5", "10"), ["1"]),
 "wbc": (["white blood cell", "leukocyte", "wbc"], ("0.1", "200"), ["1"]),
 "platelets": (["platelet", "thrombocyte", "plt"], ("5", "2500"), ["1"]),
 "bilirubin_direct": (["direct bilirubin", "conjugated bilirubin"], ("0", "30"), ["0.058465856"]),
 "bilirubin_total": (["total bilirubin", "bilirubin"], ("0", "60"), ["0.058465856"]),
 "cholesterol": (["total cholesterol", "cholesterol"], ("40", "800"), ["38.67"]),
 "hdl": (["hdl cholesterol", "high density lipoprotein", "hdl"], ("5", "200"), ["38.67"]),
 "ldl": (["ldl cholesterol", "low density lipoprotein", "ldl"], ("5", "600"), ["38.67"]),
 "triglycerides": (["triglyceride", "trig"], ("10", "3000"), ["88.57"]),
 "uric_acid": (["uric acid", "urate"], ("0.5", "35"), ["0.016812374"]),
 "iron": (["serum iron", "iron"], ("5", "500"), ["5.585"]),
 "tibc": (["total iron binding capacity", "tibc"], ("50", "800"), ["5.585"]),
 "crp": (["c-reactive protein", "c reactive protein", "crp"], ("0", "100"), ["0.1"]),
 "ferritin": (["ferritin"], ("1", "10000"), ["1"]),
 "pth": (["parathyroid hormone", "pth"], ("1", "5000"), ["9.43"]),
 "vitamin_d": (["vitamin d", "25-oh d", "25 hydroxy"], ("1", "250"), ["0.400640"]),
 "tsh": (["thyroid stimulating hormone", "tsh"], ("0.001", "200"), ["1"]),
 "free_t4": (["free thyroxine", "free t4", "ft4"], ("0.1", "10"), ["0.0777"]),
 "alt": (["alanine aminotransferase", "alanine transaminase", "alt", "sgpt"], ("0", "5000"), ["1"]),
 "ast": (["aspartate aminotransferase", "aspartate transaminase", "ast", "sgot"], ("0", "5000"), ["1"]),
 "alp": (["alkaline phosphatase", "alp"], ("5", "5000"), ["1"]),
 "ldh": (["lactate dehydrogenase", "ldh"], ("10", "10000"), ["1"]),
 "egfr": (["estimated glomerular filtration", "egfr", "gfr"], ("1", "250"), ["1"]),
}

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()

def phrase_in(phrase, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(norm(phrase)) + r"(?![a-z0-9])", text) is not None

def parse_number(value):
    s = str(value).strip()
    if s.lower() in MISSING:
        return None
    if not NUMBER.fullmatch(s):
        raise ValueError("not a strict decimal number: %r" % value)
    try:
        d = Decimal(s.replace(",", "."))
    except InvalidOperation as e:
        raise ValueError("invalid decimal: %r" % value) from e
    if not d.is_finite():
        raise ValueError("non-finite value: %r" % value)
    return d

def fixed(d):
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if q == 0:
        q = abs(q)
    return format(q, ".2f")

def description_texts(path):
    if not path:
        return {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = {}
    for row in rows:
        vals = [str(v or "") for v in row.values()]
        if not vals:
            continue
        text = " ".join(vals)
        # Any short value can be the feature code; retaining all variants is robust to heading changes.
        for v in vals:
            key = norm(v)
            if key and len(key) <= 80:
                result[key] = text
    return result

def resolve(column, desc):
    text = norm(str(column) + " " + desc.get(norm(column), ""))
    # Urine measurements and ratios need specimen-specific definitions not assumed here.
    if "urine" in text or "urinary" in text or "ratio" in text:
        return None
    matches = []
    for name, (aliases, bounds, factors) in REGISTRY.items():
        for alias in aliases:
            if phrase_in(alias, text):
                matches.append((len(norm(alias)), name, bounds, factors))
    if not matches:
        return None
    matches.sort(reverse=True)
    _, name, bounds, factors = matches[0]
    return name, Decimal(bounds[0]), Decimal(bounds[1]), [Decimal(x) for x in factors]

def in_range(v, lo, hi):
    return lo <= v <= hi

def convert(v, spec):
    """Return (converted_decimal, status); status is identity, converted, unresolved, ambiguous."""
    if spec is None:
        return v, "unmapped"
    _, lo, hi, factors = spec
    if in_range(v, lo, hi):
        return v, "identity"
    candidates = []
    for factor in factors:
        candidate = v * factor
        if in_range(candidate, lo, hi):
            candidates.append(candidate)
    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return unique[0], "converted"
    return v, "ambiguous" if len(unique) > 1 else "unresolved"

def main(cfg):
    source = cfg["input_path"]
    target = cfg["output_path"]
    strict = bool(cfg.get("strict_ranges", True))
    desc = description_texts(cfg.get("descriptions_path"))
    with open(source, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("input CSV is empty")
        if not header or len(set(header)) != len(header):
            raise ValueError("input must have a nonempty, unique header")
        raw_rows = list(reader)
    for n, row in enumerate(raw_rows, start=2):
        if len(row) != len(header):
            raise ValueError("row %d has %d fields; expected %d (decimal commas must be CSV-quoted)" % (n, len(row), len(header)))
    specs = [resolve(h, desc) for h in header]
    kept, dropped, converted_count, unresolved = [], 0, 0, []
    for row_number, row in enumerate(raw_rows, start=2):
        if any(str(x).strip().lower() in MISSING for x in row):
            dropped += 1
            continue
        parsed = []
        for col, value, spec in zip(header, row, specs):
            try:
                parsed.append(parse_number(value))
            except ValueError:
                # Text metadata is retained only when it is not a known lab measurement.
                if spec is not None:
                    raise ValueError("row %d, column %s: invalid laboratory value %r" % (row_number, col, value))
                parsed.append(None)
        out = []
        for col, original, value, spec in zip(header, row, parsed, specs):
            if value is None:
                out.append(original)
                continue
            new_value, status = convert(value, spec)
            if status == "converted":
                converted_count += 1
            if status in ("unresolved", "ambiguous"):
                unresolved.append({"row": row_number, "column": col, "reason": status, "value": str(value)})
            out.append(fixed(new_value))
        kept.append(out)
    if strict and unresolved:
        sample = "; ".join("row %(row)s %(column)s (%(reason)s)" % x for x in unresolved[:8])
        raise ValueError("recognized values could not be safely harmonized: " + sample)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(kept)
    # Structural and rendering validation of the artifact just written.
    with open(target, newline="", encoding="utf-8") as f:
        check = list(csv.reader(f))
    if not check or check[0] != header or any(len(r) != len(header) for r in check[1:]):
        raise RuntimeError("output structural validation failed")
    for r in check[1:]:
        for cell in r:
            if NUMBER.fullmatch(cell):
                if not re.fullmatch(r"-?\d+\.\d{2}", cell):
                    raise RuntimeError("numeric rendering validation failed: " + cell)
    return {"input_rows": len(raw_rows), "written_rows": len(kept), "dropped_missing_rows": dropped,
            "converted_cells": converted_count, "recognized_columns": sum(x is not None for x in specs),
            "unresolved": unresolved, "output_path": target}

if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin must contain a JSON object")
        print(json.dumps(main(config), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(2)
