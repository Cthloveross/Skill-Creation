#!/usr/bin/env python3
"""Extract PDF review material for blind-review redaction.

stdin:  {"inputs": ["input.pdf", ...]}
stdout: {"documents": [{path, page_count, metadata, reference_boundary, pages, candidates}]}

Candidates are concrete strings to review, not approved redaction instructions.
"""
import json
import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError as exc:
    raise SystemExit("PyMuPDF (fitz) is required: " + str(exc))

ARXIV_RE = re.compile(r"\barXiv\s*:\s*(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", re.I)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
REF_RE = re.compile(r"^\s*(?:\d+\.?\s+)?(?:references|bibliography)\s*$", re.I)
CLUE_RE = re.compile(r"\b(?:accepted|acceptance|proceedings|conference|published|copyright|camera[ -]?ready)\b", re.I)


def boundary(doc, page_texts):
    for index, text in enumerate(page_texts):
        for line in text.splitlines():
            heading = line.strip()
            if REF_RE.match(heading):
                hits = doc[index].search_for(heading)
                return {"page": index + 1, "y": (float(hits[0].y0) if hits else None), "heading": heading}
    return None


def context(text, start, end):
    return text[max(0, start - 150):min(len(text), end + 150)].replace("\n", " ")


def inspect(path):
    doc = fitz.open(path)
    try:
        texts = [page.get_text("text") for page in doc]
        candidates = []
        for pno, text in enumerate(texts, 1):
            for label, regex in (("email", EMAIL_RE), ("arxiv_id", ARXIV_RE), ("doi", DOI_RE)):
                for match in regex.finditer(text):
                    candidates.append({"category": label, "page": pno, "text": match.group(0),
                                       "context": context(text, match.start(), match.end())})
            for line in text.splitlines():
                if CLUE_RE.search(line):
                    candidates.append({"category": "venue_or_acceptance_clue", "page": pno,
                                       "text": line.strip(), "context": line.strip()})
        return {"path": str(path), "page_count": doc.page_count,
                "metadata": dict(doc.metadata or {}), "reference_boundary": boundary(doc, texts),
                "pages": [{"page": n + 1, "text": text} for n, text in enumerate(texts)],
                "candidates": candidates,
                "review_note": "Read bylines, acknowledgements, contribution notes, headers, and footers manually. Preserve references and self-citations."}
    finally:
        doc.close()


def main():
    request = json.load(sys.stdin)
    inputs = request.get("inputs") if isinstance(request, dict) else None
    if not isinstance(inputs, list) or not inputs or not all(isinstance(p, str) for p in inputs):
        raise ValueError("input must contain a nonempty inputs array of paths")
    missing = [p for p in inputs if not Path(p).is_file()]
    if missing:
        raise FileNotFoundError("input PDF(s) not found: " + ", ".join(missing))
    print(json.dumps({"documents": [inspect(p) for p in inputs]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
