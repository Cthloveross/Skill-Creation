#!/usr/bin/env python3
"""Atomically write task answer JSON. stdin: answers, output_path?, questions_path?, tokens?."""
import ast, json, os, re, sys
from pathlib import Path

def keys_from_question(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    for loader in (json.loads, ast.literal_eval):
        try:
            x = loader(text)
            if isinstance(x, dict): return [str(k) for k in x]
        except Exception: pass
    result = []
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z][\w.-]*)\s*[:：]", line)
        if m: result.append(m.group(1))
    return result

def main():
    req = json.load(sys.stdin)
    answers = req.get("answers")
    if not isinstance(answers, dict): raise SystemExit("answers must be an object keyed by question ID")
    expected = keys_from_question(req["questions_path"]) if req.get("questions_path") else []
    actual = [str(k) for k in answers]
    if expected and (set(expected) != set(actual)):
        raise SystemExit("answer keys do not match questions; missing=%s extra=%s" %
                         (sorted(set(expected)-set(actual)), sorted(set(actual)-set(expected))))
    tokens = req.get("tokens", "not_available")
    rendered = {}
    for key, value in answers.items():
        token_value = tokens.get(str(key), "not_available") if isinstance(tokens, dict) else tokens
        rendered[str(key)] = {"answer": value, "tokens": token_value}
    out = Path(req.get("output_path", "/root/answer.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_name(out.name + ".tmp")
    temp.write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, out)
    print(json.dumps({"ok": True, "output_path": str(out), "question_keys": list(rendered), "count": len(rendered)}))
if __name__ == "__main__": main()
