"""Verification helper.

stdin JSON : {"original": "/root/paper1.pdf",
              "redacted": "/root/redacted/paper1.pdf",
              "targets": ["Full Name", "arXiv:2401.12345", ...]}
stdout JSON: {
  "remaining_targets": [...],   # target strings still present (under-redaction)
  "page_count_ok": bool,
  "pages_original": int, "pages_redacted": int,
  "words_original": int, "words_redacted": int,
  "extra_words_removed": int    # non-target words lost (over-redaction if large)
}
"""
import sys
import os
import json
import re
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_redact as pr  # noqa: E402

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def verify(original, redacted, targets):
    orig_pages, n_orig = pr.extract_text_pages(original)
    red_pages, n_red = pr.extract_text_pages(redacted)
    orig_text = "\n".join(orig_pages)
    red_text = "\n".join(red_pages)
    red_lower = red_text.lower()

    remaining = []
    target_words = set()
    for t in targets:
        t = (t or "").strip()
        if not t:
            continue
        if t.lower() in red_lower:
            remaining.append(t)
        for w in _WORD_RE.findall(t.lower()):
            target_words.add(w)

    orig_counts = Counter(w.lower() for w in _WORD_RE.findall(orig_text))
    red_counts = Counter(w.lower() for w in _WORD_RE.findall(red_text))
    extra_removed = 0
    for w, c in orig_counts.items():
        if w in target_words:
            continue
        lost = c - red_counts.get(w, 0)
        if lost > 0:
            extra_removed += lost

    return {
        "remaining_targets": remaining,
        "page_count_ok": n_orig == n_red,
        "pages_original": n_orig,
        "pages_redacted": n_red,
        "words_original": sum(orig_counts.values()),
        "words_redacted": sum(red_counts.values()),
        "extra_words_removed": extra_removed,
    }


def main():
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"error": "invalid stdin JSON: %s" % e}))
        return
    if not pr.HAVE_FITZ:
        print(json.dumps({"error": "PyMuPDF (fitz) not installed. Run: pip install pymupdf"}))
        return
    original = req.get("original")
    redacted = req.get("redacted")
    targets = req.get("targets", [])
    if not original or not os.path.exists(original):
        print(json.dumps({"error": "original not found: %s" % original}))
        return
    if not redacted or not os.path.exists(redacted):
        print(json.dumps({"error": "redacted not found: %s" % redacted}))
        return
    print(json.dumps(verify(original, redacted, targets), ensure_ascii=False))


if __name__ == "__main__":
    main()
