"""Shared utilities for the blind PDF anonymization scripts."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REF_HEADING = re.compile(r"^\s*(?:(?:\d+|[IVXLCDM]+)\s*\.?\s*)?(references|bibliography)\s*$", re.IGNORECASE)
WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def read_request() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except Exception as exc:
        raise ValueError(f"stdin must contain one JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("stdin JSON must be an object")
    return value


def require_fitz():
    try:
        import fitz  # type: ignore
        return fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF is required: Python could not import 'fitz'") from exc


def page_texts(doc: Any) -> list[str]:
    return [page.get_text("text") for page in doc]


def find_references_page(texts: list[str]) -> int | None:
    """Return the first likely References heading page, or None.

    This is only a discovery aid. The reviewer must confirm the boundary in the
    inventory report before using before_references in a plan.
    """
    for number, text in enumerate(texts):
        for line in text.splitlines():
            if REF_HEADING.match(line):
                return number
    return None


def validate_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty path string")
    return value


def target_pages(target: dict[str, Any], page_count: int, references_page: Any) -> list[int]:
    scope = target.get("scope")
    if scope == "all":
        return list(range(page_count))
    if scope == "before_references":
        if not isinstance(references_page, int) or isinstance(references_page, bool):
            raise ValueError("before_references requires a confirmed integer references_page")
        if not 0 <= references_page < page_count:
            raise ValueError("references_page is outside the document")
        return list(range(references_page))
    if scope == "pages":
        pages = target.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("pages scope requires a nonempty pages array")
        result: list[int] = []
        for page in pages:
            if not isinstance(page, int) or isinstance(page, bool) or not 0 <= page < page_count:
                raise ValueError("each selected page must be a valid zero-based page index")
            if page not in result:
                result.append(page)
        return result
    raise ValueError("target scope must be all, before_references, or pages")


def validate_target(target: Any) -> dict[str, Any]:
    if not isinstance(target, dict):
        raise ValueError("each target must be an object")
    text = target.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("each target needs a nonempty exact text string")
    if "expected_matches" in target:
        count = target["expected_matches"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("expected_matches must be a positive integer when supplied")
    return target


def reviewed_metadata_keys(value: Any) -> list[str]:
    allowed = {"title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate", "trapped"}
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError("metadata_clear must be an array of metadata key strings")
    unknown = [x for x in value if x not in allowed]
    if unknown:
        raise ValueError("unsupported metadata_clear keys: " + ", ".join(unknown))
    return list(dict.fromkeys(value))


def words(text: str) -> list[str]:
    return [word.casefold() for word in WORD_RE.findall(text)]


def write_utf8(path_value: str, content: str) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
