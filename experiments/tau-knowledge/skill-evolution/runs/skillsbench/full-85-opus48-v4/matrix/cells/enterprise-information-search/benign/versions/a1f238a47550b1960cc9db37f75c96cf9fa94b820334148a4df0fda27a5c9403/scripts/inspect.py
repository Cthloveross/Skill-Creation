#!/usr/bin/env python3
"""Summarize JSON structure of a file or directory tree.

stdin: {"path": str, "sample": int=2, "max_depth": int=3}
stdout: {"root": str, "items": [{"file": str, "bytes": int, "summary": {...}}]}
"""
import json, os, sys


def type_tag(v):
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list[%d]" % len(v)
    if isinstance(v, dict):
        return "dict{%d}" % len(v)
    if v is None:
        return "null"
    return type(v).__name__


def trim(v, n=120):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "..."


def summarize(obj, sample, max_depth, depth=0):
    if depth >= max_depth:
        return {"type": type_tag(obj)}
    if isinstance(obj, dict):
        out = {"type": "dict", "keys": {}}
        for k, v in obj.items():
            out["keys"][k] = type_tag(v)
        # recurse into first value for shape hints
        sub = {}
        for k, v in list(obj.items())[:sample]:
            if isinstance(v, (dict, list)):
                sub[k] = summarize(v, sample, max_depth, depth + 1)
        if sub:
            out["children"] = sub
        return out
    if isinstance(obj, list):
        out = {"type": "list", "len": len(obj)}
        if obj:
            out["item0"] = summarize(obj[0], sample, max_depth, depth + 1)
            out["samples"] = [trim(x) for x in obj[:sample]]
        return out
    return {"type": type_tag(obj), "value": trim(obj)}


def iter_files(path):
    if os.path.isfile(path):
        yield path
        return
    for root, _dirs, files in os.walk(path):
        for f in sorted(files):
            if f.lower().endswith(".json"):
                yield os.path.join(root, f)


def main():
    req = json.load(sys.stdin)
    path = req["path"]
    sample = int(req.get("sample", 2))
    max_depth = int(req.get("max_depth", 3))
    items = []
    for fp in iter_files(path):
        entry = {"file": fp, "bytes": os.path.getsize(fp)}
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            entry["summary"] = summarize(data, sample, max_depth)
        except Exception as e:  # noqa
            entry["error"] = str(e)
        items.append(entry)
    print(json.dumps({"root": path, "items": items}, ensure_ascii=False))


if __name__ == "__main__":
    main()
