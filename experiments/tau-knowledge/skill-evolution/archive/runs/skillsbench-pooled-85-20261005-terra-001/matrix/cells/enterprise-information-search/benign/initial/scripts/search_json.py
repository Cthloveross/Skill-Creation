#!/usr/bin/env python3
"""Locate lexical evidence in arbitrary JSON exports; stdin/output are JSON objects."""
import ast, json, re, sys
from pathlib import Path

STOP = {"the","a","an","and","or","of","to","for","in","on","at","by","with","from","is","are","was","were","be","been","what","which","who","when","where","how","did","does","do","give","find","list","all","please","about","this","that","these","those","as","after","before","between","during","into","its","their","than","then"}

def parse_questions(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    for loader in (json.loads, ast.literal_eval):
        try:
            value = loader(text)
            if isinstance(value, dict): return {str(k): str(v) for k, v in value.items()}
        except Exception: pass
    found = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z][\w.-]*)\s*[:：]\s*(.+?)\s*$", line)
        if m: found[m.group(1)] = m.group(2)
    if found: return found
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return {f"q{i+1}": re.sub(r"^\d+[.)]\s*", "", line) for i, line in enumerate(lines)}

def terms(query):
    raw = re.findall(r"[A-Za-z0-9_@./:-]{2,}", query.lower())
    return sorted(set(x for x in raw if x not in STOP and not x.isdigit()), key=len, reverse=True)

def compact(value, cap=360):
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else: text = str(value)
    return re.sub(r"\s+", " ", text)[:cap]

def preview(mapping, cap):
    if not isinstance(mapping, dict): return None
    result = {}
    for k, v in mapping.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            result[str(k)] = compact(v, 160)
        if len(result) >= 18: break
    text = compact(result, cap)
    return text if text != "{}" else None

def walk(value, path, parent, file_rel, query_terms, hits, max_hits, cap, depth=0):
    if len(hits) >= max_hits or depth > 30: return
    if isinstance(value, dict):
        for k, child in value.items():
            walk(child, path + "." + str(k), value, file_rel, query_terms, hits, max_hits, cap, depth + 1)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            walk(child, path + f"[{i}]", parent, file_rel, query_terms, hits, max_hits, cap, depth + 1)
    else:
        text = compact(value, cap * 3)
        low = text.lower()
        matched = [t for t in query_terms if t in low]
        if matched:
            # Longer terms and multiple independent terms rank above generic word hits.
            score = sum(min(len(t), 20) for t in matched) + 8 * (len(matched) - 1)
            hits.append({"file": file_rel, "path": path, "score": score,
                         "matched_terms": matched, "value": text[:cap],
                         "record_preview": preview(parent, cap)})

def main():
    req = json.load(sys.stdin)
    root = Path(req.get("root", "/root/DATA"))
    queries = req.get("queries") or req.get("questions")
    if queries is None and req.get("question_path"):
        queries = parse_questions(req["question_path"])
    if not isinstance(queries, dict):
        raise SystemExit("Provide queries/questions mapping or question_path")
    max_hits = int(req.get("max_hits_per_question", 80))
    cap = int(req.get("max_preview_chars", 420))
    output, errors = {}, []
    files = sorted(root.rglob("*.json")) if root.is_dir() else []
    if not files: errors.append("No JSON files found under root")
    for key, query in queries.items():
        qterms = terms(str(query))
        hits = []
        for fp in files:
            if len(hits) >= max_hits: break
            try:
                with fp.open(encoding="utf-8") as f: data = json.load(f)
                walk(data, "$", None, str(fp.relative_to(root)), qterms, hits, max_hits, cap)
            except Exception as exc:
                errors.append(f"{fp}: {type(exc).__name__}: {exc}")
        hits.sort(key=lambda x: (-x["score"], x["file"], x["path"]))
        output[str(key)] = hits
    print(json.dumps({"queries": {str(k): str(v) for k, v in queries.items()}, "results": output,
                      "errors": errors}, ensure_ascii=False))
if __name__ == "__main__": main()
