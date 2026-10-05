#!/usr/bin/env python3
"""Read a JSON value at a path emitted by search_json.py.
Input: {file: str, path: [str|int], max_chars?: int}. Output has value when bounded,
otherwise a JSON preview. No field path conventions are assumed.
"""
import json
import sys
from pathlib import Path


def main():
    request = json.load(sys.stdin)
    file_path = Path(request["file"])
    path = request.get("path", [])
    if not file_path.is_file():
        raise ValueError("file must be an existing JSON file")
    if not isinstance(path, list):
        raise ValueError("path must be an array")
    with file_path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    for component in path:
        if isinstance(value, list):
            if not isinstance(component, int):
                raise ValueError("list path component must be an integer")
            value = value[component]
        elif isinstance(value, dict):
            if not isinstance(component, str):
                raise ValueError("object path component must be a string")
            value = value[component]
        else:
            raise ValueError("path continues beyond a scalar value")
    max_chars = max(100, int(request.get("max_chars", 30000)))
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    result = {"file": str(file_path), "path": path, "type": type(value).__name__}
    if len(rendered) <= max_chars:
        result["value"] = value
        result["truncated"] = False
    else:
        result["preview"] = rendered[:max_chars] + "… [truncated]"
        result["truncated"] = True
        result["serialized_chars"] = len(rendered)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
