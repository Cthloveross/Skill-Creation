#!/usr/bin/env python3
"""Render PDF pages to PNG images for visual inspection.

stdin:  {"pdf": "/root/latex_paper.pdf", "out_dir": "/root/pages", "dpi": 200}
stdout: {"pages": ["/root/pages/page-001.png", ...], "engine": "pymupdf"}

Tries PyMuPDF (fitz) first, then pdf2image. If neither is available, reports
an error object so the executor can install a library or fall back.
"""
import json
import os
import sys


def main():
    data = json.load(sys.stdin)
    pdf = data["pdf"]
    out_dir = data.get("out_dir", "/root/pages")
    dpi = int(data.get("dpi", 200))
    os.makedirs(out_dir, exist_ok=True)
    pages = []

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat)
            path = os.path.join(out_dir, "page-%03d.png" % (i + 1))
            pix.save(path)
            pages.append(path)
        json.dump({"pages": pages, "engine": "pymupdf"}, sys.stdout)
        sys.stdout.write("\n")
        return
    except Exception as e_fitz:
        err1 = str(e_fitz)

    try:
        from pdf2image import convert_from_path
        imgs = convert_from_path(pdf, dpi=dpi)
        for i, img in enumerate(imgs):
            path = os.path.join(out_dir, "page-%03d.png" % (i + 1))
            img.save(path)
            pages.append(path)
        json.dump({"pages": pages, "engine": "pdf2image"}, sys.stdout)
        sys.stdout.write("\n")
        return
    except Exception as e_p2i:
        err2 = str(e_p2i)

    json.dump({"error": "no PDF render backend",
               "pymupdf_error": err1, "pdf2image_error": err2,
               "hint": "pip install pymupdf  OR  pip install pdf2image (needs poppler)"},
              sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
