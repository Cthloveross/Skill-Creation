"""Entrypoint orchestrator: apply string-level redaction to one or more PDFs and
verify each result. Regenerates every requested output.

stdin JSON:
{"jobs": [
   {"input": "/root/paper1.pdf",
    "output": "/root/redacted/paper1.pdf",
    "redactions": ["Full Name", {"text": "arXiv:2401.12345", "scope": "all"}, ...],
    "clear_metadata": true}
   , ...
]}

stdout JSON:
{"jobs": [ {redaction report + "verification": {...}} ... ], "all_ok": bool}

redactions entries: plain strings default to scope "before_references" (keeps the
references list untouched); use {"text":..,"scope":"all"} for the paper's own exact
arXiv/DOI/venue identifiers so running headers/footers are also cleaned.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_redact as pr  # noqa: E402
import verify as verifier  # noqa: E402


def main():
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"error": "invalid stdin JSON: %s" % e}))
        return
    if not pr.HAVE_FITZ:
        print(json.dumps({"error": "PyMuPDF (fitz) not installed. Run: pip install pymupdf"}))
        return

    jobs = req.get("jobs", [])
    reports = []
    all_ok = True
    for job in jobs:
        inp = job.get("input")
        out = job.get("output")
        reds = job.get("redactions", [])
        clear_md = bool(job.get("clear_metadata", False))
        if not inp or not os.path.exists(inp):
            reports.append({"input": inp, "error": "input not found"})
            all_ok = False
            continue
        if not out:
            reports.append({"input": inp, "error": "no output path"})
            all_ok = False
            continue
        try:
            rep = pr.redact_pdf(inp, out, reds, clear_metadata=clear_md)
        except Exception as e:
            reports.append({"input": inp, "error": str(e)})
            all_ok = False
            continue
        targets = [
            (e if isinstance(e, str) else e.get("text", "")) for e in reds
        ]
        targets = [t for t in targets if t]
        try:
            v = verifier.verify(inp, out, targets)
        except Exception as e:
            v = {"error": str(e)}
        rep["verification"] = v
        ok = (
            rep.get("page_count_ok")
            and not v.get("remaining_targets")
            and v.get("page_count_ok", True)
        )
        rep["ok"] = bool(ok)
        if not ok:
            all_ok = False
        reports.append(rep)

    print(json.dumps({"jobs": reports, "all_ok": all_ok}, ensure_ascii=False))


if __name__ == "__main__":
    main()
