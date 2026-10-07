#!/usr/bin/env python3
"""Validate the public answer-file contract without judging semantic correctness."""
import json
import re
import sys
from pathlib import Path

KEYED_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*[:=]")

def keys_for(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return list(obj.keys())
    except json.JSONDecodeError:
        pass
    return [m.group(1) for line in text.splitlines() if (m := KEYED_LINE.match(line))]

def main():
    errors = []
    try:
        req = json.load(sys.stdin)
        expected = keys_for(req["questions_path"])
        data = json.loads(Path(req["answer_path"]).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            errors.append("answer root must be a JSON object")
            data = {}
        if set(data) != set(expected):
            errors.append("answer keys differ from question keys; expected=%r got=%r" % (expected, list(data)))
        for key in expected:
            item = data.get(key)
            if not isinstance(item, dict):
                errors.append("%s must contain an object" % key)
                continue
            if set(item) != {"answer", "tokens"}:
                errors.append("%s must contain exactly answer and tokens" % key)
            if not isinstance(item.get("answer"), list):
                errors.append("%s.answer must be a list" % key)
            if not isinstance(item.get("tokens"), str):
                errors.append("%s.tokens must be a string" % key)
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    result = {"valid": not errors, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
