#!/usr/bin/env python3
"""Extract text from the reflow handbook PDF.

stdin : {"pdf_path": "/app/data/handbook.pdf", "max_pages": optional int}
stdout: {"backend": str, "n_pages": int, "pages": [{"page": int, "text": str}]}

Tries pdfplumber, then PyPDF2, then the `pdftotext` CLI. Reports which backend
succeeded so the executor can trust/verify the extraction.
"""
import json
import subprocess
import sys


def via_pdfplumber(path, max_pages):
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for i, pg in enumerate(pdf.pages):
            if max_pages and i >= max_pages:
                break
            pages.append({"page": i + 1, "text": pg.extract_text() or ""})
    return pages


def via_pypdf2(path, max_pages):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for i, pg in enumerate(reader.pages):
        if max_pages and i >= max_pages:
            break
        pages.append({"page": i + 1, "text": pg.extract_text() or ""})
    return pages


def via_pdftotext(path, max_pages):
    args = ["pdftotext", "-layout"]
    if max_pages:
        args += ["-l", str(max_pages)]
    args += [path, "-"]
    txt = subprocess.check_output(args, text=True, errors="replace")
    parts = txt.split("\f")
    return [{"page": i + 1, "text": p} for i, p in enumerate(parts) if p.strip()]


def main():
    cfg = json.load(sys.stdin)
    path = cfg["pdf_path"]
    max_pages = cfg.get("max_pages")
    errors = []
    for name, fn in (("pdfplumber", via_pdfplumber), ("pypdf", via_pypdf2), ("pdftotext", via_pdftotext)):
        try:
            pages = fn(path, max_pages)
            if pages:
                print(json.dumps({"backend": name, "n_pages": len(pages), "pages": pages}))
                return
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    print(json.dumps({"backend": None, "n_pages": 0, "pages": [], "errors": errors}))


if __name__ == "__main__":
    main()
