#!/usr/bin/env python3
"""Search runtime JSON corpora with record-level context.
Input: {data_root, queries:[{id,terms,logic?}], max_hits_per_query?, preview_chars?,
        include_root_records?}. Output contains matching record paths and leaf evidence.
"""
import json
import sys
from pathlib import Path


def scalar_text(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def leaves(value, path=()):
    text = scalar_text(value)
    if text is not None:
        yield list(path), text
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, path + (index,))


def list_records(value, path=()):
    """Yield object/array entries of every array as useful local record boundaries."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from list_records(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = path + (index,)
            if isinstance(child, (dict, list)):
                yield list(child_path), child
            yield from list_records(child, child_path)


def is_match(blob, terms, logic):
    present = [term.casefold() in blob for term in terms]
    return all(present) if logic == "all" else any(present)


def preview(value, max_chars):
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[:max_chars] + "… [truncated]"


def search_value(value, file_name, query, max_hits, preview_chars, include_root):
    terms = [str(t).casefold() for t in query["terms"] if str(t)]
    logic = query.get("logic", "all")
    candidates = list(list_records(value))
    if include_root or not candidates:
        candidates.append(([], value))
    hits = []
    seen = set()
    for record_path, record in candidates:
        path_key = tuple(record_path)
        if path_key in seen:
            continue
        seen.add(path_key)
        # Use scalar values, rather than only the preview, for matching.
        record_leaves = list(leaves(record))
        blob = "\n".join(text.casefold() for _, text in record_leaves)
        if not is_match(blob, terms, logic):
            continue
        matching = []
        occurrences = 0
        for leaf_path, text in record_leaves:
            lower = text.casefold()
            matched_terms = [term for term in terms if term in lower]
            if matched_terms:
                occurrences += len(matched_terms)
                matching.append({"path": leaf_path, "value": text[:1000], "terms": matched_terms})
                if len(matching) >= 20:
                    break
        # Prefer small, deeply nested records: they are generally more specific evidence.
        score = occurrences * 100 + len(record_path)
        hits.append({
            "file": file_name,
            "record_path": record_path,
            "matched_leaves": matching,
            "preview": preview(record, preview_chars),
            "_score": score,
        })
    hits.sort(key=lambda item: (-item["_score"], item["file"], str(item["record_path"])))
    for hit in hits[:max_hits]:
        hit.pop("_score", None)
    return hits[:max_hits]


def main():
    request = json.load(sys.stdin)
    root = Path(request["data_root"])
    queries = request.get("queries", [])
    if not root.is_dir():
        raise ValueError("data_root must be an existing directory")
    if not isinstance(queries, list) or not queries:
        raise ValueError("queries must be a nonempty array")
    max_hits = max(1, int(request.get("max_hits_per_query", 30)))
    preview_chars = max(200, int(request.get("preview_chars", 2500)))
    include_root = bool(request.get("include_root_records", False))
    normalized = []
    for query in queries:
        if not isinstance(query, dict) or not query.get("id"):
            raise ValueError("each query needs a nonempty id")
        terms = query.get("terms")
        if not isinstance(terms, list) or not any(str(t) for t in terms):
            raise ValueError("each query needs nonempty terms")
        if query.get("logic", "all") not in ("all", "any"):
            raise ValueError("logic must be all or any")
        normalized.append(query)
    results = {str(query["id"]): [] for query in normalized}
    errors = []
    for file_path in sorted(root.rglob("*.json")):
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            for query in normalized:
                results[str(query["id"])].extend(
                    search_value(value, str(file_path), query, max_hits, preview_chars, include_root)
                )
        except Exception as exc:
            errors.append({"file": str(file_path), "error": str(exc)})
    # Enforce the requested global cap after merging all files.
    for query in normalized:
        key = str(query["id"])
        results[key] = results[key][:max_hits]
    print(json.dumps({"results": results, "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
