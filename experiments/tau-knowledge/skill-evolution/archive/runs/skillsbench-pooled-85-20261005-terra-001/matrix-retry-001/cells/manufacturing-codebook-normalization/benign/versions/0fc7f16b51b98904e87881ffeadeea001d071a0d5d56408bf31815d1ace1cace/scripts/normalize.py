#!/usr/bin/env python3
"""CSV defect normalizer. JSON stdin -> JSON stdout; writes solution.json unless dry_run."""
import csv, glob, json, os, re, sys, unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

# Generic, reusable terminology expansion. It is retrieval support only; assignments
# remain constrained to labels actually present in the applicable codebook.
EXPANSIONS = {
    "短路": "short circuit", "开路": "open circuit", "断路": "open circuit",
    "漏电": "leakage", "过流": "overcurrent", "过压": "overvoltage",
    "欠压": "undervoltage", "无输出": "no output", "无信号": "no signal",
    "焊接": "solder", "虚焊": "cold solder", "松动": "loose",
    "fail": "failure", "ng": "failure", "oc": "overcurrent",
    "ov": "overvoltage", "uv": "undervoltage", "sc": "short circuit",
}
LOG_ALIASES = {
    "record_id": ["record_id", "recordid", "id", "log_id", "event_id", "case_id"],
    "product_id": ["product_id", "product", "productid", "model", "product_model"],
    "station": ["station", "test_station", "station_id", "stage", "test_stage"],
    "engineer_id": ["engineer_id", "engineer", "operator", "operator_id", "user"],
    "raw_reason_text": ["raw_reason_text", "reason_text", "reason", "defect_reason", "defect", "failure_reason", "comment", "notes"],
}
BOOK_ALIASES = {
    "code": ["code", "defect_code", "error_code", "failure_code", "pred_code"],
    "label": ["label", "defect_label", "description", "defect_name", "name", "standard_reason"],
    "product": ["product_id", "product", "productid", "model", "product_model"],
    "station": ["station", "stations", "applicable_station", "station_scope", "test_station", "stage"],
    "keywords": ["keywords", "keyword", "aliases", "alias", "synonyms", "terms", "examples"],
}

class InputError(ValueError):
    pass

def header_key(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).casefold())

def resolve(headers, aliases, role, required=True):
    keyed = {h: header_key(h) for h in headers}
    wanted = {header_key(a) for a in aliases}
    exact = [h for h, k in keyed.items() if k in wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise InputError("ambiguous %s columns: %s" % (role, exact))
    # A semantic fallback is intentionally conservative: more than one plausible
    # header is an error rather than an arbitrary schema-specific choice.
    fuzzy = [h for h, k in keyed.items() if any(a in k or k in a for a in wanted) and k]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if required:
        why = "none" if not fuzzy else ", ".join(fuzzy)
        raise InputError("cannot resolve required %s column (candidates: %s; headers: %s)" % (role, why, headers))
    if len(fuzzy) > 1:
        raise InputError("ambiguous optional %s columns: %s" % (role, fuzzy))
    return None

def read_csv(path):
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise InputError("CSV has no header: " + path)
            rows = list(reader)
            return reader.fieldnames, rows
    except OSError as exc:
        raise InputError("cannot read %s: %s" % (path, exc))

def norm(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).casefold()).strip()

def expanded(value):
    text = norm(value)
    additions = [english for term, english in EXPANSIONS.items() if term in text]
    return text + (" " + " ".join(additions) if additions else "")

def tokens(value):
    # Chinese runs are retained for SequenceMatcher; individual characters also
    # supply useful overlap evidence for mixed-language terminology.
    s = expanded(value)
    out = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", s)
    for run in re.findall(r"[\u4e00-\u9fff]+", s):
        if len(run) > 1:
            out.extend(run)
    return set(out)

def similarity(a, b):
    return SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0

def containment(a, b):
    # Avoid treating one/two-character status words as decisive matches.
    if min(len(a), len(b)) < 3:
        return 0.0
    return 1.0 if a in b or b in a else 0.0

def station_values(value):
    s = norm(value)
    if not s or s in {"all", "any", "*", "global", "na", "n/a"}:
        return None
    return {norm(x) for x in re.split(r"[;,|/]+", s) if norm(x)}

def compatible_station(scope, observed):
    allowed = station_values(scope)
    current = norm(observed)
    if allowed is None or not current:
        return True
    return current in allowed

def filename_product(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"^codebook[_-]*", "", stem, flags=re.I)
    return norm(stem)

def codebook_key_for(product, books):
    p = norm(product)
    exact = [k for k, b in books.items() if p in b["products"]]
    if len(exact) == 1:
        return exact[0]
    # Product-specific codebooks often encode the product solely in the filename.
    filename = [k for k, b in books.items() if b["file_product"] == p]
    if len(filename) == 1:
        return filename[0]
    partial = [k for k, b in books.items() if p and (p in b["file_product"] or b["file_product"] in p)]
    if len(partial) == 1:
        return partial[0]
    if not exact and not filename and not partial:
        raise InputError("no applicable codebook for product %r" % product)
    raise InputError("ambiguous codebook for product %r: %s" % (product, exact + filename + partial))

def load_codebooks(paths):
    books = {}
    for path in paths:
        headers, rows = read_csv(path)
        cols = {role: resolve(headers, aliases, role, role in ("code", "label"))
                for role, aliases in BOOK_ALIASES.items()}
        entries, product_values = [], set()
        for n, row in enumerate(rows, 2):
            code, label = str(row.get(cols["code"], "")).strip(), str(row.get(cols["label"], "")).strip()
            if not code or not label:
                raise InputError("%s row %d has empty code or label" % (path, n))
            prod = norm(row.get(cols["product"], "")) if cols["product"] else ""
            if prod:
                product_values.add(prod)
            keywords = str(row.get(cols["keywords"], "")) if cols["keywords"] else ""
            terms = " ".join(x for x in (label, keywords) if x)
            entries.append({"code": code, "label": label, "terms": expanded(terms),
                            "label_norm": expanded(label), "tokens": tokens(terms),
                            "scope": row.get(cols["station"], "") if cols["station"] else ""})
        if not entries:
            raise InputError("empty codebook: " + path)
        key = os.path.abspath(path)
        books[key] = {"entries": entries, "products": product_values,
                      "file_product": filename_product(path)}
    if not books:
        raise InputError("no codebook files supplied")
    return books

def rank(span, entries, station):
    query, qt = expanded(span), tokens(span)
    scored = []
    compatible_count = 0
    for e in entries:
        if not compatible_station(e["scope"], station):
            continue
        compatible_count += 1
        label_sim, term_sim = similarity(query, e["label_norm"]), similarity(query, e["terms"])
        overlap = len(qt & e["tokens"]) / max(1, len(qt | e["tokens"]))
        contain = max(containment(query, e["label_norm"]), containment(query, e["terms"]))
        # Independent label, all-term, token, and direct-substring evidence.
        score = .38 * label_sim + .27 * term_sim + .20 * overlap + .15 * contain
        scored.append((score, e, {"label_similarity": label_sim, "term_similarity": term_sim,
                                  "token_overlap": overlap, "containment": contain}))
    scored.sort(key=lambda x: (-x[0], x[1]["code"], x[1]["label"]))
    return scored, compatible_count

def segments(raw, entries, station):
    # Separators are retained only as boundaries; returned text comes directly from raw.
    initial = [p.strip() for p in re.split(r"(?:[;；]|\r?\n)+", raw) if p.strip()]
    if not initial and raw.strip():
        initial = [raw.strip()]
    result = []
    for part in initial:
        pieces = re.split(r"\s+(?:and|&|plus)\s+|(?:以及|并且|同时)", part, flags=re.I)
        if len(pieces) > 1 and all(x.strip() for x in pieces):
            # Avoid splitting a single bilingual phrase: all resulting sides must
            # independently have some compatible codebook support.
            supports = [rank(x.strip(), entries, station)[0] for x in pieces]
            if all(s and s[0][0] >= .34 for s in supports):
                result.extend(x.strip() for x in pieces)
                continue
        result.append(part)
    return result

def choose(span, entries, station, config):
    scored, compatible_count = rank(span, entries, station)
    if not scored:
        return None, 0.0, 0.0, {"reason": "no station-compatible codebook candidate"}
    best_score, best, signals = scored[0]
    runner_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - runner_score
    accept = best_score >= config["accept_score"] and margin >= config["min_margin"]
    if not accept:
        best = None
    signals.update({"runner_score": runner_score, "margin": margin,
                    "compatible_candidates": compatible_count})
    return best, best_score, margin, signals

def confidence(accepted, score, margin):
    if accepted:
        # Bounded, monotonic evidence transformation; accepted >= 0.60.
        return round(min(.99, .60 + .32 * score + .12 * min(1.0, margin)), 4)
    # Review values remain below the accepted floor and retain uncertainty variation.
    return round(min(.57, max(.05, .09 + .42 * score + .05 * max(0.0, margin))), 4)

def rationale(span, candidate, score, margin, signals, station):
    observed = span.replace("\n", " ")
    if candidate:
        station_note = "station-compatible" if candidate["scope"] else "no station scope declared"
        return ("Observed verbatim span %r; selected code %s label %r using label/keyword similarity "
                "%.3f, token overlap %.3f, and candidate separation %.3f (%s)." %
                (observed, candidate["code"], candidate["label"], signals["term_similarity"],
                 signals["token_overlap"], margin, station_note))
    return ("Observed verbatim span %r routed to review/UNKNOWN: best applicable codebook evidence "
            "score %.3f, runner-up separation %.3f, below configured acceptance policy or ambiguous." %
            (observed, score, margin))

def validate(solution, books):
    required_record = {"record_id", "product_id", "station", "engineer_id", "raw_reason_text", "normalized"}
    required_norm = {"segment_id", "span_text", "pred_code", "pred_label", "confidence", "rationale"}
    seen_segments = set()
    for rec in solution["records"]:
        if set(rec) != required_record:
            raise InputError("record output fields do not match required schema")
        book = books[codebook_key_for(rec["product_id"], books)]
        allowed = {(e["code"], e["label"]): e for e in book["entries"]}
        prior = 0
        for item in rec["normalized"]:
            if set(item) != required_norm:
                raise InputError("normalized output fields do not match required schema")
            expected = "%s-S%d" % (rec["record_id"], prior + 1)
            if item["segment_id"] != expected or item["segment_id"] in seen_segments:
                raise InputError("invalid or duplicate segment_id " + str(item["segment_id"]))
            seen_segments.add(item["segment_id"]); prior += 1
            if not item["span_text"] or item["span_text"] not in rec["raw_reason_text"]:
                raise InputError("span is not a non-empty verbatim source substring")
            try:
                c = float(item["confidence"])
            except (TypeError, ValueError):
                raise InputError("non-numeric confidence")
            if not 0.0 <= c <= 1.0 or not item["rationale"]:
                raise InputError("invalid confidence or empty rationale")
            if item["pred_code"] == "UNKNOWN":
                if item["pred_label"] != "" or c >= .60:
                    raise InputError("UNKNOWN requires empty label and review-range confidence")
            else:
                entry = allowed.get((item["pred_code"], item["pred_label"]))
                if entry is None:
                    raise InputError("code/label is absent from product codebook")
                if not compatible_station(entry["scope"], rec["station"]):
                    raise InputError("assignment violates station applicability")
                if c < .60:
                    raise InputError("accepted assignment has review-range confidence")

def main(request):
    logs_path = request.get("logs_path", "/app/data/test_center_logs.csv")
    paths = request.get("codebook_paths") or sorted(glob.glob("/app/data/codebook_*.csv"))
    output_path = request.get("output_path", "/app/output/solution.json")
    cfg = {"accept_score": .58, "min_margin": .08}
    cfg.update(request.get("config") or {})
    for k in cfg:
        if not isinstance(cfg[k], (int, float)) or not 0 <= cfg[k] <= 1:
            raise InputError("config %s must be numeric in [0,1]" % k)
    headers, rows = read_csv(logs_path)
    lcols = {role: resolve(headers, aliases, role, True) for role, aliases in LOG_ALIASES.items()}
    books = load_codebooks(paths)
    records, unknowns, accepted = [], 0, 0
    for row_number, row in enumerate(rows, 2):
        record = {role: str(row.get(col, "")) for role, col in lcols.items()}
        if not record["record_id"] or not record["product_id"]:
            raise InputError("log row %d lacks record_id or product_id" % row_number)
        book = books[codebook_key_for(record["product_id"], books)]
        normed = []
        for i, span in enumerate(segments(record["raw_reason_text"], book["entries"], record["station"]), 1):
            candidate, score, margin, signals = choose(span, book["entries"], record["station"], cfg)
            is_accept = candidate is not None
            if is_accept:
                accepted += 1; code, label = candidate["code"], candidate["label"]
            else:
                unknowns += 1; code, label = "UNKNOWN", ""
            normed.append({"segment_id": "%s-S%d" % (record["record_id"], i), "span_text": span,
                           "pred_code": code, "pred_label": label,
                           "confidence": confidence(is_accept, score, margin),
                           "rationale": rationale(span, candidate, score, margin, signals, record["station"])})
        record["normalized"] = normed
        records.append(record)
    solution = {"records": records}
    validate(solution, books)
    if not request.get("dry_run", False):
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="") as fh:
            json.dump(solution, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return {"ok": True, "records": len(records), "accepted_segments": accepted,
            "unknown_segments": unknowns, "output_path": None if request.get("dry_run") else output_path}

if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise InputError("stdin must contain a JSON object")
        print(json.dumps(main(request), ensure_ascii=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(2)
