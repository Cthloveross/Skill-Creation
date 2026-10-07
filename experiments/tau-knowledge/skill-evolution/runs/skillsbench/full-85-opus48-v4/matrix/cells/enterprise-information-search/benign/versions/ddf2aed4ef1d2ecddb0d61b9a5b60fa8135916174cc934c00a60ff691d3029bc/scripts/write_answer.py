#!/usr/bin/env python3
"""Write /root/answer.json enforcing the required contract.

stdin: {
  "path": "/root/answer.json",
  "default_tokens": "0",
  "answers": { "q1": {"answer": any, "tokens": any} | any, ... }
}
stdout: {"path": str, "keys": [...], "written": true}

Rules enforced:
- every answer value becomes a list (length-1 list for a single item; [] for None)
- an existing list is kept as-is (inner element types preserved)
- tokens is stringified; missing -> default_tokens
- inner numeric/string/bool types are preserved exactly as supplied
"""
import json, sys


def to_list(ans):
    if ans is None:
        return []
    if isinstance(ans, list):
        return ans
    return [ans]


def main():
    req = json.load(sys.stdin)
    path = req.get("path", "/root/answer.json")
    default_tokens = str(req.get("default_tokens", "0"))
    answers = req.get("answers", {})
    out = {}
    for key, entry in answers.items():
        if isinstance(entry, dict) and ("answer" in entry or "tokens" in entry):
            ans = entry.get("answer")
            tokens = entry.get("tokens", default_tokens)
        else:
            # bare value supplied
            ans = entry
            tokens = default_tokens
        out[key] = {"answer": to_list(ans), "tokens": str(tokens)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"path": path, "keys": list(out.keys()),
                      "written": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
