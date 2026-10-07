#!/usr/bin/env python3
"""Read one PDF and emit discovery evidence as JSON on stdout.
Usage: python3 inspect_pdf.py INPUT.pdf
"""
import json
import sys
from pathlib import Path

try:
    import fitz
except ImportError as exc:
    raise SystemExit("PyMuPDF (fitz) is required: " + str(exc))

REF_HEADINGS = ("references", "bibliography", "literature cited", "works cited")


def reference_marker(page):
    """Return the y coordinate of a likely references heading, if any."""
    for heading in REF_HEADINGS:
        rects = page.search_for(heading)
        if rects:
            return min(r.y0 for r in rects)
    return None


def main(path):
    doc = fitz.open(path)
    pages = []
    first_ref = None
    for index, page in enumerate(doc):
        marker = reference_marker(page)
        if first_ref is None and marker is not None:
            first_ref = {"page": index + 1, "y": round(marker, 3)}
        pages.append({
            "page": index + 1,
            "text": page.get_text("text"),
            "reference_heading_y": None if marker is None else round(marker, 3),
        })
    result = {
        "input": str(Path(path)),
        "page_count": doc.page_count,
        "metadata": dict(doc.metadata or {}),
        "xml_metadata_present": bool(doc.get_xml_metadata()),
        "first_reference_marker": first_ref,
        "pages": pages,
    }
    doc.close()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: inspect_pdf.py INPUT.pdf")
    main(sys.argv[1])
