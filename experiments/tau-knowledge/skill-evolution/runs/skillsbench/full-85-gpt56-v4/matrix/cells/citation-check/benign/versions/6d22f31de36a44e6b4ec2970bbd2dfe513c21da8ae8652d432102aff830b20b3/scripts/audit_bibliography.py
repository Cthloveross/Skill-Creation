#!/usr/bin/env python3
"""Audit BibTeX citations using public bibliographic registries.

Reads one JSON object from stdin and emits an execution summary JSON to stdout.
See SKILL.md for the input and output schema.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

UA = "bibtex-citation-audit/1.0 (metadata verification)"


def read_balanced(text, pos, opener="{", closer="}"):
    """Return contents and position after a balanced braced BibTeX section."""
    if pos >= len(text) or text[pos] != opener:
        return "", pos
    depth, quote, escaped = 0, False, False
    start = pos + 1
    for i in range(pos, len(text)):
        ch = text[i]
        if quote:
            if ch == '"' and not escaped:
                quote = False
            escaped = (ch == "\\" and not escaped)
            continue
        if ch == '"':
            quote = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
    return text[start:], len(text)


def split_top_level(value):
    parts, start, depth, quote, escaped = [], 0, 0, False, False
    for i, ch in enumerate(value):
        if quote:
            if ch == '"' and not escaped:
                quote = False
            escaped = (ch == "\\" and not escaped)
            continue
        if ch == '"':
            quote = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append(value[start:i])
            start = i + 1
    parts.append(value[start:])
    return parts


def unquote_bib_value(value):
    value = value.strip().rstrip(",").strip()
    while len(value) >= 2 and value[0] == "{" and value[-1] == "}":
        inner, end = read_balanced(value, 0)
        if end != len(value):
            break
        value = inner.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    return value.strip()


def parse_bibtex(text):
    entries, cursor = [], 0
    head = re.compile(r"@(\w+)\s*\{")
    while True:
        m = head.search(text, cursor)
        if not m:
            break
        body, cursor = read_balanced(text, m.end() - 1)
        if m.group(1).lower() in {"comment", "preamble", "string"}:
            continue
        chunks = split_top_level(body)
        if not chunks:
            continue
        key = chunks[0].strip()
        fields = {}
        for chunk in chunks[1:]:
            if "=" not in chunk:
                continue
            name, raw = chunk.split("=", 1)
            name = name.strip().lower()
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
                fields[name] = unquote_bib_value(raw)
        if key:
            entries.append({"key": key, "type": m.group(1).lower(), "fields": fields})
    return entries


def clean_title(value):
    """Make a display/search title without common BibTeX LaTeX markup."""
    value = value or ""
    # Common accent command forms; retain their printable letter.
    value = re.sub(r"\\(?:textit|textbf|emph|mathrm|mathbf|textrm|url)\s*\{([^{}]*)\}", r"\1", value)
    value = re.sub(r'\\(?:["\'`^~=.uvHcdbkr])\s*\{?([A-Za-z])\}?', r'\1', value)
    value = re.sub(r"\\[A-Za-z]+\*?\s*", "", value)
    value = value.replace("\\&", "&").replace("\\_", "_").replace("\\%", "%")
    value = value.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"\s+", " ", value).strip()


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean_title(str(value)).lower()).strip()


def title_score(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    aa, bb = set(a.split()), set(b.split())
    jac = len(aa & bb) / max(1, len(aa | bb))
    if a in b or b in a:
        return max(seq, 0.92)
    return max(seq, jac)


def surname_set(author_value):
    result = set()
    for person in re.split(r"\s+and\s+", author_value or "", flags=re.I):
        person = re.sub(r"[{}]", "", person).strip()
        if not person:
            continue
        if "," in person:
            last = person.split(",", 1)[0]
        else:
            last = person.split()[-1] if person.split() else ""
        x = norm(last)
        if x:
            result.add(x)
    return result


def http_json(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return {"outcome": "ok", "http_status": response.status, "data": json.loads(raw)}
    except urllib.error.HTTPError as exc:
        return {"outcome": "not_found" if exc.code == 404 else "http_error", "http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"outcome": "error", "error": str(exc)}


def crossref_doi(doi, timeout):
    u = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    r = http_json(u, timeout)
    if r["outcome"] == "ok":
        r["record"] = r["data"].get("message", {})
    return r


def datacite_doi(doi, timeout):
    u = "https://api.datacite.org/dois/" + urllib.parse.quote(doi, safe="")
    r = http_json(u, timeout)
    if r["outcome"] == "ok":
        r["record"] = r["data"].get("data", {}).get("attributes", {})
    return r


def crossref_title(title, timeout):
    u = "https://api.crossref.org/works?rows=5&query.title=" + urllib.parse.quote(title)
    r = http_json(u, timeout)
    if r["outcome"] == "ok":
        r["records"] = r["data"].get("message", {}).get("items", [])
    return r


def semantic_title(title, timeout):
    u = ("https://api.semanticscholar.org/graph/v1/paper/search?limit=5&fields=title,year,venue,authors"
         "&query=" + urllib.parse.quote(title))
    r = http_json(u, timeout)
    if r["outcome"] == "ok":
        r["records"] = r["data"].get("data", [])
    return r


def dblp_title(title, timeout):
    u = "https://dblp.org/search/publ/api?format=json&h=5&q=" + urllib.parse.quote(title)
    r = http_json(u, timeout)
    if r["outcome"] == "ok":
        hits = r["data"].get("result", {}).get("hits", {}).get("hit", [])
        r["records"] = hits if isinstance(hits, list) else [hits]
    return r


def record_title(record, source):
    if source == "datacite":
        titles = record.get("titles", [])
        return titles[0].get("title", "") if titles else ""
    if source == "dblp":
        return record.get("info", {}).get("title", "")
    title = record.get("title", "")
    return title[0] if isinstance(title, list) and title else title


def metadata_summary(record, source):
    if source == "datacite":
        return {"title": record_title(record, source), "year": record.get("publicationYear"),
                "venue": record.get("publisher"), "volume": None, "pages": None}
    if source == "crossref":
        date = (record.get("published-print") or record.get("published-online") or record.get("issued") or {})
        year = (date.get("date-parts", [[None]])[0][0] if date else None)
        venue = (record.get("container-title") or [""])[0]
    else:
        year, venue = record.get("year"), record.get("venue", "")
    return {"title": record_title(record, source), "year": year, "venue": venue,
            "volume": record.get("volume"), "pages": record.get("page")}


def compact_response(response, source=None):
    out = {k: response[k] for k in ("outcome", "http_status", "error") if k in response}
    records = [response["record"]] if "record" in response else response.get("records", [])
    if records:
        out["top_matches"] = [metadata_summary(x, source) for x in records[:3]]
    return out


def best_match(records, title, source):
    if not records:
        return 0.0, None
    ranked = [(title_score(title, record_title(x, source)), x) for x in records]
    return max(ranked, key=lambda x: x[0])


def record_author_surnames(record, source):
    """Return normalized author surnames from the supported registry schemas."""
    if source == "datacite":
        names = [x.get("familyName") or x.get("name", "") for x in record.get("creators", [])]
    elif source == "dblp":
        raw_names = record.get("info", {}).get("authors", {}).get("author", [])
        if not isinstance(raw_names, list):
            raw_names = [raw_names]
        names = [x.get("text", "") if isinstance(x, dict) else str(x) for x in raw_names]
    else:
        names = [x.get("family", "") or x.get("name", "") for x in record.get("authors", [])]
        if source == "crossref":
            names = [x.get("family", "") or x.get("name", "") for x in record.get("author", [])]
    return {norm(name) for name in names if norm(name)}


def venue_matches(expected, observed):
    """Conservative venue comparison; abbreviations alone are not a match."""
    a, b = set(norm(expected).split()), set(norm(observed).split())
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.6


def exact_normalized_title(a, b):
    return bool(norm(a) and norm(a) == norm(b))


def doi_metadata_comparison(fields, record, source):
    """Report comparable fields without treating harmless export variations as proof."""
    remote = metadata_summary(record, source)
    expected_authors = surname_set(fields.get("author", ""))
    observed_authors = record_author_surnames(record, source)
    expected_venue = fields.get("journal") or fields.get("booktitle") or ""
    expected_year = re.search(r"\d{4}", str(fields.get("year", "")))
    observed_year = re.search(r"\d{4}", str(remote.get("year", "")))
    def same_pages(a, b):
        return norm(str(a)).replace(" ", "") == norm(str(b)).replace(" ", "")
    return {
        "title_score": round(title_score(clean_title(fields.get("title", "")), remote.get("title", "")), 3),
        "author_overlap": (bool(expected_authors & observed_authors) if expected_authors and observed_authors else None),
        "venue_agreement": (venue_matches(expected_venue, remote.get("venue", ""))
                            if expected_venue and remote.get("venue") else None),
        "year_agreement": (expected_year.group(0) == observed_year.group(0)
                           if expected_year and observed_year else None),
        "volume_agreement": (str(fields.get("volume")) == str(remote.get("volume"))
                             if fields.get("volume") and remote.get("volume") else None),
        "pages_agreement": (same_pages(fields.get("pages"), remote.get("pages"))
                           if fields.get("pages") and remote.get("pages") else None),
    }


def assess(entry, timeout, override):
    fields = entry["fields"]
    title = clean_title(fields.get("title", ""))
    audit = {"key": entry["key"], "entry_type": entry["type"], "clean_title": title,
             "doi": fields.get("doi", "").strip(), "status": "unverified", "sources": {}, "notes": []}
    if not title:
        audit["status"] = "unverified"
        audit["notes"].append("No usable title field; cannot produce a title answer.")
        return audit
    doi = audit["doi"].replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if doi:
        cr = crossref_doi(doi, timeout)
        audit["sources"]["crossref_doi"] = compact_response(cr, "crossref")
        dc = None
        source, response = "crossref", cr
        if cr["outcome"] == "not_found":
            dc = datacite_doi(doi, timeout)
            audit["sources"]["datacite_doi"] = compact_response(dc, "datacite")
            if dc["outcome"] == "ok":
                source, response = "datacite", dc
        if response["outcome"] == "ok":
            remote_title = record_title(response["record"], source)
            score = title_score(title, remote_title)
            audit["doi_title_score"] = round(score, 3)
            audit["doi_metadata"] = metadata_summary(response["record"], source)
            audit["doi_comparison"] = doi_metadata_comparison(fields, response["record"], source)
            if score >= 0.78:
                audit["status"] = "real"
                audit["notes"].append("DOI resolves and title substantially matches registry metadata.")
            elif score < 0.45:
                audit["status"] = "fake"
                audit["notes"].append("DOI resolves to a radically different work.")
            else:
                audit["status"] = "mismatched_doi"
                audit["notes"].append("DOI resolves but title is only a partial match; review for transcription error.")
        elif cr["outcome"] == "not_found" and dc is not None and dc["outcome"] == "not_found":
            audit["status"] = "fake"
            audit["notes"].append("DOI is absent from both Crossref and DataCite registries.")
        else:
            audit["notes"].append("DOI registry lookup was inconclusive because of a source error.")
    # Search non-verified citations, including mismatched DOI records for corroboration.
    if audit["status"] != "real":
        searches = [("crossref_title", crossref_title, "crossref"), ("semantic_scholar", semantic_title, "semantic"),
                    ("dblp", dblp_title, "dblp")]
        exact_match = False
        crossref_records = []
        for label, func, source in searches:
            r = func(title, timeout)
            audit["sources"][label] = compact_response(r, source)
            if r["outcome"] == "ok":
                records = r.get("records", [])
                score, _ = best_match(records, title, source)
                audit["sources"][label]["best_title_score"] = round(score, 3)
                exact_match = exact_match or any(exact_normalized_title(title, record_title(x, source)) for x in records)
                if source == "crossref":
                    crossref_records = records
            time.sleep(0.15)
        if audit["status"] == "unverified" and exact_match:
            audit["status"] = "likely_real"
            audit["notes"].append("A title index has an exact normalized title match.")
        elif audit["status"] == "unverified":
            # A generic, similar title is not corroboration.  It becomes affirmative
            # contradiction only when a healthy registry returns several different
            # works and none agrees with the supplied authors or venue.
            expected_authors = surname_set(fields.get("author", ""))
            expected_venue = fields.get("journal") or fields.get("booktitle") or ""
            candidates_with_authors = [x for x in crossref_records if record_author_surnames(x, "crossref")]
            candidates_with_venue = [x for x in crossref_records if metadata_summary(x, "crossref").get("venue")]
            author_agrees = any(expected_authors & record_author_surnames(x, "crossref") for x in crossref_records)
            venue_agrees = any(venue_matches(expected_venue, metadata_summary(x, "crossref").get("venue", ""))
                                for x in crossref_records)
            if (not doi and len(crossref_records) >= 3 and expected_authors and expected_venue
                    and len(candidates_with_authors) >= 3 and len(candidates_with_venue) >= 3
                    and not author_agrees and not venue_agrees):
                audit["status"] = "fake"
                audit["notes"].append("Registry search returned only differently authored and differently venued works; no exact title record supports this citation.")
            else:
                audit["notes"].append("No exact indexed title match; absence alone is not proof of fabrication.")
    if override in {"fake", "real", "unverified"}:
        audit["status"] = override
        audit["notes"].append("Status set by explicit manual override.")
    return audit


def validate_answer(answer):
    if set(answer) != {"fake_citations"} or not isinstance(answer["fake_citations"], list):
        raise ValueError("answer schema is invalid")
    titles = answer["fake_citations"]
    if any(not isinstance(x, str) or "{" in x or "}" in x or "\\" in x for x in titles):
        raise ValueError("answer contains an unclean title")
    if titles != sorted(titles) or len(titles) != len(set(titles)):
        raise ValueError("answer titles are not sorted unique strings")


def main():
    config = json.load(sys.stdin)
    bib_path = Path(config["bib_path"])
    output_path = Path(config["output_path"])
    audit_path = Path(config.get("audit_path", str(output_path.with_suffix(".audit.json"))))
    timeout = float(config.get("timeout_seconds", 15))
    overrides = config.get("manual_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("manual_overrides must be an object")
    entries = parse_bibtex(bib_path.read_text(encoding="utf-8", errors="replace"))
    audits = [assess(entry, timeout, overrides.get(entry["key"])) for entry in entries]
    fake_titles = sorted(set(a["clean_title"] for a in audits if a["status"] == "fake" and a["clean_title"]))
    answer = {"fake_citations": fake_titles}
    validate_answer(answer)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_path.write_text(json.dumps({"entries": audits}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {}
    for audit in audits:
        counts[audit["status"]] = counts.get(audit["status"], 0) + 1
    print(json.dumps({"entries_parsed": len(entries), "status_counts": counts,
                      "answer_path": str(output_path), "audit_path": str(audit_path)}))


if __name__ == "__main__":
    main()
