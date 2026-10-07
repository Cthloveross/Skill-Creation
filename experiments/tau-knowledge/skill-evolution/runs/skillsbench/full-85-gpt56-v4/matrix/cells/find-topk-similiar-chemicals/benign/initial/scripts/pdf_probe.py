#!/usr/bin/env python3
"""Inspect PDF text and tables. stdin: {pdf_path, max_chars?, max_rows?}; stdout JSON."""
import json
import sys


def main():
    request = json.load(sys.stdin)
    path = request["pdf_path"]
    max_chars = int(request.get("max_chars", 5000))
    max_rows = int(request.get("max_rows", 12))
    pages = []
    errors = []

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for number, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                table_preview = []
                try:
                    for table in page.extract_tables() or []:
                        table_preview.append((table or [])[:max_rows])
                except Exception as exc:
                    errors.append("pdfplumber table page %d: %s" % (number, exc))
                pages.append({"page": number, "text": text[:max_chars], "tables": table_preview})
        backend = "pdfplumber"
    except Exception as exc:
        errors.append("pdfplumber: %s" % exc)
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            for number, page in enumerate(reader.pages, 1):
                pages.append({"page": number, "text": (page.extract_text() or "")[:max_chars], "tables": []})
            backend = "pypdf"
        except Exception as fallback:
            raise RuntimeError("No usable PDF text extractor: %s" % fallback)

    print(json.dumps({"backend": backend, "page_count": len(pages), "pages": pages, "warnings": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
