#!/usr/bin/env python3
"""End-to-end 13F analysis entrypoint.

Stdin: optional JSON config (any subset of keys below). Empty input / '{}'
uses the task defaults. Nothing in this script is a hardcoded answer; query
strings and paths are read from config and the actual dataset is read at
runtime.

Config keys:
  q2_dir, q3_dir            data folders (unzipped from q2_zip/q3_zip if absent)
  q2_zip, q3_zip            quarterly zip archives
  renaissance_query         fuzzy query for q1/q2 fund
  berkshire_query           fuzzy query for q3 fund
  security_name             issuer-name substring for q4
  stock_count_policy        equity_unique_cusip | equity_rows |
                            all_unique_cusip | all_rows
  output                    answers.json path

Stdout: diagnostics JSON. Side effect: writes answers.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edgar13f as e  # noqa: E402

DEFAULTS = {
    "q2_dir": "/root/2025-q2",
    "q3_dir": "/root/2025-q3",
    "q2_zip": "/root/13f-2025-q2.zip",
    "q3_zip": "/root/13f-2025-q3.zip",
    "renaissance_query": "renaissance technologies",
    "berkshire_query": "berkshire hathaway",
    "security_name": "palantir",
    "stock_count_policy": "equity_unique_cusip",
    "output": "/root/answers.json",
}


def main():
    raw = sys.stdin.read().strip()
    cfg = dict(DEFAULTS)
    if raw:
        try:
            cfg.update(json.loads(raw))
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"bad stdin JSON: {exc}"}))
            sys.exit(2)

    q2d = e.ensure_dir(cfg["q2_dir"], cfg["q2_zip"])
    q3d = e.ensure_dir(cfg["q3_dir"], cfg["q3_zip"])

    cover_q2 = e.load_coverpage(q2d)
    cover_q3 = e.load_coverpage(q3d)
    info_q2 = e.load_infotable(q2d)
    info_q3 = e.load_infotable(q3d)
    summary_q3 = e.load_summary(q3d)

    # q1 + q2: Renaissance in Q3
    ren = e.match_manager(cover_q3, cfg["renaissance_query"])
    ren_aum = e.aum(info_q3, ren["accession"]) if ren["accession"] else 0.0
    counts = e.stock_counts(info_q3, ren["accession"]) if ren["accession"] else {}
    policy = cfg["stock_count_policy"]
    q2_val = counts.get(policy)
    if q2_val is None:
        q2_val = counts.get("equity_unique_cusip", 0)

    summary_check = None
    if summary_q3 is not None and ren["accession"]:
        srow = summary_q3[summary_q3["ACCESSION_NUMBER"] == ren["accession"]]
        if len(srow):
            summary_check = {
                "TABLEENTRYTOTAL": srow["TABLEENTRYTOTAL"].iloc[0]
                if "TABLEENTRYTOTAL" in srow else None,
                "TABLEVALUETOTAL": srow["TABLEVALUETOTAL"].iloc[0]
                if "TABLEVALUETOTAL" in srow else None,
            }

    # q3: Berkshire Q2 -> Q3 top increases
    bh_q2 = e.match_manager(cover_q2, cfg["berkshire_query"])
    bh_q3 = e.match_manager(cover_q3, cfg["berkshire_query"])
    top5, _merged = ([], None)
    if bh_q2["accession"] and bh_q3["accession"]:
        top5, _merged = e.top_increases(
            info_q2, bh_q2["accession"], info_q3, bh_q3["accession"], top=5)

    # q4: top-3 Palantir holders in Q3
    top3_names, pal_cusips, _grp = e.top_holders_of_security(
        info_q3, cover_q3, cfg["security_name"], top=3)

    answers = {
        "q1_answer": int(round(ren_aum)),
        "q2_answer": int(q2_val),
        "q3_answer": [str(c) for c in top5],
        "q4_answer": [str(n) for n in top3_names],
    }

    with open(cfg["output"], "w") as f:
        json.dump(answers, f, indent=2)

    diagnostics = {
        "answers": answers,
        "output_path": cfg["output"],
        "renaissance_match": ren,
        "renaissance_aum": ren_aum,
        "stock_count_variants": counts,
        "stock_count_policy_used": policy,
        "renaissance_summary_crosscheck": summary_check,
        "berkshire_match_q2": bh_q2,
        "berkshire_match_q3": bh_q3,
        "palantir_cusips": pal_cusips,
    }
    print(json.dumps(diagnostics, indent=2, default=str))


if __name__ == "__main__":
    main()
