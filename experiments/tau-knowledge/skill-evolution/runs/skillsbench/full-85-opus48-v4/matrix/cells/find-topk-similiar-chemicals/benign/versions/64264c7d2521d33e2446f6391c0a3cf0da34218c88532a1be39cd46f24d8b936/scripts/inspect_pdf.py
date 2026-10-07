#!/usr/bin/env python3
"""Preview how the pool PDF parses, to validate/tune name extraction.

Stdin (JSON, optional): {"pdf_path": "/root/molecules.pdf", "max": 40}
Stdout (JSON): {"table_pages": int, "n_names": int, "sample": [...], "text_preview": "..."}
"""
import json
import os
import sys


def main():
    raw = sys.stdin.read().strip()
    cfg = {}
    if raw:
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}
    pdf_path = cfg.get("pdf_path") or "/root/molecules.pdf"
    max_n = int(cfg.get("max", 40))

    here = os.path.dirname(os.path.abspath(__file__))
    ref = os.path.normpath(os.path.join(here, "..", "references"))
    sys.path.insert(0, ref)
    import solution_source as sol  # type: ignore

    import pdfplumber

    table_pages = 0
    text_preview = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                if page.extract_tables():
                    table_pages += 1
            except Exception:
                pass
        if pdf.pages:
            text_preview = (pdf.pages[0].extract_text() or "")[:800]

    names = sol._extract_names_from_pdf(pdf_path)
    print(json.dumps({
        "table_pages": table_pages,
        "n_names": len(names),
        "sample": names[:max_n],
        "text_preview": text_preview,
    }))


if __name__ == "__main__":
    main()
