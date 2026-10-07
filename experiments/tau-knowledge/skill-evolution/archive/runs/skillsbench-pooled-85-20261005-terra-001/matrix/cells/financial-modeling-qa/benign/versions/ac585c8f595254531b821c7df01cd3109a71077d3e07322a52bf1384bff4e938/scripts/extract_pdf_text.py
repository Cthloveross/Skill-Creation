#!/usr/bin/env python3
"""JSON stdin: {"pdf": path}. JSON stdout: extracted PDF text and method."""
import json
import subprocess
import sys
from pathlib import Path


def extract(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"PDF does not exist: {path}")
    try:
        from pypdf import PdfReader
        pages = PdfReader(str(path)).pages
        return {"text": "\n\n".join(page.extract_text() or "" for page in pages),
                "method": "pypdf", "pages": len(pages)}
    except ImportError:
        pass
    except Exception as exc:
        pypdf_problem = str(exc)
    try:
        result = subprocess.run(["pdftotext", str(path), "-"], text=True,
                                capture_output=True, check=True)
        return {"text": result.stdout, "method": "pdftotext"}
    except Exception as exc:
        suffix = f"; pypdf: {pypdf_problem}" if "pypdf_problem" in locals() else ""
        raise RuntimeError("Unable to extract PDF text" + suffix + f"; pdftotext: {exc}")


def main():
    try:
        obj = json.load(sys.stdin)
        print(json.dumps(extract(obj["pdf"]), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
