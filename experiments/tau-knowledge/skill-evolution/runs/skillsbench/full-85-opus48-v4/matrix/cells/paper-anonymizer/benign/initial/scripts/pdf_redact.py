"""Core PyMuPDF redaction helpers (string-level only).

All functions operate on specific text strings discovered during the discovery
phase. No area/region redaction is ever used.
"""
import re

try:
    import fitz  # PyMuPDF
    HAVE_FITZ = True
except Exception:  # pragma: no cover
    HAVE_FITZ = False

_REF_HEADINGS = {"references", "bibliography", "references and notes"}


def find_references_boundary(doc):
    """Return (page_index, y_top) of the References/Bibliography heading, else None.

    Scans forward for a line whose stripped text (minus leading section numbers
    and trailing punctuation) exactly equals a known heading.
    """
    for pno in range(len(doc)):
        page = doc[pno]
        try:
            d = page.get_text("dict")
        except Exception:
            continue
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                txt = "".join(s.get("text", "") for s in line.get("spans", []))
                clean = txt.strip()
                clean = re.sub(r"^[0-9IVX]+[.)]?\s*", "", clean)  # drop section number
                clean = clean.strip(" .:").lower()
                if clean in _REF_HEADINGS:
                    return (pno, line.get("bbox", [0, 0, 0, 0])[1])
    return None


def _normalize_entries(redactions, default_scope="before_references"):
    out = []
    for e in redactions:
        if isinstance(e, str):
            text, scope = e, default_scope
        elif isinstance(e, dict):
            text = e.get("text", "")
            scope = e.get("scope", default_scope)
        else:
            continue
        text = (text or "").strip()
        if text:
            out.append((text, scope))
    return out


def redact_pdf(input_path, output_path, redactions, clear_metadata=False):
    """Apply string-level redaction. Returns a report dict.

    redactions: list of strings or {"text":str,"scope":"all"|"before_references"}.
    Preserves page count; applies redaction annotations and removes text data.
    """
    if not HAVE_FITZ:
        raise RuntimeError("PyMuPDF (fitz) not installed. Run: pip install pymupdf")
    entries = _normalize_entries(redactions)
    doc = fitz.open(input_path)
    n_pages_in = len(doc)
    ref_boundary = find_references_boundary(doc)
    counts = {text: 0 for text, _ in entries}

    for pno in range(len(doc)):
        page = doc[pno]
        added = 0
        for text, scope in entries:
            try:
                rects = page.search_for(text)
            except Exception:
                rects = []
            for r in rects:
                if scope == "before_references" and ref_boundary is not None:
                    ref_page, ref_y = ref_boundary
                    if pno > ref_page:
                        continue
                    if pno == ref_page and r.y0 >= ref_y:
                        continue
                page.add_redact_annot(r, fill=(0, 0, 0))
                counts[text] += 1
                added += 1
        if added:
            page.apply_redactions()

    if clear_metadata:
        md = doc.metadata or {}
        for field in ("author", "creator", "keywords"):
            if field in md:
                md[field] = ""
        try:
            doc.set_metadata(md)
        except Exception:
            pass

    import os
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    doc.save(output_path, garbage=4, deflate=True)
    n_pages_out = len(doc)
    doc.close()
    return {
        "input": input_path,
        "output": output_path,
        "pages_in": n_pages_in,
        "pages_out": n_pages_out,
        "page_count_ok": n_pages_in == n_pages_out,
        "references_boundary": (
            {"page": ref_boundary[0], "y": ref_boundary[1]} if ref_boundary else None
        ),
        "match_counts": counts,
        "unmatched_targets": [t for t, c in counts.items() if c == 0],
    }


def extract_text_pages(path):
    if not HAVE_FITZ:
        raise RuntimeError("PyMuPDF (fitz) not installed. Run: pip install pymupdf")
    doc = fitz.open(path)
    pages = [doc[i].get_text("text") for i in range(len(doc))]
    n = len(doc)
    doc.close()
    return pages, n
