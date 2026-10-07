"""Shared exact-string PDF redaction routines. Uses only PyMuPDF."""
import re
from collections import Counter

import fitz

REF_HEADINGS = ("references", "bibliography", "literature cited", "works cited")
STANDARD_METADATA_KEYS = (
    "title", "author", "subject", "keywords", "creator", "producer",
    "creationDate", "modDate", "trapped", "format", "encryption",
)


def first_reference_boundary(doc):
    """Return (zero-based page, y) for first likely bibliography heading, else None."""
    for pno, page in enumerate(doc):
        found = []
        for heading in REF_HEADINGS:
            found.extend(page.search_for(heading))
        if found:
            return pno, min(rect.y0 for rect in found)
    return None


def eligible(rect, page_number, scope, boundary):
    if scope == "all" or boundary is None:
        return True
    boundary_page, boundary_y = boundary
    if page_number < boundary_page:
        return True
    if page_number > boundary_page:
        return False
    # A header above the references heading remains an eligible non-reference area.
    return rect.y0 < boundary_y


def normalize_config(cfg):
    if not isinstance(cfg, dict) or not cfg.get("input") or not cfg.get("output"):
        raise ValueError("configuration requires nonempty input and output paths")
    raw_targets = cfg.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("configuration requires a nonempty reviewed targets list")
    targets = []
    seen = set()
    for item in raw_targets:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ValueError("each target must be an object containing string text")
        text = item["text"].strip()
        if not text:
            raise ValueError("target text cannot be blank")
        scope = item.get("scope", "non_references")
        if scope not in ("all", "non_references"):
            raise ValueError("target scope must be all or non_references")
        key = (text, scope)
        if key not in seen:
            targets.append({"text": text, "scope": scope,
                            "required": bool(item.get("required", True))})
            seen.add(key)
    keys = set(cfg.get("metadata_keys", [])) | {"author", "creator"}
    bad = keys - set(STANDARD_METADATA_KEYS)
    if bad:
        raise ValueError("unsupported metadata_keys: " + ", ".join(sorted(bad)))
    return targets, keys, bool(cfg.get("clear_xmp_metadata", True))


def redact_document(doc, targets):
    boundary = first_reference_boundary(doc)
    counts = {target["text"]: 0 for target in targets}
    removed_links = 0
    for pno, page in enumerate(doc):
        # Gather exact-match annotations first, then apply once per page.
        # A hyperlink can retain an identity-bearing URI after its displayed
        # text is redacted, so delete only links intersecting a redaction box.
        redacted_rects = []
        page_links = page.get_links()
        for target in targets:
            for rect in page.search_for(target["text"]):
                if eligible(rect, pno, target["scope"], boundary):
                    page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
                    redacted_rects.append(rect)
                    counts[target["text"]] += 1
        if redacted_rects:
            for link in page_links:
                link_rect = link.get("from")
                if link_rect is not None and any(link_rect.intersects(rect) for rect in redacted_rects):
                    page.delete_link(link)
                    removed_links += 1
        page.apply_redactions(images=0, graphics=0)
    return boundary, counts, removed_links


def scrub_metadata(doc, keys, clear_xmp):
    old = dict(doc.metadata or {})
    replacement = dict(old)
    # set_metadata requires its complete standard key mapping on supported versions.
    for key in STANDARD_METADATA_KEYS:
        replacement.setdefault(key, "")
    for key in keys:
        replacement[key] = ""
    doc.set_metadata(replacement)
    if clear_xmp:
        doc.set_xml_metadata("")
    return old


def find_remaining(doc, targets):
    boundary = first_reference_boundary(doc)
    remaining = {}
    for target in targets:
        hits = []
        for pno, page in enumerate(doc):
            for rect in page.search_for(target["text"]):
                if eligible(rect, pno, target["scope"], boundary):
                    hits.append({"page": pno + 1, "rect": [round(v, 2) for v in rect]})
        remaining[target["text"]] = hits
    return boundary, remaining


def identity_bearing_links(doc, targets):
    """Return links whose stored destination directly contains a target string."""
    leaks = []
    for pno, page in enumerate(doc):
        for link in page.get_links():
            values = [str(link.get(key, "")) for key in ("uri", "file", "nameddest")]
            for target in targets:
                if any(target["text"] in value for value in values):
                    leaks.append({"page": pno + 1, "target": target["text"],
                                  "link": {key: link.get(key) for key in ("uri", "file", "nameddest") if link.get(key)}})
    return leaks

def tokens(text):
    return re.findall(r"\b[\w]+\b", text, flags=re.UNICODE)


def token_loss_summary(original, redacted, target_texts):
    """Conservative bag-of-words loss excluding words present in target strings."""
    excluded = set()
    for value in target_texts:
        excluded.update(t.casefold() for t in tokens(value))
    before, after = Counter(t.casefold() for t in tokens(original)), Counter(
        t.casefold() for t in tokens(redacted))
    losses = []
    for token, n in (before - after).items():
        if token not in excluded:
            losses.extend([token] * n)
    return {"non_target_token_loss_count": len(losses),
            "sample": losses[:50]}
