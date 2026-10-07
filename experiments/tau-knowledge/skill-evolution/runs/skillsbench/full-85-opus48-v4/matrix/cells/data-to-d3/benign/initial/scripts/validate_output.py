#!/usr/bin/env python3
"""Structural validation of the generated dashboard.

stdin: {"output_dir": "/root/output"}
stdout: {"ok": bool, "checks": [{"name":..., "ok":bool, "detail":...}]}
Does not run a browser; verifies files and required code/markup markers.
"""
import json
import os
import sys


def main():
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "checks": [
            {"name": "stdin", "ok": False, "detail": str(e)}]}))
        return 1
    out = cfg.get("output_dir", "/root/output")
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    required = [
        "index.html", "js/d3.v6.min.js", "js/visualization.js",
        "css/style.css", "data/stock-descriptions.csv",
    ]
    for rel in required:
        p = os.path.join(out, rel)
        add("exists:" + rel, os.path.isfile(p), p)

    # d3 is a real library
    d3p = os.path.join(out, "js/d3.v6.min.js")
    if os.path.isfile(d3p):
        sz = os.path.getsize(d3p)
        add("d3-size", sz > 20000, "%d bytes" % sz)

    def read(rel):
        p = os.path.join(out, rel)
        if not os.path.isfile(p):
            return ""
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    html = read("index.html")
    for marker in ["js/d3.v6.min.js", "js/visualization.js", "css/style.css"]:
        add("index-refs:" + marker, marker in html)
    for col in ["Ticker symbol", "Full company name", "Sector", "Market cap"]:
        add("table-col:" + col, col in html)

    js = read("visualization.js")
    for marker in ["forceX", "forceY", "forceCollide", "scaleSqrt"]:
        add("js-has:" + marker, marker in js)
    add("js-etf-tooltip-guard", "isETF" in js)
    add("js-linking", "selected" in js and "data-ticker" in js)
    add("js-legend", "legend" in js.lower())

    css = read("css/style.css")
    add("css-flex", "flex" in css)
    add("css-selected", ".selected" in css or "selected" in css)

    add("data-indiv-dir", os.path.isdir(os.path.join(out, "data/indiv-stock")))

    ok = all(c["ok"] for c in checks)
    print(json.dumps({"ok": ok, "checks": checks}))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
