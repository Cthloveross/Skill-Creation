#!/usr/bin/env python3
"""Compare a Flink output (lines of '(jobId,count)') to the oracle's expected counts.

stdin JSON: {
  "output_path": str,                 # file, or directory of part-* files
  "expected": {jobId(str): count} ,   # optional, provide this OR oracle_json_path
  "oracle_json_path": str             # optional, path to oracle.py stdout JSON
}
stdout JSON: {
  "match": bool, "num_expected": int, "num_output": int,
  "only_in_expected": [...], "only_in_output": [...],
  "count_mismatches": [[job, expected, got], ...]
}
"""
import sys
import os
import re
import json

LINE_RE = re.compile(r"\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)")


def load_expected(cfg):
    if "expected" in cfg and cfg["expected"] is not None:
        return {str(k): int(v) for k, v in cfg["expected"].items()}
    if "oracle_json_path" in cfg:
        with open(cfg["oracle_json_path"], "r") as fh:
            data = json.load(fh)
        return {str(k): int(v) for k, v in data["counts"].items()}
    raise SystemExit("compare.py: provide 'expected' or 'oracle_json_path'")


def iter_output_files(path):
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                yield full
    elif os.path.isfile(path):
        yield path
    else:
        raise SystemExit("compare.py: output_path not found: %s" % path)


def load_output(path):
    got = {}
    for fpath in iter_output_files(path):
        with open(fpath, "r") as fh:
            for line in fh:
                m = LINE_RE.search(line)
                if not m:
                    continue
                job, cnt = m.group(1), int(m.group(2))
                got[job] = cnt  # last wins; duplicates flagged indirectly
    return got


def main():
    cfg = json.load(sys.stdin)
    expected = load_expected(cfg)
    got = load_output(cfg["output_path"])

    only_exp = sorted(set(expected) - set(got))
    only_got = sorted(set(got) - set(expected))
    mismatches = []
    for job in sorted(set(expected) & set(got)):
        if expected[job] != got[job]:
            mismatches.append([job, expected[job], got[job]])

    result = {
        "match": not only_exp and not only_got and not mismatches,
        "num_expected": len(expected),
        "num_output": len(got),
        "only_in_expected": only_exp[:50],
        "only_in_output": only_got[:50],
        "count_mismatches": mismatches[:50],
    }
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
