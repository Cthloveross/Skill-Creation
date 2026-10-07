#!/usr/bin/env python3
"""Validate taxonomy artifacts. JSON stdin -> JSON stdout."""
import csv
import json
import os
import re
import sys
from collections import defaultdict

LEVELS = [f"unified_level_{i}" for i in range(1, 6)]
FULL_COLUMNS = ["source", "category_path", "depth", *LEVELS]
DEFAULT_FILES = {
    "amazon": "amazon_product_categories.csv",
    "facebook": "fb_product_categories.csv",
    "google": "google_shopping_product_categories.csv",
}
LABEL_RE = re.compile(r"^[A-Za-z0-9]+(?: \| [A-Za-z0-9]+){0,4}$")
FORBIDDEN = {"none", "null", "nan", "other", "misc", "unknown", "cluster"}


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def path_key(value):
    return tuple(piece.strip().casefold() for piece in str(value).split(">")["__len__"]() if piece.strip())


def word_set(label):
    result = set()
    for word in label.casefold().split(" | "):
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        result.add(word)
    return result


def source_paths(data_dir, files):
    expected = set()
    for source, default in DEFAULT_FILES.items():
        filename = files.get(source, default)
        path = filename if os.path.isabs(filename) else os.path.join(data_dir, filename)
        headers, rows = read_csv(path)
        if "category_path" not in headers:
            raise ValueError(f"{path} lacks required category_path column")
        for row in rows:
            key = path_key(row.get("category_path", ""))
            if key:
                expected.add((source, key))
    return expected


def validate(request):
    full_path = request.get("full_csv")
    hierarchy_path = request.get("hierarchy_csv")
    errors = []
    if not full_path or not hierarchy_path or not os.path.isfile(full_path) or not os.path.isfile(hierarchy_path):
        return {"valid": False, "errors": ["full_csv and hierarchy_csv must exist"], "warnings": []}
    full_headers, full_rows = read_csv(full_path)
    hierarchy_headers, hierarchy_rows = read_csv(hierarchy_path)
    if full_headers != FULL_COLUMNS:
        errors.append("full mapping headers do not exactly match required columns")
    if hierarchy_headers != LEVELS:
        errors.append("hierarchy headers do not exactly match required unified levels")

    projection = set()
    observed = []
    children = defaultdict(set)
    for index, row in enumerate(full_rows, 2):
        source = (row.get("source") or "").strip().casefold()
        key = path_key(row.get("category_path", ""))
        if source not in DEFAULT_FILES:
            errors.append(f"row {index}: invalid source")
        if not key:
            errors.append(f"row {index}: empty category_path")
        observed.append((source, key))
        values = tuple((row.get(level) or "").strip() for level in LEVELS)
        projection.add(values)
        try:
            depth = int((row.get("depth") or "").strip())
        except ValueError:
            depth = 0
        if depth != sum(bool(value) for value in values) or not 1 <= depth <= 5:
            errors.append(f"row {index}: invalid depth or nonmatching populated levels")
        blank = False
        for value in values:
            if not value:
                blank = True
                continue
            if blank:
                errors.append(f"row {index}: noncontiguous unified levels")
            if not LABEL_RE.fullmatch(value) or value.casefold() in FORBIDDEN or value.casefold().startswith("cluster "):
                errors.append(f"row {index}: invalid label {value!r}")
        for level in range(1, 5):
            if values[level]:
                children[values[:level]].add(values[level])

    if len(observed) != len(set(observed)):
        errors.append("full mapping repeats source/category_path assignments")
    hierarchy_keys = [tuple((row.get(level) or "").strip() for level in LEVELS) for row in hierarchy_rows]
    if len(hierarchy_keys) != len(set(hierarchy_keys)):
        errors.append("hierarchy has duplicate paths")
    if set(hierarchy_keys) != projection:
        errors.append("hierarchy is not the exact deduplicated full-mapping projection")

    roots = {path[0] for path in projection if path[0]}
    if not 10 <= len(roots) <= 20:
        errors.append(f"root count {len(roots)} is outside 10-20")
    for parent, kids in children.items():
        if not 3 <= len(kids) <= 20:
            errors.append(f"parent {parent!r} has {len(kids)} children instead of 3-20")
        parent_words = word_set(parent[-1])
        ordered = sorted(kids)
        for child in ordered:
            if parent_words & word_set(child):
                errors.append(f"parent/child word overlap: {parent[-1]!r} -> {child!r}")
        for offset, left in enumerate(ordered):
            left_words = word_set(left)
            for right in ordered[offset + 1:]:
                right_words = word_set(right)
                if len(left_words & right_words) / len(left_words | right_words) >= 0.30:
                    errors.append(f"sibling word overlap: {left!r} / {right!r}")

    if request.get("data_dir"):
        try:
            expected = source_paths(request["data_dir"], request.get("files", {}))
            observed_set = set(observed)
            if expected - observed_set:
                errors.append(f"full mapping misses {len(expected - observed_set)} input source paths")
            if observed_set - expected:
                errors.append(f"full mapping contains {len(observed_set - expected)} unexpected source paths")
        except Exception as exc:
            errors.append(f"cannot validate input coverage: {exc}")
    return {
        "valid": not errors,
        "errors": errors[:100],
        "warnings": [],
        "full_rows": len(full_rows),
        "hierarchy_rows": len(hierarchy_rows),
        "root_count": len(roots),
        "nonleaf_parent_count": len(children),
    }


def main():
    try:
        request = json.load(sys.stdin)
        result = validate(request)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)], "warnings": []}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
