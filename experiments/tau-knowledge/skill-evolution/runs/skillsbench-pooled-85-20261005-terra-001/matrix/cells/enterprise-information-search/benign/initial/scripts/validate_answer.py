#!/usr/bin/env python3
"""Check answer artifact structure; does not judge factual correctness."""
import ast, json, re, sys
from pathlib import Path

def qkeys(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    for loader in (json.loads, ast.literal_eval):
        try:
            x = loader(text)
            if isinstance(x, dict): return set(map(str, x))
        except Exception: pass
    return {m.group(1) for m in re.finditer(r"^\s*([A-Za-z][\w.-]*)\s*[:：]", text, re.M)}

def main():
    req = json.load(sys.stdin); issues = []
    try:
        data = json.loads(Path(req.get("answer_path", "/root/answer.json")).read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "issues": [f"cannot read valid JSON: {e}"]})); return
    if not isinstance(data, dict): issues.append("top level must be an object")
    else:
        for key, row in data.items():
            if not isinstance(row, dict): issues.append(f"{key}: value must be an object")
            elif "answer" not in row or "tokens" not in row: issues.append(f"{key}: requires answer and tokens")
        if req.get("questions_path"):
            expected = qkeys(req["questions_path"]); got = set(data)
            if expected and expected != got: issues.append("question key mismatch: missing=%s extra=%s" % (sorted(expected-got), sorted(got-expected)))
    print(json.dumps({"ok": not issues, "issues": issues, "keys": list(data) if isinstance(data, dict) else []}))
if __name__ == "__main__": main()
