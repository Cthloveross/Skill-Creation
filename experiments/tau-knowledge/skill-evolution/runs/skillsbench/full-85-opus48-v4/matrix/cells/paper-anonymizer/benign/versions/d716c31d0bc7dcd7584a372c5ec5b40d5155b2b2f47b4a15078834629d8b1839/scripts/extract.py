"""Discovery helper: extract per-page text, metadata, references boundary, and
regex candidate identifiers (collected only BEFORE the references section).

stdin JSON : {"pdf": "/path/to/file.pdf", "include_page_text": true}
stdout JSON: {
  "pdf", "num_pages", "metadata",
  "references_boundary": {"page":int,"y":float}|null,
  "auto_candidates": {"emails":[], "arxiv":[], "doi":[], "venue":[]},
  "pages": [{"page":int, "text":str}, ...]   # omitted if include_page_text=false
}
The person names (authors, acknowledgements, contribution footnotes) are NOT in
auto_candidates: you must read `pages` to find them.
"""
import sys
import json
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_redact as pr  # noqa: E402

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
ARXIV_RE = re.compile(r"arXiv:\s*\d{4}\.\d{4,5}(?:v\d+)?", re.IGNORECASE)
DOI_RE = re.compile(r"10\.\d{4,9}/[\-._;()/:A-Za-z0-9]+")
VENUE_HINT_RE = re.compile(
    r"(?:accepted|to appear|appears in|published in|proceedings of|"
    r"in proceedings|conference on|workshop on|camera[- ]ready)",
    re.IGNORECASE,
)


def _dedup(seq):
    seen = []
    for x in seq:
        x = x.strip()
        if x and x not in seen:
            seen.append(x)
    return seen


def main():
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"error": "invalid stdin JSON: %s" % e}))
        return
    path = req.get("pdf")
    include_text = req.get("include_page_text", True)
    if not path or not os.path.exists(path):
        print(json.dumps({"error": "pdf not found: %s" % path}))
        return
    if not pr.HAVE_FITZ:
        print(json.dumps({"error": "PyMuPDF (fitz) not installed. Run: pip install pymupdf"}))
        return

    import fitz
    doc = fitz.open(path)
    metadata = dict(doc.metadata or {})
    ref_boundary = pr.find_references_boundary(doc)
    pages_text = [doc[i].get_text("text") for i in range(len(doc))]
    num_pages = len(doc)
    doc.close()

    # Text region before references (for candidate scanning).
    if ref_boundary is not None:
        pre_pages = pages_text[: ref_boundary[0] + 1]
    else:
        pre_pages = pages_text
    pre_text = "\n".join(pre_pages)

    emails = _dedup(EMAIL_RE.findall(pre_text))
    arxiv = _dedup(m.group(0) for m in ARXIV_RE.finditer(pre_text))
    doi = _dedup(DOI_RE.findall(pre_text))
    venue_lines = []
    for ln in pre_text.splitlines():
        if VENUE_HINT_RE.search(ln):
            venue_lines.append(ln.strip())
    venue = _dedup(venue_lines)

    out = {
        "pdf": path,
        "num_pages": num_pages,
        "metadata": metadata,
        "references_boundary": (
            {"page": ref_boundary[0], "y": ref_boundary[1]} if ref_boundary else None
        ),
        "auto_candidates": {
            "emails": emails,
            "arxiv": arxiv,
            "doi": doi,
            "venue": venue,
        },
    }
    if include_text:
        out["pages"] = [{"page": i, "text": t} for i, t in enumerate(pages_text)]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
