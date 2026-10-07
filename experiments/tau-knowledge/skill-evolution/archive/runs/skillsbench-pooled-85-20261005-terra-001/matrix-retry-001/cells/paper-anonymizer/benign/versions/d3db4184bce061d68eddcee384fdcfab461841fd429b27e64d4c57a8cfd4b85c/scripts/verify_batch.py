"""Validate produced anonymized PDFs. stdin JSON: {"inputs":[...],"output_dir":"/..."}."""
from __future__ import annotations
import json, sys
from pathlib import Path
try:
    import fitz
except Exception as exc:
    fitz = None; FITZ_ERROR = str(exc)
else: FITZ_ERROR = ""
def main() -> int:
    try:
        if fitz is None: raise RuntimeError("PyMuPDF (fitz) is required: " + FITZ_ERROR)
        req = json.load(sys.stdin)
        if not isinstance(req, dict) or not isinstance(req.get("inputs"), list) or not req["inputs"] or not isinstance(req.get("output_dir"), str) or not req["output_dir"]: raise ValueError("need nonempty inputs array and output_dir")
        jobs=[]
        for item in req["inputs"]:
            source, output = Path(item), Path(req["output_dir"]) / Path(item).name
            issues=[]
            if not source.is_file(): issues.append("source missing")
            if not output.is_file(): issues.append("output missing")
            if not issues:
                a=fitz.open(str(source)); b=fitz.open(str(output))
                try:
                    if a.page_count != b.page_count or not b.page_count: issues.append("page count differs")
                    if sum(len(p.get_text("text")) for p in b) <= 100: issues.append("implausibly little text")
                    author=str(b.metadata.get("author") or "").strip().casefold()
                    if author and author not in {"anonymous","anon","none"}: issues.append("non-anonymous Author metadata")
                    jobs.append({"input":str(source),"output":str(output),"ok":not issues,"original_page_count":a.page_count,"output_page_count":b.page_count,"issues":issues})
                finally: a.close(); b.close()
            else: jobs.append({"input":str(source),"output":str(output),"ok":False,"issues":issues})
        result={"status":"ok" if all(x["ok"] for x in jobs) else "error","jobs":jobs}
        print(json.dumps(result,sort_keys=True)); return 0 if result["status"]=="ok" else 2
    except Exception as exc:
        print(json.dumps({"status":"error","error":str(exc)})); return 2
if __name__ == "__main__": sys.exit(main())
