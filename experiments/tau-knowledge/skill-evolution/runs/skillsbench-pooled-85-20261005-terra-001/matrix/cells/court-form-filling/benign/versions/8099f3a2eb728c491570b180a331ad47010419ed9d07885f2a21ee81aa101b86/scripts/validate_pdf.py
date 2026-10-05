#!/usr/bin/env python3
"""Check that required factual fragments remain observable in a completed PDF."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from pdf_form import emit, load_pypdf


def compact(value: Any) -> str:
    """Case-fold and remove separators so adjacent form fields can be checked together."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def pdf_observable_text(path: Path) -> Dict[str, Any]:
    PdfReader, _, _, _, _ = load_pypdf()
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise RuntimeError("encrypted PDFs are unsupported")
    if not reader.pages:
        raise RuntimeError("PDF has no pages")

    page_pieces: List[str] = []
    extraction_errors: List[str] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            page_pieces.append(page.extract_text() or "")
        except Exception as exc:
            extraction_errors.append("page %d: %s" % (number, exc))

    field_pieces: List[str] = []
    for name, field in (reader.get_fields() or {}).items():
        field_pieces.append(str(name))
        value = field.get("/V") if hasattr(field, "get") else None
        if value is not None:
            field_pieces.append(str(value))

    return {
        "page_count": len(reader.pages),
        "field_count": len(reader.get_fields() or {}),
        "page_text": "\n".join(page_pieces),
        "field_text": "\n".join(field_pieces),
        "extraction_errors": extraction_errors,
    }


def main(request: Dict[str, Any]) -> Dict[str, Any]:
    raw_path = request.get("pdf")
    fragments = request.get("required_fragments")
    if not isinstance(raw_path, str) or not raw_path:
        raise RuntimeError("pdf must be a nonempty string")
    if not isinstance(fragments, list) or not fragments:
        raise RuntimeError("required_fragments must be a nonempty array of nonempty strings")
    if not all(isinstance(item, str) and item.strip() for item in fragments):
        raise RuntimeError("required_fragments must contain only nonempty strings")

    path = Path(raw_path)
    if not path.is_file():
        raise RuntimeError("pdf does not exist or is not a regular file: %s" % raw_path)
    observed = pdf_observable_text(path)
    searchable = compact(observed["page_text"] + "\n" + observed["field_text"])
    checks = [{"fragment": item, "found": compact(item) in searchable} for item in fragments]
    missing = [item["fragment"] for item in checks if not item["found"]]
    return {
        "ok": not bool(missing),
        "complete": not bool(missing),
        "pdf": str(path),
        "checks": checks,
        "missing": missing,
        "page_count": observed["page_count"],
        "field_count": observed["field_count"],
        "page_text_characters": len(observed["page_text"]),
        "field_text_characters": len(observed["field_text"]),
        "extraction_errors": observed["extraction_errors"],
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise RuntimeError("stdin JSON must be an object")
        result = main(request)
        emit(result)
        if not result["ok"]:
            sys.exit(1)
    except Exception as exc:
        emit({"ok": False, "complete": False, "error": str(exc)})
        sys.exit(1)
