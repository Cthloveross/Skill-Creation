#!/usr/bin/env python3
"""Inventory JSON export structures. stdin: {root, max_files?, max_paths?, max_examples?}."""
import json, os, sys
from pathlib import Path
from collections import Counter


def scalar_type(value):
    if value is None: return "null"
    if isinstance(value, bool): return "bool"
    if isinstance(value, (int, float)): return "number"
    if isinstance(value, str): return "string"
    if isinstance(value, list): return "array"
    if isinstance(value, dict): return "object"
    return type(value).__name__


def inspect(value, paths, examples, path="$", depth=0, limit=250):
    if len(paths) >= limit or depth > 10:
        return
    kind = scalar_type(value)
    paths[path + "::" + kind] += 1
    if isinstance(value, dict):
        for key, child in value.items():
            inspect(child, paths, examples, path + "." + str(key), depth + 1, limit)
    elif isinstance(value, list):
        for child in value[:3]:
            inspect(child, paths, examples, path + "[]", depth + 1, limit)
    elif len(examples) < 12:
        text = str(value).replace("\n", " ")
        examples.append({"path": path, "type": kind, "value": text[:180]})


def main():
    req = json.load(sys.stdin)
    root = Path(req.get("root", "/root/DATA"))
    max_files = int(req.get("max_files", 200))
    max_paths = int(req.get("max_paths", 100))
    out, errors = [], []
    if not root.is_dir():
        print(json.dumps({"root": str(root), "files": [], "errors": ["root is not a directory"]}))
        return
    files = sorted(root.rglob("*.json"))[:max_files]
    for fp in files:
        entry = {"file": str(fp.relative_to(root)), "bytes": fp.stat().st_size}
        try:
            with fp.open("r", encoding="utf-8") as f:
                data = json.load(f)
            entry["root_type"] = scalar_type(data)
            if isinstance(data, dict): entry["root_keys"] = list(data.keys())[:40]
            elif isinstance(data, list): entry["root_length"] = len(data)
            paths, examples = Counter(), []
            inspect(data, paths, examples, limit=max_paths * 3)
            entry["observed_paths"] = [{"path": p.rsplit("::", 1)[0], "type": p.rsplit("::", 1)[1], "observations": n}
                                       for p, n in paths.most_common(max_paths)]
            entry["examples"] = examples[:int(req.get("max_examples", 6))]
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            errors.append({"file": entry["file"], "error": entry["error"]})
        out.append(entry)
    print(json.dumps({"root": str(root), "files": out, "errors": errors}, ensure_ascii=False))

if __name__ == "__main__":
    main()
