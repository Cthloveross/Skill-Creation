"""End-to-end 13F analysis entrypoint.

Reads optional JSON config on stdin, writes answers.json (and a diagnostics
file), and prints a JSON summary on stdout.

Config keys (all optional, with defaults):
  q2_zip, q3_zip, q2_dir, q3_dir, output, diagnostics,
  renaissance_query, berkshire_query, palantir_query, stock_count_mode
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thirteenf as tf  # noqa: E402

DEFAULTS = {
    "q2_zip": "/root/13f-2025-q2.zip",
    "q3_zip": "/root/13f-2025-q3.zip",
    "q2_dir": "/root/2025-q2",
    "q3_dir": "/root/2025-q3",
    "output": "/root/answers.json",
    "diagnostics": "/root/answers_diagnostics.json",
    "renaissance_query": "renaissance technologies",
    "berkshire_query": "berkshire hathaway",
    "palantir_query": "palantir",
    "stock_count_mode": "unique_cusip_equity",
}
VALID_MODES = {"unique_cusip_equity", "unique_cusip_all", "rows_equity", "rows_all"}


def resolve_manager(quarter_dir, query, cover_rows):
    """Fuzzy-match a manager, aggregate its candidate accessions, pick primary.
    Returns (best_name, score, primary_accession, agg_record, candidates_info).
    """
    name, score, rows_for_name = tf.fuzzy_best(query, cover_rows)
    cand_accs = [r["accession"] for r in rows_for_name if r["accession"]]
    agg = tf.aggregate_accessions(quarter_dir, cand_accs)
    acc_totals = {a: agg[a]["total_value"] for a in agg}
    primary = tf.select_primary_accession(rows_for_name, acc_totals)
    cand_info = [
        {"accession": r["accession"], "isamendment": r["isamendment"],
         "total_value": acc_totals.get(r["accession"], 0.0)}
        for r in rows_for_name
    ]
    return name, score, primary, (agg.get(primary) if primary else None), cand_info


def main():
    raw = sys.stdin.read().strip()
    cfg = dict(DEFAULTS)
    if raw:
        try:
            cfg.update({k: v for k, v in json.loads(raw).items() if v is not None})
        except json.JSONDecodeError as e:
            print(json.dumps({"error": "bad stdin JSON: %s" % e}))
            return 1

    mode = cfg["stock_count_mode"]
    mode_note = None
    if mode not in VALID_MODES:
        mode_note = "unsupported stock_count_mode %r; using default" % mode
        mode = "unique_cusip_equity"

    diag = {"stock_count_mode_used": mode}
    if mode_note:
        diag["stock_count_mode_note"] = mode_note

    try:
        q2_dir = tf.ensure_extracted(cfg["q2_zip"], cfg["q2_dir"])
        q3_dir = tf.ensure_extracted(cfg["q3_zip"], cfg["q3_dir"])
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}))
        return 1
    diag["q2_dir"] = q2_dir
    diag["q3_dir"] = q3_dir

    q2_cover = tf.load_coverpage(q2_dir)
    q3_cover = tf.load_coverpage(q3_dir)

    # ---- Q1 & Q2: Renaissance Technologies, Q3 ----
    r_name, r_score, r_acc, r_rec, r_cand = resolve_manager(
        q3_dir, cfg["renaissance_query"], q3_cover)
    diag["renaissance"] = {
        "matched_name": r_name, "score": r_score,
        "primary_accession": r_acc, "candidates": r_cand,
    }
    if r_rec is None:
        q1 = None
        q2 = None
    else:
        q1 = int(round(r_rec["total_value"]))
        diag["renaissance"]["stock_counts"] = {
            m: tf.stock_count(r_rec, m) for m in VALID_MODES
        }
        q2 = tf.stock_count(r_rec, mode)

    # ---- Q3: Berkshire Hathaway change Q2 -> Q3 ----
    b2_name, b2_score, b2_acc, b2_rec, b2_cand = resolve_manager(
        q2_dir, cfg["berkshire_query"], q2_cover)
    b3_name, b3_score, b3_acc, b3_rec, b3_cand = resolve_manager(
        q3_dir, cfg["berkshire_query"], q3_cover)
    diag["berkshire"] = {
        "q2": {"matched_name": b2_name, "score": b2_score,
               "primary_accession": b2_acc, "candidates": b2_cand},
        "q3": {"matched_name": b3_name, "score": b3_score,
               "primary_accession": b3_acc, "candidates": b3_cand},
    }
    if b2_rec is None or b3_rec is None:
        q3_answer = None
    else:
        ranking = tf.compute_change_ranking(
            b2_rec["cusip_equity_value"], b3_rec["cusip_equity_value"])
        increases = [row for row in ranking if row[3] > 0]
        diag["berkshire"]["top_increases"] = [
            {"cusip": c, "q2": v2, "q3": v3, "change": ch}
            for (c, v2, v3, ch) in increases[:15]
        ]
        q3_answer = [row[0] for row in increases[:5]]

    # ---- Q4: top-3 managers holding Palantir in Q3 ----
    pal_cusips = tf.find_cusips_by_issuer(q3_dir, cfg["palantir_query"], equity_only=True)
    diag["palantir"] = {"cusips": pal_cusips}
    if not pal_cusips:
        q4_answer = None
    else:
        acc_value = tf.value_by_accession_for_cusips(
            q3_dir, list(pal_cusips), equity_only=True)
        name_map = tf.cover_name_map(q3_dir)
        # De-duplicate by manager name (avoid amendment double counting): keep
        # the maximum value seen for each manager name.
        by_name = {}
        for acc, val in acc_value.items():
            nm = name_map.get(acc, acc)
            if nm not in by_name or val > by_name[nm]:
                by_name[nm] = val
        ranked = sorted(by_name.items(), key=lambda kv: kv[1], reverse=True)
        diag["palantir"]["top_holders"] = [
            {"name": nm, "value": v} for nm, v in ranked[:10]
        ]
        q4_answer = [nm for nm, _ in ranked[:3]]

    answers = {
        "q1_answer": q1,
        "q2_answer": q2,
        "q3_answer": q3_answer,
        "q4_answer": q4_answer,
    }

    with open(cfg["output"], "w", encoding="utf-8") as fh:
        json.dump(answers, fh, indent=2)
    with open(cfg["diagnostics"], "w", encoding="utf-8") as fh:
        json.dump(diag, fh, indent=2, default=list)

    print(json.dumps({
        "answers": answers,
        "output_path": cfg["output"],
        "diagnostics_path": cfg["diagnostics"],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
