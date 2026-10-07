#!/usr/bin/env python3
"""CSV manufacturing defect normalizer. Standard-library only.

stdin schema:
 {"events_path": str?, "codebook_paths": [str]|str?, "output_path": str?,
  "min_score": float?, "min_margin": float?}
stdout schema: {"output_path": str, "records": int, "segments": int,
                "assigned": int, "unknown": int}
"""
import csv
import difflib
import glob
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter


class InputError(ValueError):
    pass


def norm(value):
    """Retrieval representation only; never used as the reported source span."""
    s = unicodedata.normalize("NFKC", str(value or "")).casefold()
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def tokens(value):
    return [x for x in norm(value).split() if len(x) > 1 or not x.isascii()]


def grams(value, n=3):
    s = norm(value).replace(" ", "")
    if not s:
        return set()
    if len(s) < n:
        return {s}
    return {s[i:i+n] for i in range(len(s)-n+1)}


def read_csv(path):
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(8192)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            if not reader.fieldnames:
                raise InputError("CSV has no header: " + path)
            fields = [x.strip() for x in reader.fieldnames]
            rows = []
            for row in reader:
                rows.append({(k or "").strip(): (v or "") for k, v in row.items()})
            return fields, rows
    except OSError as e:
        raise InputError("Cannot read %s: %s" % (path, e))


def header_role(fields, role, required=True):
    # Exact semantic aliases take precedence; fuzzy header matching is intentionally avoided.
    aliases = {
        "record": ["record_id", "recordid", "log_id", "event_id", "id"],
        "product": ["product_id", "product", "productid", "model", "product_family"],
        "station": ["station", "test_station", "station_id", "test_stage", "stage"],
        "engineer": ["engineer_id", "engineer", "operator_id", "operator", "author"],
        "reason": ["raw_reason_text", "reason_text", "raw_reason", "defect_reason", "reason", "failure_reason", "comment", "notes"],
        "code": ["code", "defect_code", "fault_code", "standard_code", "error_code"],
        "label": ["label", "defect_label", "standard_label", "code_label", "fault_label", "name", "description"],
        "keywords": ["keywords", "keyword", "synonyms", "synonym", "aliases", "alias", "examples", "example", "terms", "term"],
        "scope_station": ["applicable_station", "applicable_stations", "station_scope", "stations", "station"],
        "scope_product": ["product_id", "product", "productid", "model", "product_family"],
    }
    canon = {f: re.sub(r"[^a-z0-9]+", "_", f.casefold()).strip("_") for f in fields}
    hits = [f for f, c in canon.items() if c in aliases[role]]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # Prefer exact order declared by aliases, but detect ties at that semantic priority.
        ranks = {a: i for i, a in enumerate(aliases[role])}
        best = min(ranks.get(canon[h], 999) for h in hits)
        winners = [h for h in hits if ranks.get(canon[h], 999) == best]
        if len(winners) == 1:
            return winners[0]
        raise InputError("Ambiguous %s columns: %s" % (role, ", ".join(hits)))
    if required:
        raise InputError("Missing %s column; found headers: %s" % (role, ", ".join(fields)))
    return None


def split_aliases(value):
    # Codebook aliases are fields, not evidence spans, so delimiter splitting is safe.
    parts = re.split(r"(?:\r?\n|[|;]|\s*/\s*|\s{2,})", str(value or ""))
    return [p.strip() for p in parts if norm(p.strip())]


def infer_file_product(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"^(codebook|defect[_-]?codebook)[_-]*", "", stem, flags=re.I)
    return stem


def resolve_codebook_paths(spec):
    if not spec:
        found = sorted(glob.glob("/app/data/codebook_*.csv"))
    elif isinstance(spec, str):
        found = sorted(glob.glob(os.path.join(spec, "*.csv"))) if os.path.isdir(spec) else [spec]
    else:
        found = list(spec)
    if not found:
        raise InputError("No codebook CSV files found")
    return found


def load_codebooks(paths):
    books = []
    for path in paths:
        fields, rows = read_csv(path)
        code_col = header_role(fields, "code")
        label_col = header_role(fields, "label")
        kw_col = header_role(fields, "keywords", required=False)
        product_col = header_role(fields, "scope_product", required=False)
        station_col = header_role(fields, "scope_station", required=False)
        entries = []
        for i, row in enumerate(rows, 2):
            code, label = row.get(code_col, "").strip(), row.get(label_col, "").strip()
            if not code or not label:
                raise InputError("Blank code or label in %s row %d" % (path, i))
            aliases = [label]
            if kw_col:
                aliases += split_aliases(row.get(kw_col, ""))
            # Remove duplicates while preserving label as the principal rendering.
            seen, clean = set(), []
            for a in aliases:
                n = norm(a)
                if n and n not in seen:
                    clean.append(a); seen.add(n)
            product = row.get(product_col, "").strip() if product_col else infer_file_product(path)
            stations = split_aliases(row.get(station_col, "")) if station_col else []
            entries.append({"code": code, "label": label, "aliases": clean,
                            "stations": stations, "source": os.path.basename(path)})
        if not entries:
            raise InputError("Codebook has no entries: " + path)
        declared = {norm(row.get(product_col, "")) for row in rows if product_col and norm(row.get(product_col, ""))}
        if len(declared) > 1:
            # A multi-product file is supported by making one book per declared product.
            for product in declared:
                subset = [e for e, r in zip(entries, rows) if norm(r.get(product_col, "")) == product]
                books.append((product, subset))
        else:
            key = next(iter(declared), norm(infer_file_product(path)))
            books.append((key, entries))
    return books


def product_entries(product, books):
    p = norm(product)
    exact = [entries for key, entries in books if key == p]
    if len(exact) == 1:
        return exact[0]
    # File names often include a family suffix not retained by the event export.
    compatible = [entries for key, entries in books if p and (p in key or key in p)]
    if len(compatible) == 1:
        return compatible[0]
    if not compatible:
        raise InputError("No applicable codebook for product %r" % product)
    raise InputError("Ambiguous applicable codebooks for product %r" % product)


def station_allowed(entry, station):
    declared = [norm(x) for x in entry["stations"] if norm(x)]
    if not declared:
        return True
    s = norm(station)
    universal = {"all", "any", "*", "global", "na"}
    if any(x in universal for x in declared):
        return True
    return any(x == s or (x and s and (x in s or s in x)) for x in declared)


def pair_score(query, alias):
    q, a = norm(query), norm(alias)
    if not q or not a:
        return 0.0, "no textual evidence"
    if q == a:
        return 1.0, "exact normalized codebook term"
    seq = difflib.SequenceMatcher(None, q, a).ratio()
    tq, ta = set(tokens(q)), set(tokens(a))
    f1 = (2.0 * len(tq & ta) / (len(tq) + len(ta))) if (tq or ta) else 0.0
    gq, ga = grams(q), grams(a)
    gj = len(gq & ga) / len(gq | ga) if (gq or ga) else 0.0
    contained = bool((len(a) >= 3 and a in q) or (len(q) >= 4 and q in a))
    score = 0.38 * seq + 0.34 * f1 + 0.28 * gj
    if contained:
        score = max(score, 0.84 if len(min(q, a, key=len)) >= 6 else 0.72)
    shared = sorted(tq & ta)
    evidence = "shared terms " + ", ".join(shared[:5]) if shared else "character-form similarity"
    if contained:
        evidence = "normalized codebook term contained in source"
    return min(1.0, score), evidence


def rank_candidates(span, entries, station):
    scored = []
    for e in entries:
        if not station_allowed(e, station):
            continue
        best, why, matched = -1.0, "", ""
        for alias in e["aliases"]:
            score, evidence = pair_score(span, alias)
            if score > best:
                best, why, matched = score, evidence, alias
        scored.append((best, e, why, matched))
    scored.sort(key=lambda x: (-x[0], x[1]["code"]))
    return scored


def independent_split(text, entries, station):
    """Split only when each side has credible evidence for different codebook entries."""
    initial = []
    start = 0
    for m in re.finditer(r"[;|\n\r]+", text):
        if text[start:m.start()].strip():
            initial.append((start, m.start()))
        start = m.end()
    if text[start:].strip():
        initial.append((start, len(text)))
    if not initial and text.strip():
        initial = [(0, len(text))]
    out = []
    splitter = re.compile(r"[,，、]+|\b(?:and|with|plus)\b|以及|并且|和", re.I)
    for left, right in initial:
        chunk = text[left:right]
        cuts = list(splitter.finditer(chunk))
        pieces = [(left, right)]
        # One conservative pass prevents punctuation-only oversegmentation.
        for m in cuts:
            a, b = left, left + m.start()
            c, d = left + m.end(), right
            if not text[a:b].strip() or not text[c:d].strip():
                continue
            ra, rb = rank_candidates(text[a:b].strip(), entries, station), rank_candidates(text[c:d].strip(), entries, station)
            if ra and rb and ra[0][0] >= 0.66 and rb[0][0] >= 0.66 and ra[0][1]["code"] != rb[0][1]["code"]:
                pieces = [(a, b), (c, d)]
                break
        for a, b in pieces:
            # Strip surrounding whitespace only; resulting text remains verbatim.
            while a < b and text[a].isspace(): a += 1
            while b > a and text[b-1].isspace(): b -= 1
            if a < b:
                out.append(text[a:b])
    return out


def confidence(score, margin, accepted):
    # A monotonic, evidence-based engineering proxy; configurations should be calibrated externally.
    margin_component = max(0.0, min(1.0, margin / 0.34))
    if accepted:
        return round(min(0.99, 0.60 + 0.28 * score + 0.11 * margin_component), 4)
    return round(max(0.03, min(0.55, 0.06 + 0.37 * max(0.0, score) + 0.10 * margin_component)), 4)


def normalize_record(row, cols, books, min_score, min_margin):
    record_id = str(row[cols["record"]])
    product = str(row[cols["product"]])
    station = str(row[cols["station"]])
    raw = str(row[cols["reason"]])
    entries = product_entries(product, books)
    if not raw.strip():
        # No nonempty source span exists; empty normalized list preserves the record without inventing evidence.
        return {"record_id": record_id, "product_id": product, "station": station,
                "engineer_id": str(row[cols["engineer"]]), "raw_reason_text": raw, "normalized": []}
    segments = []
    for i, span in enumerate(independent_split(raw, entries, station), 1):
        ranked = rank_candidates(span, entries, station)
        if not ranked:
            raise InputError("No station-compatible codebook entries for product %r station %r" % (product, station))
        best_score, best, evidence, alias = ranked[0]
        runner = ranked[1][0] if len(ranked) > 1 else 0.0
        margin = max(0.0, best_score - runner)
        exact = best_score >= 0.999
        accepted = best_score >= min_score and (exact or margin >= min_margin)
        if accepted:
            rationale = ("Assigned %s (%s): %s; best retrieval score %.3f, "
                         "runner-up %.3f, separation %.3f; product and station constraints applied."
                         % (best["code"], best["label"], evidence, best_score, runner, margin))
            code, label = best["code"], best["label"]
        else:
            reason = "below minimum score" if best_score < min_score else "insufficient separation from runner-up"
            rationale = ("UNKNOWN: source evidence did not support a unique constrained assignment (%s); "
                         "best candidate %s score %.3f, runner-up %.3f, separation %.3f."
                         % (reason, best["code"], best_score, runner, margin))
            code, label = "UNKNOWN", ""
        segments.append({"segment_id": "%s-S%d" % (record_id, i), "span_text": span,
                         "pred_code": code, "pred_label": label,
                         "confidence": confidence(best_score, margin, accepted), "rationale": rationale})
    return {"record_id": record_id, "product_id": product, "station": station,
            "engineer_id": str(row[cols["engineer"]]), "raw_reason_text": raw,
            "normalized": segments}


def validate(output, source_rows, books):
    records = output.get("records")
    if not isinstance(records, list) or len(records) != len(source_rows):
        raise InputError("Validation failed: output must represent every input record exactly once")
    seen_records = set()
    for rec in records:
        rid = rec.get("record_id")
        if rid in seen_records:
            raise InputError("Validation failed: duplicate record_id " + str(rid))
        seen_records.add(rid)
        entries = product_entries(rec.get("product_id", ""), books)
        allowed = {e["code"]: e for e in entries if station_allowed(e, rec.get("station", ""))}
        prior = 0
        for seg in rec.get("normalized", []):
            expected = "%s-S%d" % (rid, prior + 1)
            if seg.get("segment_id") != expected:
                raise InputError("Validation failed: unordered segment identifier " + str(seg.get("segment_id")))
            prior += 1
            span = seg.get("span_text")
            if not isinstance(span, str) or not span or span not in rec.get("raw_reason_text", ""):
                raise InputError("Validation failed: span is not a nonempty verbatim substring")
            c = seg.get("confidence")
            if not isinstance(c, (int, float)) or not math.isfinite(c) or not 0.0 <= c <= 1.0:
                raise InputError("Validation failed: invalid confidence")
            if not isinstance(seg.get("rationale"), str) or not seg["rationale"].strip():
                raise InputError("Validation failed: empty rationale")
            if seg.get("pred_code") == "UNKNOWN":
                if seg.get("pred_label") != "":
                    raise InputError("Validation failed: UNKNOWN must have empty label")
            else:
                e = allowed.get(seg.get("pred_code"))
                if not e or seg.get("pred_label") != e["label"]:
                    raise InputError("Validation failed: code/label is outside applicable codebook")


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise InputError("stdin must be a JSON object")
        event_path = config.get("events_path", "/app/data/test_center_logs.csv")
        paths = resolve_codebook_paths(config.get("codebook_paths"))
        output_path = config.get("output_path", "/app/output/solution.json")
        min_score = float(config.get("min_score", 0.66))
        min_margin = float(config.get("min_margin", 0.07))
        if not (0.0 <= min_score <= 1.0 and 0.0 <= min_margin <= 1.0):
            raise InputError("min_score and min_margin must be within [0,1]")
        fields, rows = read_csv(event_path)
        cols = {role: header_role(fields, role) for role in ("record", "product", "station", "engineer", "reason")}
        ids = [str(r[cols["record"]]) for r in rows]
        if len(ids) != len(set(ids)):
            raise InputError("record_id values must be unique for required segment IDs")
        books = load_codebooks(paths)
        records = [normalize_record(row, cols, books, min_score, min_margin) for row in rows]
        output = {"records": records}
        validate(output, rows, books)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        segments = [s for r in records for s in r["normalized"]]
        summary = {"output_path": output_path, "records": len(records), "segments": len(segments),
                   "assigned": sum(s["pred_code"] != "UNKNOWN" for s in segments),
                   "unknown": sum(s["pred_code"] == "UNKNOWN" for s in segments)}
        print(json.dumps(summary, ensure_ascii=False))
    except (InputError, csv.Error, json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
