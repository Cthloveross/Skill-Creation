#!/usr/bin/env python3
"""Summarize JSON files without assuming a corpus schema.
Input: {"data_root": str, "max_paths_per_file": int=80, "max_depth": int=5}
Output: {"files": [...], "errors": [...]}.
"""
import json
import sys
from pathlib import Path
from collections import Counter


def type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def path_text(parts):
    if not parts:
        return "$"
    out = "$"
    for part in parts:
        out += "[]" if part == "[]" else "." + str(part)
    return out


def describe(value, parts, depth, max_depth, rows, limit):
    if len(rows) >= limit:
        return
    row = {"path": path_text(parts), "type": type_name(value)}
    if isinstance(value, dict):
        row["keys"] = list(value.keys())[:30]
    elif isinstance(value, list):
        row["length"] = len(value)
    elif isinstance(value, str):
        row["sample"] = value[:160]
    else:
        row["sample"] = value
    rows.append(row)
    if depth >= max_depth:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            describe(child, parts + [key], depth + 1, max_depth, rows, limit)
            if len(rows) >= limit:
                return
    elif isinstance(value, list):
        # Sampling an item reveals array member schema without assuming an index is stable.
        for child in value[:2]:
            describe(child, parts + ["[]"], depth + 1, max_depth, rows, limit)
            if len(rows) >= limit:
                return


def main():
    request = json.load(sys.stdin)
    root = Path(request["data_root"])
    limit = int(request.get("max_paths_per_file", 80))
    max_depth = int(request.get("max_depth", 5))
    if not root.is_dir():
        raise ValueError("data_root must be an existing directory")
    files, errors = [], []
    for file_path in sorted(root.rglob("*.json")):
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            rows = []
            describe(value, [], 0, max_depth, rows, limit)
            top = list(value.keys())[:50] if isinstance(value, dict) else None
            files.append({
                "file": str(file_path),
                "root_type": type_name(value),
                "top_level_keys": top,
                "schema_samples": rows,
            })
        except Exception as exc:
            errors.append({"file": str(file_path), "error": str(exc)})
    print(json.dumps({"files": files, "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
