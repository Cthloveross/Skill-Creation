"""Validate batch PDF artifacts. stdin: {"inputs":[...],"output_dir":"/..."}."""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    import fitz
except Exception as exc:
    fitz = None
    FITZ_ERROR = str(exc)
else:
    FITZ_ERROR = ""


def main() -> int:
    try:
        if fitz is None:
            raise RuntimeError("PyMuPDF (fitz) is required: " + FITZ_ERROR)
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("inputs"), list) or not request["inputs"]:
            raise ValueError("inputs must be a nonempty array")
        if not isinstance(request.get("output_dir"), str) or not request["output_dir"]:
            raise ValueError("output_dir must be a nonempty path")
        jobs = []
        for name in request["inputs"]:
            source = Path(name)
            output = Path(request["output_dir"]) / source.name
            issues = []
            if not source.is_file():
                issues.append("source missing")
            if not output.is_file():
                issues.append("output missing")
            if not issues:
                original = fitz.open(str(source))
                redacted = fitz.open(str(output))
                try:
                    if not redacted.page_count or redacted.page_count != original.page_count:
                        issues.append("page count differs")
                    if sum(len(page.get_text("text")) for page in redacted) <= 100:
                        issues.append("implausibly little extractable text")
                    author = str(redacted.metadata.get("author") or "").strip().casefold()
                    if author and author not in {"anonymous", "anon", "none"}:
                        issues.append("non-anonymous Author metadata")
                    jobs.append({"input": str(source), "output": str(output), "ok": not issues, "original_page_count": original.page_count, "output_page_count": redacted.page_count, "issues": issues})
                finally:
                    original.close()
                    redacted.close()
            else:
                jobs.append({"input": str(source), "output": str(output), "ok": False, "issues": issues})
        result = {"status": "ok" if all(job["ok"] for job in jobs) else "error", "jobs": jobs}
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "ok" else 2
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
