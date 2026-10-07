from __future__ import annotations
import csv, json, os, re, sys
from pdf_text import extract_pdf_text

KEYWORDS = ("preheat", "ramp", "liquidus", "TAL", "peak", "conveyor", "dwell", "speed", "rank", "defect", "yield")

def main(arg):
    data_dir = arg.get("data_dir", "/app/data")
    handbook = arg.get("handbook_path", os.path.join(data_dir, "handbook.pdf"))
    files = arg.get("csv_paths") or [os.path.join(data_dir, x) for x in
                                      ("mes_log.csv", "test_defects.csv", "thermocouples.csv")]
    schemas = {}
    for path in files:
        if not os.path.exists(path):
            schemas[path] = {"error": "file not found"}
            continue
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = []
            for _, row in zip(range(3), reader):
                rows.append(row)
            schemas[path] = {"columns": reader.fieldnames or [], "sample_rows": rows}
    text = extract_pdf_text(handbook)
    lines = text.splitlines()
    contexts = {}
    for key in KEYWORDS:
        hits = []
        for i, line in enumerate(lines):
            if re.search(re.escape(key), line, re.I):
                hits.append("\n".join(lines[max(0, i-2):min(len(lines), i+3)]))
        contexts[key] = hits[:20]
    return {"ok": True, "schemas": schemas, "handbook_text": text,
            "keyword_contexts": contexts}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise
