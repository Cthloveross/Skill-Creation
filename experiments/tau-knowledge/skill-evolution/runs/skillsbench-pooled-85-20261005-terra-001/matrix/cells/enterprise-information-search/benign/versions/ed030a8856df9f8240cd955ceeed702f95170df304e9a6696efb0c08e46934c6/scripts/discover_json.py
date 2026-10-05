#!/usr/bin/env python3
"""stdin: {root, max_files?, max_paths?}; stdout: JSON schema inventory."""
import json, sys
from collections import Counter
from pathlib import Path

def kind(v):
    if v is None: return "null"
    if isinstance(v, bool): return "bool"
    if isinstance(v, (int, float)): return "number"
    if isinstance(v, str): return "string"
    if isinstance(v, list): return "array"
    if isinstance(v, dict): return "object"
    return type(v).__name__

def scan(v, paths, examples, path="$", depth=0, limit=300):
    if depth > 12 or len(paths) >= limit: return
    paths[path + "::" + kind(v)] += 1
    if isinstance(v, dict):
        for k, x in v.items(): scan(x, paths, examples, path + "." + str(k), depth + 1, limit)
    elif isinstance(v, list):
        for x in v[:3]: scan(x, paths, examples, path + "[]", depth + 1, limit)
    elif len(examples) < 8:
        examples.append({"path": path, "type": kind(v), "value": str(v).replace("\n", " ")[:180]})

def main():
    req = json.load(sys.stdin); root = Path(req.get("root", "/root/DATA"))
    out, errors = [], []
    if not root.is_dir():
        print(json.dumps({"root": str(root), "files": [], "errors": ["root is not a directory"]})); return
    for fp in sorted(root.rglob("*.json"))[:int(req.get("max_files", 200))]:
        row = {"file": str(fp.relative_to(root)), "bytes": fp.stat().st_size}
        try:
            data = json.loads(fp.read_text(encoding="utf-8")); row["root_type"] = kind(data)
            if isinstance(data, dict): row["root_keys"] = list(data)[:40]
            if isinstance(data, list): row["root_length"] = len(data)
            paths, examples = Counter(), []; scan(data, paths, examples)
            row["observed_paths"] = [{"path": p.rsplit("::",1)[0], "type": p.rsplit("::",1)[1], "observations": n} for p,n in paths.most_common(int(req.get("max_paths",100)))]
            row["examples"] = examples
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"; errors.append({"file": row["file"], "error": row["error"]})
        out.append(row)
    print(json.dumps({"root": str(root), "files": out, "errors": errors}, ensure_ascii=False))
if __name__ == "__main__": main()
