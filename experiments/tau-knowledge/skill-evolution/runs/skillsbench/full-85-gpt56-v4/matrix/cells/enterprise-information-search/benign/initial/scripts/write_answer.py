#!/usr/bin/env python3
"""Create the required answer artifact while enforcing complete keyed coverage."""
import json
import re
import sys
from pathlib import Path

KEYED_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*[:=]\s*(.*?)\s*$")

def question_keys(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return list(parsed.keys())
    except json.JSONDecodeError:
        pass
    keys = []
    for line in text.splitlines():
        match = KEYED_LINE.match(line)
        if match:
            keys.append(match.group(1))
    if not keys:
        raise ValueError("could not identify keyed questions in question file")
    if len(set(keys)) != len(keys):
        raise ValueError("question file has duplicate keys")
    return keys

def main():
    try:
        req = json.load(sys.stdin)
        keys = question_keys(req["questions_path"])
        answers = req["answers"]
        if not isinstance(answers, dict):
            raise ValueError("answers must be an object keyed by question")
        unknown = sorted(set(answers) - set(keys))
        missing = [key for key in keys if key not in answers]
        if unknown or missing:
            raise ValueError("answer keys mismatch; missing=%r unknown=%r" % (missing, unknown))
        token_counts = req.get("token_counts", {})
        if not isinstance(token_counts, dict):
            raise ValueError("token_counts must be an object when supplied")
        output = {}
        for key in keys:
            value = answers[key]
            output[key] = {
                "answer": value if isinstance(value, list) else [value],
                "tokens": str(token_counts.get(key, "0")),
            }
        target = Path(req.get("output_path", "/root/answer.json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"written": str(target), "keys": keys}, ensure_ascii=False))
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(2)

if __name__ == "__main__":
    main()
