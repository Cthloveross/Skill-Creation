#!/usr/bin/env python3
"""Validate taxonomy CSV consistency. JSON stdin -> JSON report on stdout."""
import csv
import json
import os
import re
import sys
from collections import defaultdict

LEVELS = [f"unified_level_{i}" for i in range(1, 6)]
FULL = ["source", "category_path", "depth"] + LEVELS
ALLOWED_SOURCES = {"amazon", "facebook", "google"}


def read(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def check_label(value):
    if not value:
        return None
    words = [x.strip() for x in value.split("|")]
    if any(not x for x in words) or len(words) > 5:
        return "must contain one to five nonempty pipe-separated words"
    if not re.fullmatch(r"[A-Za-z0-9]+(?: \| [A-Za-z0-9]+){0,4}", value):
        return "contains non-normalized characters or separator spacing"
    return None


def validate(full_path, hierarchy_path):
    errors, warnings = [], []
    if not os.path.isfile(full_path) or not os.path.isfile(hierarchy_path):
        return {"valid": False, "errors": ["full_csv or hierarchy_csv does not exist"], "warnings": []}
    full, hierarchy = read(full_path), read(hierarchy_path)
    if not full:
        errors.append("full mapping has no data rows")
    with open(full_path, encoding="utf-8-sig", newline="") as fh:
        full_headers = csv.DictReader(fh).fieldnames or []
    with open(hierarchy_path, encoding="utf-8-sig", newline="") as fh:
        hierarchy_headers = csv.DictReader(fh).fieldnames or []
    missing_full = [x for x in FULL if x not in full_headers]
    if missing_full:
        errors.append("full mapping missing columns: " + ", ".join(missing_full))
    if hierarchy_headers != LEVELS:
        errors.append("hierarchy columns must be exactly: " + ", ".join(LEVELS))

    projection = set()
    children = defaultdict(set)
    for n, row in enumerate(full, 2):
        if row.get("source") not in ALLOWED_SOURCES:
            errors.append(f"row {n}: invalid source")
        values = tuple((row.get(c) or "").strip() for c in LEVELS)
        projection.add(values)
        try:
            depth = int(row.get("depth", ""))
        except ValueError:
            depth = 0
        actual = sum(bool(x) for x in values)
        if depth != actual or not 1 <= depth <= 5:
            errors.append(f"row {n}: depth must equal contiguous populated unified levels")
        blank_seen = False
        for value in values:
            if not value:
                blank_seen = True
            elif blank_seen:
                errors.append(f"row {n}: a populated level follows a blank level")
                break
            problem = check_label(value)
            if problem:
                errors.append(f"row {n}: label '{value}' {problem}")
        for i in range(1, 5):
            if values[i]:
                children[values[:i]].add(values[i])

    hierarchy_keys = [tuple((row.get(c) or "").strip() for c in LEVELS) for row in hierarchy]
    hierarchy_set = set(hierarchy_keys)
    if len(hierarchy_set) != len(hierarchy_keys):
        errors.append("hierarchy contains duplicate unified paths")
    if hierarchy_set != projection:
        errors.append("hierarchy is not the exact deduplicated five-level projection of full mapping")
    roots = {key[0] for key in projection if key[0]}
    if not 10 <= len(roots) <= 20:
        warnings.append(f"root count is {len(roots)}, outside requested 10-20 range")
    sparse = [(parent, len(kids)) for parent, kids in children.items() if len(kids) < 3]
    wide = [(parent, len(kids)) for parent, kids in children.items() if len(kids) > 20]
    if sparse:
        warnings.append(f"{len(sparse)} non-leaf parents have fewer than 3 observed children")
    if wide:
        errors.append(f"{len(wide)} parents have more than 20 children")
    return {
        "valid": not errors,
        "errors": errors[:100],
        "warnings": warnings,
        "full_rows": len(full),
        "hierarchy_rows": len(hierarchy),
        "root_count": len(roots),
        "nonleaf_parent_count": len(children),
    }


def main():
    try:
        request = json.load(sys.stdin)
        result = validate(request["full_csv"], request["hierarchy_csv"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
    except KeyError:
        print(json.dumps({"valid": False, "errors": ["stdin requires full_csv and hierarchy_csv"], "warnings": []}))
        raise SystemExit(1)

if __name__ == "__main__":
    main()
