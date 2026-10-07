#!/usr/bin/env python3
"""Validate and atomically write the required keyed answer artifact.
Input: {question_file, output_file, answers:{key:[...]}, tokens?:{key:string},
        question_keys?:[string]}. Output: summary. Answers must already be evidence-based.
"""
import json
import os
import re
import sys
from pathlib import Path


def detect_keys(question_file):
    text = Path(question_file).read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed:
            return list(parsed.keys())
    except json.JSONDecodeError:
        pass
    # Supports conventional lines such as q1: question, "q1" = question, etc.
    found = re.findall(r"(?m)^\s*[\"']?([A-Za-z][A-Za-z0-9_-]*)[\"']?\s*[:=]", text)
    unique = []
    for key in found:
        if key not in unique:
            unique.append(key)
    if not unique:
        raise ValueError("could not detect question keys; pass question_keys explicitly")
    return unique


def main():
    request = json.load(sys.stdin)
    answers = request.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object keyed by question ID")
    supplied_keys = request.get("question_keys")
    if supplied_keys is None:
        expected = detect_keys(request["question_file"])
    else:
        if not isinstance(supplied_keys, list) or not all(isinstance(k, str) and k for k in supplied_keys):
            raise ValueError("question_keys must be a nonempty array of strings")
        expected = supplied_keys
    if len(set(expected)) != len(expected):
        raise ValueError("question keys must be unique")
    if set(answers) != set(expected):
        missing = [key for key in expected if key not in answers]
        extra = [key for key in answers if key not in expected]
        raise ValueError("answer keys do not match questions; missing=%r extra=%r" % (missing, extra))
    tokens = request.get("tokens", {})
    if not isinstance(tokens, dict):
        raise ValueError("tokens must be an object when provided")
    output = {}
    for key in expected:
        answer = answers[key]
        if not isinstance(answer, list):
            raise ValueError("answer for %s must be a list, including singleton answers" % key)
        token_value = tokens.get(key, "unavailable")
        if not isinstance(token_value, str):
            raise ValueError("token value for %s must be a string" % key)
        output[key] = {"answer": answer, "tokens": token_value}
    output_path = Path(request["output_file"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, output_path)
    print(json.dumps({"output_file": str(output_path), "question_keys": expected, "answers_written": len(output)}))


if __name__ == "__main__":
    main()
