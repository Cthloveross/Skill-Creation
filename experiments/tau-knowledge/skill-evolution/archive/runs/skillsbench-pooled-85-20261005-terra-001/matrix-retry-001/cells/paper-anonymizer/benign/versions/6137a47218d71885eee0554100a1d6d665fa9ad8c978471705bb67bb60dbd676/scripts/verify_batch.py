"""Post-production structural and reviewed-target validation for anonymized PDFs.

stdin JSON: {"inputs":["/source.pdf"], "output_dir":"/out",
             "targets_by_input":{"/source.pdf":["reviewed target", ...]}}
stdout JSON: {"status":"ok|error", "jobs":[...]}. Requires PyMuPDF.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

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
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        inputs = request.get("inputs")
        output_dir = request.get("output_dir")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) and x for x in inputs):
            raise ValueError("inputs must be a nonempty array of paths")
        if not isinstance(output_dir, str) or not output_dir:
            raise ValueError("output_dir must be a nonempty path")
        target_map = request.get("targets_by_input", {})
        if not isinstance(target_map, dict):
            raise ValueError("targets_by_input must be an object")

        jobs: list[dict[str, Any]] = []
        for source_value in inputs:
            source = Path(source_value)
            output = Path(output_dir) / source.name
            issues: list[str] = []
            if not source.is_file():
                jobs.append({"input": str(source), "output": str(output), "ok": False,
                             "issues": ["source is missing"]})
                continue
            if not output.is_file():
                jobs.append({"input": str(source), "output": str(output), "ok": False,
                             "issues": ["output is missing"]})
                continue
            original = fitz.open(str(source))
            redacted = fitz.open(str(output))
            try:
                if original.page_count != redacted.page_count or redacted.page_count < 1:
                    issues.append("page count differs")
                text = "\n".join(page.get_text("text") for page in redacted)
                if len(text.strip()) <= 100:
                    issues.append("output has implausibly little extractable text")
                author = str(redacted.metadata.get("author") or "").strip().casefold()
                if author and author not in {"anonymous", "anon", "none"}:
                    issues.append("output Author metadata is non-anonymous")
                raw_targets = target_map.get(source_value, [])
                if not isinstance(raw_targets, list) or not all(isinstance(t, str) and t.strip() for t in raw_targets):
                    raise ValueError("targets_by_input validation values must be arrays of nonempty strings")
                remaining = [target for target in raw_targets if re.search(re.escape(target), text, re.I)]
                if remaining:
                    issues.append("reviewed targets remain: " + repr(remaining))
                jobs.append({"input": str(source), "output": str(output), "ok": not issues,
                             "original_page_count": original.page_count,
                             "output_page_count": redacted.page_count, "issues": issues})
            finally:
                original.close()
                redacted.close()
        result = {"status": "ok" if all(job["ok"] for job in jobs) else "error", "jobs": jobs}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "ok" else 2
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
