#!/usr/bin/env python3
"""Validate a generated similarity solution.
stdin: {solution_path, pdf_path, targets: [str], top_k: int}
stdout: {ok: bool, checks: [...], errors: [...]}
"""
import importlib.util
import json
import math
import sys


def ordered(rows):
    return rows == sorted(rows, key=lambda row: (-row[1], row[0].casefold(), row[0]))


def main():
    request = json.load(sys.stdin)
    checks, errors = [], []
    spec = importlib.util.spec_from_file_location("submitted_solution", request["solution_path"])
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        func = getattr(module, "topk_tanimoto_similarity_molecules")
        checks.append("module imports and required function exists")
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": checks, "errors": ["import: %s" % exc]}))
        return

    k = request["top_k"]
    for target in request.get("targets", []):
        try:
            first = func(target, request["pdf_path"], k)
            second = func(target, request["pdf_path"], k)
            if not isinstance(first, list):
                raise TypeError("result is not a list")
            if first != second:
                raise ValueError("repeated calls returned different results")
            if len(first) > k:
                raise ValueError("result exceeds top_k")
            for row in first:
                if not (isinstance(row, (tuple, list)) and len(row) == 2 and isinstance(row[0], str)):
                    raise TypeError("each result must be a (name, score) pair")
                score = row[1]
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("score is not a finite number in [0, 1]")
            normalized = [(r[0], float(r[1])) for r in first]
            if not ordered(normalized):
                raise ValueError("results are not sorted by score then alphabetical name")
            checks.append("validated target %r (%d results)" % (target, len(first)))
        except Exception as exc:
            errors.append("target %r: %s" % (target, exc))

    try:
        zero_target = request.get("targets", [None])[0]
        if zero_target is not None and func(zero_target, request["pdf_path"], 0) != []:
            errors.append("top_k=0 did not return []")
        elif zero_target is not None:
            checks.append("top_k=0 returns []")
    except Exception as exc:
        errors.append("top_k=0 check: %s" % exc)
    print(json.dumps({"ok": not errors, "checks": checks, "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
