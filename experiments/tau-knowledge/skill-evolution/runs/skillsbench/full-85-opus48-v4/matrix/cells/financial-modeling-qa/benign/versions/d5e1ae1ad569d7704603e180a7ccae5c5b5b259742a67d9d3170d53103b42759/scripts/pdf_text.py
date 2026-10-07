#!/usr/bin/env python3
"""Extract full text from a PDF.

stdin:  {"pdf_path": "/root/background.pdf"}
stdout: {"text": str, "pages": int, "engine": str}  or  {"error": str, "hint": str}
"""
import sys, json


def extract(path):
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(path) as pdf:
            for pg in pdf.pages:
                parts.append(pg.extract_text() or "")
        return "\n".join(parts), len(parts), "pdfplumber"
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("no_pdf_library")
    reader = PdfReader(path)
    parts = [(pg.extract_text() or "") for pg in reader.pages]
    return "\n".join(parts), len(parts), "pypdf"


def main():
    req = json.load(sys.stdin)
    path = req["pdf_path"]
    try:
        text, pages, engine = extract(path)
    except ImportError:
        print(json.dumps({
            "error": "no_pdf_library",
            "hint": "pip install pdfplumber (or pypdf) then re-run; internet is allowed.",
        }))
        return
    except Exception as e:  # noqa
        print(json.dumps({"error": str(e)}))
        return
    print(json.dumps({"text": text, "pages": pages, "engine": engine}))


if __name__ == "__main__":
    main()
