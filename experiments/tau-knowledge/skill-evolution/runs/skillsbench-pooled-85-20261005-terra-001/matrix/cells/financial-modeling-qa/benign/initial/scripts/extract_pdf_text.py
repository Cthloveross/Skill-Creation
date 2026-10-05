#!/usr/bin/env python3
"""Read JSON {"pdf": path} from stdin and emit JSON {"text": string, "method": string}."""
import json
import subprocess
import sys
from pathlib import Path


def main(obj):
    path = Path(obj["pdf"])
    if not path.is_file():
        raise ValueError("PDF does not exist: " + str(path))
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return {"text": "\n\n".join((p.extract_text() or "") for p in reader.pages),
                "method": "pypdf", "pages": len(reader.pages)}
    except ImportError:
        pass
    except Exception as exc:
        pypdf_error = str(exc)
    else:
        pypdf_error = ""
    try:
        result = subprocess.run(["pdftotext", str(path), "-"], check=True,
                                text=True, capture_output=True)
        return {"text": result.stdout, "method": "pdftotext"}
    except Exception as exc:
        detail = ("; pypdf: " + pypdf_error) if 'pypdf_error' in locals() else ""
        raise RuntimeError("Cannot extract PDF text; install pypdf or pdftotext" + detail + "; pdftotext: " + str(exc))


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
