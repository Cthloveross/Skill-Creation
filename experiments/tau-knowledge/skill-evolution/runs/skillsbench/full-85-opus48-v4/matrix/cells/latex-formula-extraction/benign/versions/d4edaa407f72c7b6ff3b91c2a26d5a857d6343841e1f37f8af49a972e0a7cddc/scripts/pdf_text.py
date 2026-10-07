#!/usr/bin/env python3
"""Dump per-page text from a PDF to help locate display lines.

stdin:  {"pdf": "/root/latex_paper.pdf"}
stdout: {"pages": [{"page": 1, "text": "..."}, ...], "engine": "..."}

Text extraction of a research PDF rarely yields clean LaTeX for math (glyphs are
positioned, not stored as source). Use this only to orient yourself; rely on the
rendered images (pdf_render.py) to transcribe formulas faithfully.
"""
import json
import sys


def main():
    data = json.load(sys.stdin)
    pdf = data["pdf"]
    pages = []

    try:
        import fitz
        doc = fitz.open(pdf)
        for i, page in enumerate(doc):
            pages.append({"page": i + 1, "text": page.get_text()})
        json.dump({"pages": pages, "engine": "pymupdf"}, sys.stdout)
        sys.stdout.write("\n")
        return
    except Exception as e1:
        err1 = str(e1)

    try:
        import pdfplumber
        with pdfplumber.open(pdf) as doc:
            for i, page in enumerate(doc.pages):
                pages.append({"page": i + 1, "text": page.extract_text() or ""})
        json.dump({"pages": pages, "engine": "pdfplumber"}, sys.stdout)
        sys.stdout.write("\n")
        return
    except Exception as e2:
        err2 = str(e2)

    json.dump({"error": "no PDF text backend",
               "pymupdf_error": err1, "pdfplumber_error": err2,
               "hint": "pip install pymupdf  OR  pip install pdfplumber"},
              sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
