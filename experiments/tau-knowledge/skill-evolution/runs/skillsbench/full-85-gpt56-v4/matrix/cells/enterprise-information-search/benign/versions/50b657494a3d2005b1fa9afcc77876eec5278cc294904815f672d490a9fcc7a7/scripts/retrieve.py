#!/usr/bin/env python3
"""Schema discovery, provenance-preserving lexical search, and JSON-pointer reads."""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@+\-]*")
STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "to",
    "was", "were", "what", "when", "which", "who", "with", "you", "that",
}

def fail(message):
    print(json.dumps({"error": message}, ensure_ascii=False))
    raise SystemExit(2)

def pointer_join(base, part):
    escaped = str(part).replace("~", "~0").replace("/", "~1")
    return base + "/" + escaped

def compact(value, depth=0, budget=1800):
    """Provide nearby, useful context without emitting a whole export."""
    if isinstance(value, str):
        return value[:budget] + ("…" if len(value) > budget else "")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if depth >= 2:
        if isinstance(value, list):
            return "[{} items]".format(len(value))
        if isinstance(value, dict):
            return "{{{} keys}}".format(len(value))
    if isinstance(value, list):
        return [compact(x, depth + 1, max(100, budget // 4)) for x in value[:8]]
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:20]:
            out[str(key)] = compact(item, depth + 1, max(100, budget // 5))
        return out
    return str(value)[:budget]

def json_files(root, contains=""):
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        fail("data_root is not a readable directory: " + str(root))
    needle = contains.casefold()
    files = []
    for path in root_path.rglob("*.json"):
        if needle and needle not in str(path).casefold():
            continue
        files.append(path)
    return sorted(files)

def load(path):
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"__load_error__": str(exc)}

def schema_walk(value, keys, types, limit, seen):
    if seen[0] >= limit:
        return
    seen[0] += 1
    types[type(value).__name__] += 1
    if isinstance(value, dict):
        for key, child in value.items():
            keys[str(key)] += 1
            schema_walk(child, keys, types, limit, seen)
    elif isinstance(value, list):
        for child in value:
            schema_walk(child, keys, types, limit, seen)

def discover(root):
    out = []
    for path in json_files(root):
        data = load(path)
        keys, types = Counter(), Counter()
        schema_walk(data, keys, types, 200000, [0])
        item = {
            "file": str(path),
            "top_level_type": type(data).__name__,
            "top_level_count": len(data) if isinstance(data, (dict, list)) else None,
            "common_keys": keys.most_common(50),
            "value_types": dict(types),
        }
        if isinstance(data, dict) and "__load_error__" in data:
            item["load_error"] = data["__load_error__"]
        out.append(item)
    return {"mode": "discover", "file_count": len(out), "files": out}

def query_terms(query):
    return [x.casefold() for x in WORD.findall(query) if x.casefold() not in STOP and len(x) > 1]

def score_text(text, terms, raw_query, path):
    folded = text.casefold()
    token_set = set(WORD.findall(folded))
    score = 0
    for term in terms:
        if term in token_set:
            score += 5
        elif term in folded:
            score += 2
        score += min(3, folded.count(term)) if len(term) >= 4 else 0
    if raw_query.casefold() in folded and len(raw_query.strip()) > 3:
        score += 12
    if any(term in path.casefold() for term in terms):
        score += 1
    return score

def leaves(value, pointer="", parent=None):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, pointer_join(pointer, key), value)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, pointer_join(pointer, index), value)
    elif isinstance(value, (str, int, float, bool)) and value is not None:
        yield pointer, str(value), parent

def search(root, query, maximum, contains):
    terms = query_terms(query)
    if not terms:
        fail("query has no searchable distinctive terms")
    results = []
    for path in json_files(root, contains):
        data = load(path)
        if isinstance(data, dict) and "__load_error__" in data:
            continue
        for pointer, text, parent in leaves(data):
            score = score_text(text, terms, query, pointer)
            if score:
                results.append({
                    "file": str(path), "pointer": pointer,
                    "matched_text": text[:1200] + ("…" if len(text) > 1200 else ""),
                    "score": score, "context": compact(parent),
                })
    results.sort(key=lambda x: (-x["score"], x["file"], x["pointer"]))
    return {
        "mode": "search", "query": query, "terms": terms,
        "result_count": len(results), "results": results[:maximum],
    }

def unescape(part):
    return part.replace("~1", "/").replace("~0", "~")

def at_pointer(value, pointer):
    if pointer in ("", "/"):
        return value
    if not pointer.startswith("/"):
        raise ValueError("pointer must be empty or start with /")
    current = value
    for raw in pointer[1:].split("/"):
        part = unescape(raw)
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError("cannot descend through " + type(current).__name__)
    return current

def get_value(request):
    filename = request.get("file")
    if not isinstance(filename, str):
        fail("get requires string file")
    path = Path(filename).resolve()
    root = request.get("data_root")
    if root:
        try:
            path.relative_to(Path(root).resolve())
        except ValueError:
            fail("requested file is outside data_root")
    data = load(path)
    try:
        value = at_pointer(data, request.get("pointer", ""))
    except (KeyError, ValueError, IndexError) as exc:
        fail("invalid pointer: " + str(exc))
    limit = request.get("max_chars")
    if isinstance(limit, int) and limit > 0:
        rendered = json.dumps(value, ensure_ascii=False)
        if len(rendered) > limit:
            return {"mode": "get", "file": str(path), "pointer": request.get("pointer", ""),
                    "truncated_json": rendered[:limit] + "…", "truncated": True}
    return {"mode": "get", "file": str(path), "pointer": request.get("pointer", ""), "value": value}

def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must be one JSON object: " + str(exc))
    if not isinstance(request, dict):
        fail("stdin JSON must be an object")
    mode = request.get("mode")
    if mode == "discover":
        result = discover(request.get("data_root", ""))
    elif mode == "search":
        query = request.get("query")
        if not isinstance(query, str):
            fail("search requires string query")
        maximum = request.get("max_results", 50)
        if not isinstance(maximum, int) or maximum < 1 or maximum > 1000:
            fail("max_results must be an integer from 1 to 1000")
        result = search(request.get("data_root", ""), query, maximum, request.get("file_contains", ""))
    elif mode == "get":
        result = get_value(request)
    else:
        fail("mode must be discover, search, or get")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

if __name__ == "__main__":
    main()
