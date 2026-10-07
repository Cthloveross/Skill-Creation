#!/usr/bin/env python3
"""Regex search over string values in JSON files, returning provenance.

stdin: {
  "paths": [str,...]  OR  "dir": str,
  "patterns": [str,...],
  "ignore_case": true,
  "require_all": false,
  "max_matches": 100,
  "record_depth": 1   # how many levels up from the match to return as record
}
stdout: {"count": int, "files_scanned": int, "matches": [
  {"file":str, "pointer":str, "value":str, "record": any}]}

A record matches when ANY pattern matches some string value within it
(require_all=true requires every pattern to match somewhere in the file-walk
of that match's enclosing record is not enforced; patterns apply per string).
"""
import json, os, re, sys


def iter_files(req):
    paths = []
    if "dir" in req:
        paths.append(req["dir"])
    paths.extend(req.get("paths", []))
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, _d, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(".json"):
                        yield os.path.join(root, f)


def walk(obj, ancestors):
    """Yield (pointer, value, ancestors) for every string leaf.
    ancestors is a list of (container, pointer) from root to the leaf's parent.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            ptr = ancestors[-1][1] + "/" + str(k) if ancestors else "/" + str(k)
            if isinstance(v, (dict, list)):
                yield from walk(v, ancestors + [(v, ptr)])
            elif isinstance(v, str):
                yield ptr, v, ancestors + [(v, ptr)]
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            ptr = ancestors[-1][1] + "/" + str(i) if ancestors else "/" + str(i)
            if isinstance(v, (dict, list)):
                yield from walk(v, ancestors + [(v, ptr)])
            elif isinstance(v, str):
                yield ptr, v, ancestors + [(v, ptr)]


def trim_record(rec, limit=4000):
    s = json.dumps(rec, ensure_ascii=False)
    if len(s) <= limit:
        return rec
    return {"_truncated": s[:limit] + "..."}


def main():
    req = json.load(sys.stdin)
    flags = re.IGNORECASE if req.get("ignore_case", True) else 0
    pats = [re.compile(p, flags) for p in req.get("patterns", [])]
    require_all = req.get("require_all", False)
    max_matches = int(req.get("max_matches", 100))
    record_depth = int(req.get("record_depth", 1))
    matches = []
    scanned = 0
    for fp in iter_files(req):
        scanned += 1
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        for ptr, val, anc in walk(data, []):
            hits = [bool(p.search(val)) for p in pats]
            ok = all(hits) if require_all else any(hits)
            if not ok:
                continue
            # choose enclosing record: go up record_depth dict/list levels
            rec = anc[-1][0]
            idx = len(anc) - 1
            levels = 0
            while idx > 0 and levels < record_depth:
                idx -= 1
                cand = anc[idx][0]
                if isinstance(cand, (dict, list)):
                    rec = cand
                    levels += 1
            matches.append({
                "file": fp,
                "pointer": ptr,
                "value": val if len(val) <= 300 else val[:300] + "...",
                "record": trim_record(rec),
            })
            if len(matches) >= max_matches:
                print(json.dumps({"count": len(matches),
                                  "files_scanned": scanned,
                                  "truncated": True,
                                  "matches": matches}, ensure_ascii=False))
                return
    print(json.dumps({"count": len(matches), "files_scanned": scanned,
                      "truncated": False, "matches": matches},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
