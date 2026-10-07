#!/usr/bin/env python3
"""Build the D3 v6 stock bubble + table dashboard.

Reads a JSON config on stdin, writes the web app, prints a JSON report on
stdout. See SKILL.md for the schema.
"""
import csv
import json
import os
import shutil
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "references")

DEFAULTS = {
    "descriptions": "/root/data/stock-descriptions.csv",
    "indiv_dir": "/root/data/indiv-stock",
    "output_dir": "/root/output",
    "d3_path": None,
}

FIELD_CANDIDATES = {
    "ticker": ["symbol", "ticker", "tickerSymbol", "Symbol", "Ticker"],
    "name": ["longName", "shortName", "companyName", "name", "Name",
             "longname", "company"],
    "sector": ["sector", "Sector", "gicsSector"],
    "marketCap": ["marketCap", "market_cap", "marketcap", "MarketCap",
                  "MarketCapitalization", "marketCapitalization"],
}

D3_URLS = [
    "https://d3js.org/d3.v6.min.js",
    "https://cdn.jsdelivr.net/npm/d3@6/dist/d3.min.js",
    "https://unpkg.com/d3@6/dist/d3.min.js",
]

D3_SEARCH = [
    "/root/output/js/d3.v6.min.js",
    "/root/d3.v6.min.js",
    "/usr/share/d3/d3.v6.min.js",
]


def resolve_field(header, kind):
    lower = {h.lower(): h for h in header}
    for cand in FIELD_CANDIDATES[kind]:
        if cand in header:
            return cand
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def looks_like_d3(data: bytes) -> bool:
    if len(data) < 20000:
        return False
    txt = data[:4000].decode("utf-8", "ignore")
    return ("d3" in txt) and ("6." in txt or "version" in txt or "exports" in txt)


def obtain_d3(output_js_dir, d3_path):
    dest = os.path.join(output_js_dir, "d3.v6.min.js")
    # 1. explicit path
    candidates = []
    if d3_path:
        candidates.append((d3_path, "local"))
    # 2/3. existing / common locations
    for p in D3_SEARCH:
        candidates.append((p, "cache"))
    for path, src in candidates:
        try:
            if path and os.path.isfile(path):
                with open(path, "rb") as f:
                    data = f.read()
                if looks_like_d3(data):
                    with open(dest, "wb") as f:
                        f.write(data)
                    return src, len(data)
        except OSError:
            continue
    # 4. download
    last_err = None
    for url in D3_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if looks_like_d3(data):
                with open(dest, "wb") as f:
                    f.write(data)
                return "download", len(data)
        except Exception as e:  # noqa: BLE001
            last_err = "%s: %s" % (url, e)
            continue
    raise RuntimeError(
        "Could not obtain a valid d3.v6.min.js. Provide d3_path or enable "
        "internet. Last error: %s" % last_err
    )


def copy_tree_csv(src_dir, dst_dir):
    if not os.path.isdir(src_dir):
        return []
    os.makedirs(dst_dir, exist_ok=True)
    copied = []
    for name in sorted(os.listdir(src_dir)):
        sp = os.path.join(src_dir, name)
        if os.path.isfile(sp):
            shutil.copy2(sp, os.path.join(dst_dir, name))
            copied.append(name)
    return copied


def read_template(name):
    with open(os.path.join(REF, name), "r", encoding="utf-8") as f:
        return f.read()


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = dict(DEFAULTS)
        if raw:
            cfg.update(json.loads(raw))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"status": "error", "message": "bad stdin: %s" % e}))
        return 1

    descriptions = cfg["descriptions"]
    indiv_dir = cfg["indiv_dir"]
    output_dir = cfg["output_dir"]

    try:
        if not os.path.isfile(descriptions):
            raise FileNotFoundError("descriptions CSV not found: %s" % descriptions)

        js_dir = os.path.join(output_dir, "js")
        css_dir = os.path.join(output_dir, "css")
        data_dir = os.path.join(output_dir, "data")
        for d in (output_dir, js_dir, css_dir, data_dir):
            os.makedirs(d, exist_ok=True)

        # copy data
        shutil.copy2(descriptions, os.path.join(data_dir, "stock-descriptions.csv"))
        copied = copy_tree_csv(indiv_dir, os.path.join(data_dir, "indiv-stock"))

        # inspect header + row count
        with open(descriptions, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            num_rows = sum(1 for _ in reader)
        resolved = {k: resolve_field(header, k) for k in FIELD_CANDIDATES}

        # obtain d3
        d3_src, d3_bytes = obtain_d3(js_dir, cfg.get("d3_path"))

        # write templates
        index_html = read_template("index.html")
        style_css = read_template("style.css")
        viz_js = read_template("visualization.js.tmpl")
        viz_js = viz_js.replace("__FIELD_MAP__", json.dumps(resolved))

        with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html)
        with open(os.path.join(css_dir, "style.css"), "w", encoding="utf-8") as f:
            f.write(style_css)
        with open(os.path.join(js_dir, "visualization.js"), "w", encoding="utf-8") as f:
            f.write(viz_js)

        files = [
            "index.html", "js/d3.v6.min.js", "js/visualization.js",
            "css/style.css", "data/stock-descriptions.csv",
        ] + ["data/indiv-stock/%s" % n for n in copied]

        report = {
            "status": "ok",
            "output_dir": output_dir,
            "files": files,
            "num_rows": num_rows,
            "columns": header,
            "resolved_fields": resolved,
            "d3_source": d3_src,
            "d3_bytes": d3_bytes,
        }
        if any(v is None for v in resolved.values()):
            report["message"] = (
                "Some fields unresolved; extend FIELD_CANDIDATES. "
                "Runtime JS also re-resolves case-insensitively."
            )
        print(json.dumps(report))
        return 0
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"status": "error", "message": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
