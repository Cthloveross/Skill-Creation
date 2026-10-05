#!/usr/bin/env python3
"""Network-assisted BibTeX integrity triage.

Reads JSON from stdin; see SKILL.md for the input and output schemas.  Uses only
Python's standard library so it can run in a minimal task runtime.
"""
import difflib
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen

USER_AGENT = "citation-integrity-verifier/1.0 (bibliography validation)"


def request_json(url, timeout):
    """Return (HTTP status, decoded object or None), preserving API failures."""
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(raw)
            except json.JSONDecodeError:
                return response.status, None
    except HTTPError as exc:
        return exc.code, None
    except (URLError, TimeoutError, OSError):
        return None, None


def doi_resolution_status(doi, timeout):
    """Check DOI resolution without following redirects, preserving 3xx as success."""
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    request = Request("https://doi.org/" + quote(doi, safe="/"), headers={"User-Agent": USER_AGENT})
    try:
        opener = build_opener(NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except HTTPError as exc:
        return exc.code
    except (URLError, TimeoutError, OSError):
        return None


def balanced_end(text, start, opener="{", closer="}"):
    depth = 0
    escaped = False
    in_quote = False
    for pos in range(start, len(text)):
        char = text[pos]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return pos
    return None


def parse_fields(body):
    """Parse common BibTeX field assignments from the contents of one entry."""
    first_comma = body.find(",")
    if first_comma < 0:
        return None, {}
    key = body[:first_comma].strip()
    fields = {}
    i = first_comma + 1
    length = len(body)
    while i < length:
        while i < length and (body[i].isspace() or body[i] == ","):
            i += 1
        match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[i:])
        if not match:
            i += 1
            continue
        field = match.group(1).lower()
        i += match.end()
        if i >= length:
            break
        if body[i] == "{":
            end = balanced_end(body, i)
            if end is None:
                value = body[i + 1:].strip()
                i = length
            else:
                value = body[i + 1:end]
                i = end + 1
        elif body[i] == '"':
            i += 1
            chars = []
            escaped = False
            while i < length:
                ch = body[i]
                if not escaped and ch == '"':
                    i += 1
                    break
                chars.append(ch)
                if ch == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
                i += 1
            value = "".join(chars)
        else:
            end = body.find(",", i)
            if end < 0:
                value, i = body[i:].strip(), length
            else:
                value, i = body[i:end].strip(), end
        fields[field] = value.strip()
    return key, fields


def parse_bibtex(text):
    entries = []
    i = 0
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        type_match = re.match(r"@\s*([A-Za-z]+)\s*([\{\(])", text[at:])
        if not type_match:
            i = at + 1
            continue
        entry_type = type_match.group(1).lower()
        opening = type_match.group(2)
        closing = "}" if opening == "{" else ")"
        body_start = at + type_match.end() - 1
        body_end = balanced_end(text, body_start, opening, closing)
        if body_end is None:
            i = body_start + 1
            continue
        if entry_type not in ("comment", "preamble", "string"):
            key, fields = parse_fields(text[body_start + 1:body_end])
            if key:
                entries.append({"key": key, "entry_type": entry_type, "fields": fields})
        i = body_end + 1
    return entries


def clean_title(value):
    """Remove common LaTeX/BibTeX markup while retaining the visible text."""
    if not value:
        return ""
    value = re.sub(r"\\(?:url|href)\s*\{([^}]*)\}(?:\{[^}]*\})?", r"\1", value)
    value = value.replace("~", " ")
    value = re.sub(r"\\&", "and", value)
    value = re.sub(r"\\([#$%_{}])", r"\1", value)
    # Remove command names, leaving their braced argument in place. This also
    # turns accent forms such as \\'{e} into e after braces are stripped.
    value = re.sub(r"\\[A-Za-z]+\*?\s*", "", value)
    value = re.sub(r"\\[^A-Za-z\s]", "", value)
    value = value.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", value).strip()


def normalized(value):
    value = clean_title(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def title_similarity(left, right):
    left_n, right_n = normalized(left), normalized(right)
    if not left_n or not right_n:
        return 0.0
    sequence = difflib.SequenceMatcher(None, left_n, right_n).ratio()
    a, b = set(left_n.split()), set(right_n.split())
    jaccard = len(a & b) / len(a | b) if (a or b) else 0.0
    return max(sequence, jaccard, (sequence + jaccard) / 2)


def strong_title_match(left, right):
    left_n, right_n = normalized(left), normalized(right)
    if not left_n or not right_n:
        return False
    sequence = difflib.SequenceMatcher(None, left_n, right_n).ratio()
    a, b = set(left_n.split()), set(right_n.split())
    jaccard = len(a & b) / len(a | b) if (a or b) else 0.0
    return sequence >= 0.92 or (sequence >= 0.75 and jaccard >= 0.86)


def extract_doi(fields):
    for field in ("doi", "url"):
        match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", fields.get(field, ""), re.I)
        if match:
            return match.group(0).rstrip(".,;)").lower()
    return None


def doi_metadata(doi, timeout):
    encoded = quote(doi, safe="")
    cr_status, cr_data = request_json("https://api.crossref.org/works/" + encoded, timeout)
    dc_status, dc_data = request_json("https://api.datacite.org/dois/" + encoded, timeout)
    titles = []
    if cr_status == 200 and isinstance(cr_data, dict):
        message = cr_data.get("message", {})
        titles.extend(message.get("title", []) if isinstance(message.get("title"), list) else [])
    if dc_status == 200 and isinstance(dc_data, dict):
        attributes = dc_data.get("data", {}).get("attributes", {})
        for title in attributes.get("titles", []) or []:
            if isinstance(title, dict) and title.get("title"):
                titles.append(title["title"])
    return {"crossref_status": cr_status, "datacite_status": dc_status,
            "resolution_status": doi_resolution_status(doi, timeout), "titles": titles}


def search_titles(title, timeout):
    query = quote(title)
    sources = {}
    cr_status, cr_data = request_json("https://api.crossref.org/works?" + urlencode({"query.title": title, "rows": 5}), timeout)
    cr_titles = []
    if cr_status == 200 and isinstance(cr_data, dict):
        for item in cr_data.get("message", {}).get("items", []) or []:
            cr_titles.extend(item.get("title", []) or [])
    sources["crossref"] = {"status": cr_status, "titles": cr_titles}

    oa_status, oa_data = request_json("https://api.openalex.org/works?" + urlencode({"search": title, "per-page": 5}), timeout)
    oa_titles = []
    if oa_status == 200 and isinstance(oa_data, dict):
        oa_titles = [x.get("display_name", "") for x in oa_data.get("results", []) or []]
    sources["openalex"] = {"status": oa_status, "titles": oa_titles}

    ss_status, ss_data = request_json("https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode({"query": title, "limit": 5, "fields": "title"}), timeout)
    ss_titles = []
    if ss_status == 200 and isinstance(ss_data, dict):
        ss_titles = [x.get("title", "") for x in ss_data.get("data", []) or []]
    sources["semantic_scholar"] = {"status": ss_status, "titles": ss_titles}
    return sources


def brief_candidates(titles, title):
    ranked = sorted(((title_similarity(title, item), clean_title(item)) for item in titles if item), reverse=True)
    return [{"title": item, "similarity": round(score, 3)} for score, item in ranked[:3]]


def classify(entry, timeout):
    fields = entry["fields"]
    title = clean_title(fields.get("title", ""))
    record = {"key": entry["key"], "entry_type": entry["entry_type"], "title": title,
              "doi": extract_doi(fields), "classification": "needs_review", "reasons": [], "evidence": {}}
    if not title:
        record["classification"] = "needs_review"
        record["reasons"].append("missing_title")
        return record
    doi = record["doi"]
    if doi:
        evidence = doi_metadata(doi, timeout)
        record["evidence"]["doi"] = evidence
        registry_titles = evidence["titles"]
        if registry_titles:
            record["evidence"]["doi"]["title_candidates"] = brief_candidates(registry_titles, title)
            if any(strong_title_match(title, candidate) for candidate in registry_titles):
                record["classification"] = "verified"
                record["reasons"].append("doi_registry_title_match")
            else:
                record["classification"] = "likely_fake"
                record["reasons"].append("doi_registry_title_mismatch")
        elif (evidence["crossref_status"] == 404 and evidence["datacite_status"] == 404
              and (evidence["resolution_status"] is None or evidence["resolution_status"] >= 400)):
            record["classification"] = "likely_fake"
            record["reasons"].append("doi_absent_from_registries_and_unresolvable")
        else:
            record["reasons"].append("doi_inconclusive_or_network_failure")
        return record

    searches = search_titles(title, timeout)
    record["evidence"]["title_search"] = {}
    any_match = False
    successful = 0
    for source, result in searches.items():
        candidates = result["titles"]
        if result["status"] == 200:
            successful += 1
        matched = any(strong_title_match(title, candidate) for candidate in candidates)
        any_match = any_match or matched
        record["evidence"]["title_search"][source] = {"status": result["status"], "match": matched,
                                                          "candidates": brief_candidates(candidates, title)}
    if any_match:
        record["classification"] = "verified"
        record["reasons"].append("title_found_in_scholarly_index")
    elif successful == 3 and entry["entry_type"] in {"article", "inproceedings", "incollection"}:
        record["classification"] = "likely_fake"
        record["reasons"].append("absent_from_three_scholarly_indexes")
    else:
        record["reasons"].append("insufficient_index_coverage_for_conclusion")
    return record


def main():
    config = json.load(sys.stdin)
    bib_path = Path(config["bib_path"])
    answer_path = Path(config.get("answer_path", "answer.json"))
    audit_path = Path(config.get("audit_path", "citation_audit.json"))
    timeout = float(config.get("timeout_sec", 15))
    if timeout <= 0:
        raise ValueError("timeout_sec must be positive")
    entries = parse_bibtex(bib_path.read_text(encoding="utf-8", errors="replace"))
    if not entries:
        raise ValueError("No parseable BibTeX entries found")
    records = []
    for entry in entries:
        records.append(classify(entry, timeout))
        time.sleep(0.08)  # modest pacing for public scholarly APIs
    fake_titles = sorted({r["title"] for r in records if r["classification"] == "likely_fake"}, key=str.casefold)
    answer = {"fake_citations": fake_titles}
    # Validate the exact required artifact shape before writing it.
    if set(answer) != {"fake_citations"} or not all(isinstance(x, str) for x in fake_titles):
        raise ValueError("internal answer schema validation failed")
    answer_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    answer_path.write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_path.write_text(json.dumps({"entries": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"answer_path": str(answer_path), "audit_path": str(audit_path), "entries_parsed": len(entries),
               "fake_count": len(fake_titles), "needs_review_count": sum(r["classification"] == "needs_review" for r in records)}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
