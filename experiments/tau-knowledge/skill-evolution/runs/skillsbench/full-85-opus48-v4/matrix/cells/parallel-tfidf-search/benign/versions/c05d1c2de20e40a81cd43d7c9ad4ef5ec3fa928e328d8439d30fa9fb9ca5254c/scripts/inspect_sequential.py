#!/usr/bin/env python3
"""Print the sequential engine's public API so assumptions can be verified.

stdin  (optional): {"workspace": "/root/workspace"}
stdout: {"ok": bool, "sequential": {...}, "document_generator": {...}, "error"?}
"""
import importlib
import inspect
import json
import sys
from dataclasses import fields, is_dataclass


def describe_module(mod):
    out = {}
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if inspect.isclass(obj) and getattr(obj, "__module__", None) == mod.__name__:
            info = {"kind": "class"}
            if is_dataclass(obj):
                info["dataclass_fields"] = [f.name for f in fields(obj)]
            out[name] = info
        elif inspect.isfunction(obj) and getattr(obj, "__module__", None) == mod.__name__:
            try:
                sig = str(inspect.signature(obj))
            except (TypeError, ValueError):
                sig = "(?)"
            out[name] = {"kind": "function", "signature": sig}
    return out


def main():
    try:
        raw = sys.stdin.read().strip()
        req = json.loads(raw) if raw else {}
    except Exception:
        req = {}
    workspace = req.get("workspace", "/root/workspace")
    if workspace not in sys.path:
        sys.path.insert(0, workspace)
    result = {"ok": True}
    try:
        seq = importlib.import_module("sequential")
        result["sequential"] = describe_module(seq)
    except Exception as e:  # pragma: no cover
        result["ok"] = False
        result["error"] = "sequential: %s" % e
    try:
        gen = importlib.import_module("document_generator")
        result["document_generator"] = describe_module(gen)
    except Exception as e:
        result.setdefault("notes", []).append("document_generator: %s" % e)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
