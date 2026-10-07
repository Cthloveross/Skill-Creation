#!/usr/bin/env python3
"""End-to-end entrypoint for the enterprise-information-search task.

Reads /root/question.txt (keyed questions q1, q2, ...) and the /root/DATA tree,
classifies each question into a supported retrieval intent, derives the answer
from the data (nothing hardcoded), and writes /root/answer.json in the required
contract: {"qN": {"answer": [...], "tokens": "..."}}.

Usage:
  python3 scripts/run.py                      # default paths
  echo '{"question_file":"/root/question.txt","data_dir":"/root/DATA",
         "out":"/root/answer.json","tokens":"0"}' | python3 scripts/run.py

It prints a JSON report of what it did per question so the executor can review
and, for any question marked "unsupported", fall back to inspect.py/search.py
and the retrieve.py ops documented in SKILL.md.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retrieve  # packaged helper


def parse_questions(text):
    """Return list of (key, question_text). Handles 'qN": ...' lines and
    'qN: ...' / 'qN) ...' forms, tolerating trailing commas/quotes."""
    qs = []
    # match q<number> followed by : or ) then the rest up to end of line
    for m in re.finditer(r'(?mi)^\s*"?\b(q\d+)\b"?\s*[:)]\s*(.+?)\s*,?\s*$', text):
        key = m.group(1).lower()
        val = m.group(2).strip().strip('"').strip()
        qs.append((key, val))
    if not qs:
        # fallback: split on q<number>
        for m in re.finditer(r'(?i)(q\d+)\s*[:)]\s*([^\n]+)', text):
            qs.append((m.group(1).lower(), m.group(2).strip().strip('",')))
    # dedupe preserving order
    seen, out = set(), []
    for k, v in qs:
        if k not in seen:
            seen.add(k); out.append((k, v))
    return out


def list_products(data_dir):
    pdir = os.path.join(data_dir, 'products')
    prods = {}
    if os.path.isdir(pdir):
        for fn in os.listdir(pdir):
            if fn.endswith('.json'):
                prods[fn[:-5]] = os.path.join(pdir, fn)
    return prods


def find_product(qtext, prods):
    """Match a product by its file stem appearing in the question (case-insens).
    Longest stem match wins to prefer e.g. 'CollaborationForce' over 'Force'."""
    ql = qtext.lower()
    best = None
    for stem, path in prods.items():
        if stem.lower() in ql:
            if best is None or len(stem) > len(best[0]):
                best = (stem, path)
    return best  # (stem, path) or None


def find_doc_type(qtext, product_file):
    """Pick the documents[].type whose text appears in the question."""
    try:
        d = retrieve.load(product_file)
    except Exception:
        return None
    ql = qtext.lower()
    types = []
    for doc in d.get('documents', []) or []:
        t = str(doc.get('type', '')).strip()
        if t and t not in types:
            types.append(t)
    best = None
    for t in types:
        if t.lower() in ql:
            if best is None or len(t) > len(best):
                best = t
    return best


def answer_question(qtext, prods):
    ql = qtext.lower()
    info = {"intent": None, "product": None}
    prod = find_product(qtext, prods)
    if prod:
        info["product"] = prod[0]

    # --- demo URLs for competitor products ---
    if ('demo' in ql and ('url' in ql or 'link' in ql)) and 'competitor' in ql:
        info["intent"] = "competitor_demos"
        if not prod:
            return [], info
        r = retrieve.competitor_demos(prod[1])
        urls = []
        for s in r.get("external_shared_demos", []):
            if s["url"] not in urls:
                urls.append(s["url"])
        if not urls:  # fall back to catalogued external demo urls
            for u in r.get("external_demo_urls", []):
                if u["link"] not in urls:
                    urls.append(u["link"])
        return urls, info

    # --- insights on competitor strengths/weaknesses ---
    if 'competitor' in ql and ('insight' in ql or 'strength' in ql or 'weakness' in ql):
        info["intent"] = "competitor_insights"
        if not prod:
            return [], info
        r = retrieve.competitor_insights(prod[1])
        return list(r.get("insight_providers", [])), info

    # --- authors and/or reviewers of a document ---
    if 'author' in ql or 'review' in ql:
        info["intent"] = "authors_reviewers"
        if not prod:
            return [], info
        dt = find_doc_type(qtext, prod[1])
        info["doc_type"] = dt
        if not dt:
            return [], info
        r = retrieve.authors_reviewers(prod[1], dt)
        out = []
        if 'author' in ql:
            out += r.get("authors", [])
        if 'review' in ql:
            out += r.get("reviewers", [])
        # dedupe preserving order
        seen, ded = set(), []
        for x in out:
            if x not in seen:
                seen.add(x); ded.append(x)
        return ded, info

    info["intent"] = "unsupported"
    return [], info


def main():
    req = {}
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            try:
                req = json.loads(data)
            except Exception:
                req = {}
    qfile = req.get("question_file", "/root/question.txt")
    data_dir = req.get("data_dir", "/root/DATA")
    out = req.get("out", "/root/answer.json")
    tokens = str(req.get("tokens", "0"))

    with open(qfile) as f:
        qtext = f.read()
    questions = parse_questions(qtext)
    prods = list_products(data_dir)

    answers, report = {}, []
    for key, text in questions:
        ans, info = answer_question(text, prods)
        answers[key] = {"answer": ans, "tokens": tokens}
        report.append({"key": key, "question": text, **info, "answer": ans})

    with open(out, "w") as f:
        json.dump(answers, f, indent=2)

    print(json.dumps({"written": out, "keys": list(answers), "report": report},
                     indent=2))


if __name__ == "__main__":
    main()
