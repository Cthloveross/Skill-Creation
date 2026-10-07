#!/usr/bin/env python3
"""CSV manufacturing-defect normalizer.

Input: one JSON object on stdin; schema is documented in SKILL.md.
Output: JSON execution summary on stdout and a solution JSON at output_path.
Only Python's standard library is required.
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


def fail(message):
    raise ValueError(message)


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(16384)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        if not reader.fieldnames:
            fail("CSV has no header: " + path)
        headers = [h.strip() for h in reader.fieldnames if h is not None]
        rows = []
        for row in reader:
            rows.append({(k or "").strip(): (v or "") for k, v in row.items()})
    return headers, rows


def norm(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = re.sub(r"[\s_\-./\\,;:|()\[\]{}]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def compact(value):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", norm(value))


def words(value):
    # English-like words, numeric references, and individual Han characters.
    return set(re.findall(r"[a-z]+\d*|\d+(?:\.\d+)?|[\u4e00-\u9fff]", norm(value)))


def header_score(header, role):
    h = norm(header).replace(" ", "")
    targets = {
        "record_id": ["recordid", "record", "logid", "eventid", "id"],
        "product_id": ["productid", "product", "model", "family", "sku"],
        "station": ["station", "teststation", "stage", "process"],
        "engineer_id": ["engineerid", "engineer", "operator", "author", "user"],
        "raw_reason_text": ["rawreasontext", "reasontext", "reason", "defecttext", "comment", "description", "note", "failure"],
        "code": ["defectcode", "errorcode", "failurecode", "code"],
        "label": ["defectlabel", "standardlabel", "label", "defectname", "standardreason", "reasonname", "name"],
    }
    best = 0
    for rank, target in enumerate(targets[role]):
        if h == target:
            best = max(best, 100 - rank)
        elif target in h:
            best = max(best, 65 - rank)
    return best


def choose_header(headers, role, override=None, required=False):
    if override:
        if override not in headers:
            fail("Configured %s header is absent: %r" % (role, override))
        return override
    scored = sorted(((header_score(h, role), h) for h in headers), reverse=True)
    if not scored or scored[0][0] == 0:
        if required:
            fail("Cannot infer required %s column; headers are %s" % (role, headers))
        return None
    best, name = scored[0]
    tied = [h for s, h in scored if s == best]
    if len(tied) > 1:
        fail("Ambiguous %s columns %s; set an explicit role mapping" % (role, tied))
    return name


def split_aliases(value):
    """Return useful codebook alias phrases without inventing translations."""
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"(?:\r?\n|[;；|])", text)
    result = []
    for part in parts:
        part = part.strip()
        if compact(part):
            result.append(part)
    return result


def station_allowed(scope, observed):
    if not scope or not str(scope).strip():
        return True
    observed_n = norm(observed)
    if not observed_n:
        return True
    allowed = [norm(x) for x in re.split(r"[;,/|；\n]", str(scope)) if norm(x)]
    if not allowed:
        return True
    # Explicit wildcard scope is compatible; otherwise require a complete scope item match.
    return any(x in ("*", "all", "any", "na", "n a") or x == observed_n for x in allowed)


def source_keys(path, rows, product_col):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"^(?:codebook|codes?|defects?)[ _-]*", "", stem, flags=re.I)
    keys = {norm(stem), compact(stem)}
    if product_col:
        for row in rows:
            value = row.get(product_col, "")
            if value:
                keys.update((norm(value), compact(value)))
    return {x for x in keys if x}


def select_sources(product, sources):
    pnorm, pcompact = norm(product), compact(product)
    exact = [s for s in sources if pnorm in s["keys"] or pcompact in s["keys"]]
    if exact:
        return exact
    # A prefix fallback is safe only where it identifies exactly one supplied namespace.
    possible = []
    for source in sources:
        if any(k and (pnorm.startswith(k + " ") or k.startswith(pnorm + " ") or
                      pcompact.startswith(k) or k.startswith(pcompact)) for k in source["keys"]):
            possible.append(source)
    return possible if len(possible) == 1 else []


def build_candidates(paths, config):
    role_cfg = config.get("codebook_roles") or {}
    sources = []
    for path in paths:
        headers, rows = read_csv(path)
        code_col = choose_header(headers, "code", role_cfg.get("code"), required=True)
        label_col = choose_header(headers, "label", role_cfg.get("label"), required=True)
        prod_col = choose_header(headers, "product_id", role_cfg.get("product_id"), required=False)
        station_col = choose_header(headers, "station", role_cfg.get("station"), required=False)
        excluded = {code_col, label_col, prod_col, station_col}
        alias_cols = [h for h in headers if h not in excluded]
        candidates = []
        for row in rows:
            code, label = row.get(code_col, "").strip(), row.get(label_col, "").strip()
            if not code or not label:
                continue
            aliases = [(label, "label")]
            for col in alias_cols:
                value = row.get(col, "")
                # Numeric metadata is not a defect expression.
                if value and not re.fullmatch(r"\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*", value):
                    aliases.extend((x, col) for x in split_aliases(value))
            unique = []
            seen = set()
            for phrase, field in aliases:
                key = compact(phrase)
                if len(key) >= 2 and key not in seen:
                    seen.add(key)
                    unique.append((phrase, field, key, words(phrase)))
            candidates.append({"code": code, "label": label, "scope": row.get(station_col, "") if station_col else "", "aliases": unique})
        if not candidates:
            fail("No usable code/label rows in " + path)
        sources.append({"path": path, "keys": source_keys(path, rows, prod_col), "candidates": candidates})
    return sources


def score_candidate(text, candidate):
    nt, ct, wt = norm(text), compact(text), words(text)
    if not ct:
        return 0.0, "", "", 0.0
    best = (0.0, "", "", 0.0)
    for phrase, field, ca, wa in candidate["aliases"]:
        exact = ct == ca
        if exact:
            score = 1.0
        elif len(ca) >= 3 and ca in ct:
            score = min(0.985, 0.84 + 0.14 * min(1.0, len(ca) / max(1, len(ct))))
        elif len(ct) >= 4 and ct in ca:
            score = 0.72 + 0.10 * min(1.0, len(ct) / len(ca))
        else:
            seq = difflib.SequenceMatcher(None, ct, ca).ratio()
            union = wt | wa
            jac = len(wt & wa) / len(union) if union else 0.0
            nums_t, nums_a = set(re.findall(r"\d+(?:\.\d+)?", ct)), set(re.findall(r"\d+(?:\.\d+)?", ca))
            digit = 1.0 if nums_t and nums_t == nums_a else (0.0 if nums_t or nums_a else 0.5)
            score = 0.57 * seq + 0.35 * jac + 0.08 * digit
        if score > best[0]:
            best = (score, phrase, field, difflib.SequenceMatcher(None, ct, ca).ratio())
    return best


def split_segments(raw):
    """Split only strong list boundaries; every returned value is a literal substring."""
    if not raw or not str(raw).strip():
        return []
    raw = str(raw)
    pieces = re.split(r"(?:\r?\n|[;；])+")
    result = []
    for piece in pieces:
        span = piece.strip()
        if span:
            result.append(span)
    return result or [raw.strip()]


def decide(span, candidates, station, accept, margin):
    eligible = [c for c in candidates if station_allowed(c["scope"], station)]
    if not eligible:
        return {"code": "UNKNOWN", "label": "", "confidence": 0.08,
                "rationale": "Verbatim span %r has no candidate compatible with the declared product and station scope." % span}
    ranked = []
    for candidate in eligible:
        score, phrase, field, seq = score_candidate(span, candidate)
        ranked.append((score, candidate, phrase, field, seq))
    ranked.sort(key=lambda x: (-x[0], x[1]["code"]))
    best_score, best, phrase, field, _ = ranked[0]
    runner = ranked[1][0] if len(ranked) > 1 else 0.0
    gap = best_score - runner
    accepted = best_score >= accept and (len(ranked) == 1 or gap >= margin)
    if not accepted:
        # UNKNOWN scores quantify strength of the unresolved evidence but stay below accepted scores.
        conf = round(min(0.58, max(0.06, 0.12 + 0.42 * best_score + 0.10 * max(0.0, gap))), 4)
        why = "below configured acceptance score" if best_score < accept else "too close to runner-up"
        return {"code": "UNKNOWN", "label": "", "confidence": conf,
                "rationale": "Verbatim span %r is routed to review: best product-scoped candidate %s scored %.3f, runner-up %.3f (%s)." % (span, best["code"], best_score, runner, why)}
    conf = 0.64 + 0.30 * best_score + 0.06 * min(1.0, gap / max(margin, 0.001))
    conf = round(min(0.995, max(0.61, conf)), 4)
    return {"code": best["code"], "label": best["label"], "confidence": conf,
            "rationale": "Verbatim span %r matched %s alias %r in the applicable product codebook (score %.3f; runner-up %.3f)." % (span, field, phrase, best_score, runner)}


def validate(output, source_rows, sources):
    records = output.get("records")
    if not isinstance(records, list) or len(records) != len(source_rows):
        fail("Validation failed: output does not represent every input record exactly once")
    allowed_by_product = {}
    for rec in records:
        rid = str(rec.get("record_id", ""))
        product = str(rec.get("product_id", ""))
        selected = select_sources(product, sources)
        allowed = {c["code"]: c for s in selected for c in s["candidates"]}
        seen = set()
        for index, item in enumerate(rec.get("normalized", []), 1):
            expected = rid + "-S" + str(index)
            if item.get("segment_id") != expected or item["segment_id"] in seen:
                fail("Validation failed: invalid segment identifier for record " + rid)
            seen.add(item["segment_id"])
            span = item.get("span_text", "")
            if not isinstance(span, str) or not span or span not in str(rec.get("raw_reason_text", "")):
                fail("Validation failed: non-verbatim or empty span for record " + rid)
            confidence = item.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
                fail("Validation failed: confidence out of range for record " + rid)
            if not item.get("rationale"):
                fail("Validation failed: empty rationale for record " + rid)
            if item.get("pred_code") == "UNKNOWN":
                if item.get("pred_label") != "":
                    fail("Validation failed: UNKNOWN must have empty label")
            else:
                candidate = allowed.get(item.get("pred_code"))
                if not candidate or item.get("pred_label") != candidate["label"]:
                    fail("Validation failed: code or label outside product codebook for record " + rid)
                if not station_allowed(candidate["scope"], rec.get("station", "")):
                    fail("Validation failed: station-incompatible code for record " + rid)


def main():
    raw_config = sys.stdin.read().strip()
    config = json.loads(raw_config) if raw_config else {}
    logs_path = config.get("logs_path", "/app/data/test_center_logs.csv")
    paths = config.get("codebook_paths") or sorted(glob.glob(config.get("codebook_glob", "/app/data/codebook_*.csv")))
    if not paths:
        fail("No codebook files found")
    accept = float(config.get("accept_score", 0.70))
    margin = float(config.get("ambiguity_margin", 0.055))
    if not 0.0 <= accept <= 1.0 or margin < 0:
        fail("accept_score must be in [0,1] and ambiguity_margin must be nonnegative")
    headers, rows = read_csv(logs_path)
    role_cfg = config.get("log_roles") or {}
    roles = {
        "record_id": choose_header(headers, "record_id", role_cfg.get("record_id"), True),
        "product_id": choose_header(headers, "product_id", role_cfg.get("product_id"), True),
        "station": choose_header(headers, "station", role_cfg.get("station"), True),
        "engineer_id": choose_header(headers, "engineer_id", role_cfg.get("engineer_id"), True),
        "raw_reason_text": choose_header(headers, "raw_reason_text", role_cfg.get("raw_reason_text"), True),
    }
    sources = build_candidates(paths, config)
    records, accepted_count, unknown_count = [], 0, 0
    for row in rows:
        record = {out_key: str(row.get(col, "")) for out_key, col in roles.items()}
        selected_sources = select_sources(record["product_id"], sources)
        candidates = [c for source in selected_sources for c in source["candidates"]]
        normalized = []
        for idx, span in enumerate(split_segments(record["raw_reason_text"]), 1):
            decision = decide(span, candidates, record["station"], accept, margin)
            normalized.append({"segment_id": record["record_id"] + "-S" + str(idx), "span_text": span,
                               "pred_code": decision["code"], "pred_label": decision["label"],
                               "confidence": decision["confidence"], "rationale": decision["rationale"]})
            if decision["code"] == "UNKNOWN":
                unknown_count += 1
            else:
                accepted_count += 1
        record["normalized"] = normalized
        records.append(record)
    output = {"records": records}
    validate(output, rows, sources)
    output_path = config.get("output_path", "/app/output/solution.json")
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"output_path": output_path, "records": len(records), "accepted_segments": accepted_count,
                      "unknown_segments": unknown_count, "resolved_log_roles": roles}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(2)
