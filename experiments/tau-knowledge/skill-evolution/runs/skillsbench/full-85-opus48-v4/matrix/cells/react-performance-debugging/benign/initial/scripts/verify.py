#!/usr/bin/env python3
"""Verify that performance edits preserved required constraints and that
optimization patterns are present.

Input  (stdin JSON): {"app_root": "/app"}
Output (stdout JSON): {
    "ok": bool,
    "checks": [ {"name": str, "ok": bool, "detail": str} ],
    "notes": [str]
}

Constraint checks (must stay true):
  * every data-testid literal found in the tree is still present
    (compared against a baseline recorded on first run, if available)
  * performance.mark remains in any product-card component

Optimization signals (informational, not pass/fail by themselves):
  * Promise.all present in a route handler / async server page
  * React.memo / useCallback / useMemo present in client components
  * dynamic()/lazy()/import() present where a heavy import was flagged

The script never edits files. Combine its result with a real `npm run build`
and, where possible, end-to-end route timing.
"""
import json
import os
import re
import sys

TEXT_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs")
TESTID = re.compile(r"data-testid\s*=\s*[\"']([^\"']+)[\"']")


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def iter_source_files(root):
    src = os.path.join(root, "src")
    base = src if os.path.isdir(src) else root
    for dp, dn, fn in os.walk(base):
        if "node_modules" in dp or "/.next" in dp:
            continue
        for name in fn:
            if name.endswith(TEXT_EXT):
                yield os.path.join(dp, name)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    root = payload.get("app_root") or os.getcwd()

    checks = []
    notes = []
    all_text = {}
    testids = set()
    product_card_marks = []

    for path in iter_source_files(root):
        text = read(path)
        all_text[path] = text
        for m in TESTID.finditer(text):
            testids.add(m.group(1))
        if re.search(r"ProductCard", os.path.basename(path)):
            product_card_marks.append(
                (path, bool(re.search(r"performance\.mark\s*\(", text))))

    # Baseline comparison for data-testid preservation.
    baseline_path = os.path.join(root, ".skill_testid_baseline.json")
    if os.path.exists(baseline_path):
        try:
            baseline = set(json.loads(read(baseline_path)))
        except Exception:
            baseline = set()
        missing = sorted(baseline - testids)
        checks.append({
            "name": "data-testid-preserved",
            "ok": not missing,
            "detail": ("all baseline testids present" if not missing
                       else "missing: %s" % ", ".join(missing)),
        })
    else:
        try:
            with open(baseline_path, "w", encoding="utf-8") as f:
                json.dump(sorted(testids), f)
            notes.append("recorded data-testid baseline (%d ids); rerun after edits to detect removals" % len(testids))
        except Exception:
            notes.append("could not write data-testid baseline")
        checks.append({
            "name": "data-testid-preserved",
            "ok": True,
            "detail": "baseline recorded this run (%d ids)" % len(testids),
        })

    # performance.mark preserved in product card components.
    if product_card_marks:
        ok = all(flag for _, flag in product_card_marks)
        checks.append({
            "name": "performance-mark-preserved",
            "ok": ok,
            "detail": ("performance.mark present in product card(s)" if ok
                       else "performance.mark missing in: %s" %
                       ", ".join(p for p, f in product_card_marks if not f)),
        })
    else:
        checks.append({
            "name": "performance-mark-preserved",
            "ok": True,
            "detail": "no ProductCard file found to check",
        })

    # Optimization signals (informational).
    joined = "\n".join(all_text.values())
    for name, pat in (("promise-all-present", r"Promise\.all\s*\("),
                      ("react-memo-present", r"React\.memo|\bmemo\s*\("),
                      ("usecallback-present", r"useCallback\s*\("),
                      ("usememo-present", r"useMemo\s*\("),
                      ("dynamic-import-present", r"\bdynamic\s*\(|React\.lazy\s*\(")):
        notes.append("%s: %s" % (name, bool(re.search(pat, joined))))

    ok = all(c["ok"] for c in checks)
    json.dump({"ok": ok, "checks": checks, "notes": notes},
              sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
