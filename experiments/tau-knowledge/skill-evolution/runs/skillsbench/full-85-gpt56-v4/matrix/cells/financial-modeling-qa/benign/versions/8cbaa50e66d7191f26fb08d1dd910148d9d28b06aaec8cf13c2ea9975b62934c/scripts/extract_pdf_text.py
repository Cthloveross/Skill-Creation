#!/usr/bin/env python3
"""Extract embedded PDF text page-by-page. JSON stdin -> JSON stdout."""
import json
import os
import sys


def emit(value, code=0):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    raise SystemExit(code)


def main():
    try:
        request = json.load(sys.stdin)
        path = request["pdf_path"]
        if not isinstance(path, str) or not os.path.isfile(path):
            emit({"ok": False, "error": "pdf_path is not a readable file"}, 2)
        reader = None
        errors = []
        for module_name, class_name in (("pypdf", "PdfReader"), ("PyPDF2", "PdfReader")):
            try:
                mod = __import__(module_name, fromlist=[class_name])
                reader = getattr(mod, class_name)(path)
                break
            except Exception as exc:
                errors.append(f"{module_name}: {exc}")
        if reader is None:
            emit({"ok": False, "error": "No supported Python PDF reader is available", "details": errors}, 2)
        pages = []
        blank_pages = []
        for index, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                emit({"ok": False, "error": f"Cannot extract page {index}: {exc}"}, 2)
            pages.append({"page": index, "text": text})
            if len(text.strip()) < 20:
                blank_pages.append(index)
        emit({"ok": True, "pdf_path": path, "page_count": len(pages), "blank_or_nearly_blank_pages": blank_pages,
              "ocr_or_visual_review_needed": bool(blank_pages), "pages": pages})
    except KeyError as exc:
        emit({"ok": False, "error": f"Missing required field: {exc.args[0]}"}, 2)
    except json.JSONDecodeError as exc:
        emit({"ok": False, "error": f"Invalid JSON input: {exc}"}, 2)
    except Exception as exc:
        emit({"ok": False, "error": str(exc)}, 2)


if __name__ == "__main__":
    main()
