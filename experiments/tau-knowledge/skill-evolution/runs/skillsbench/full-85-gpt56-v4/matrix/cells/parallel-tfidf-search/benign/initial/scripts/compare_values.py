#!/usr/bin/env python3
"""Compare JSON values deeply with an optional absolute float tolerance.

Input JSON: {"left": "path.json", "right": "path.json", "float_tolerance": 0.0}
Output JSON: {"equal": bool, "difference": null|{path, left, right}}
"""
import json
import math
import sys
from pathlib import Path


def first_difference(left, right, tolerance, path="$"):
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        if isinstance(left, float) and isinstance(right, float) and math.isnan(left) and math.isnan(right):
            return None
        if abs(left - right) <= tolerance:
            return None
        return {"path": path, "left": left, "right": right}
    if type(left) is not type(right):
        return {"path": path, "left": left, "right": right}
    if isinstance(left, dict):
        if list(left.keys()) != list(right.keys()):
            return {"path": path + ".keys", "left": list(left.keys()), "right": list(right.keys())}
        for key in left:
            result = first_difference(left[key], right[key], tolerance, path + "[" + repr(key) + "]")
            if result:
                return result
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return {"path": path + ".length", "left": len(left), "right": len(right)}
        for index, (a, b) in enumerate(zip(left, right)):
            result = first_difference(a, b, tolerance, path + "[" + str(index) + "]")
            if result:
                return result
        return None
    if left != right:
        return {"path": path, "left": left, "right": right}
    return None


def main():
    request = json.load(sys.stdin)
    tolerance = float(request.get("float_tolerance", 0.0))
    if tolerance < 0:
        raise ValueError("float_tolerance must be non-negative")
    left = json.loads(Path(request["left"]).read_text(encoding="utf-8"))
    right = json.loads(Path(request["right"]).read_text(encoding="utf-8"))
    difference = first_difference(left, right, tolerance)
    print(json.dumps({"equal": difference is None, "difference": difference}, sort_keys=True))


if __name__ == "__main__":
    main()
