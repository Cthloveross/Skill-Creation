#!/usr/bin/env python3
"""End-to-end entrypoint for the Mars cloud clustering Pareto task.

Reads optional JSON config on stdin, writes JSON summary on stdout, and writes
the Pareto frontier CSV to the configured output path.

stdin JSON (all optional):
  {"citsci_path": str, "expert_path": str, "output_path": str, "n_jobs": int}

stdout JSON:
  {"status":"ok"|"error", ...}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clustering_lib as cl  # noqa: E402


def main():
    try:
        raw = sys.stdin.read().strip()
        cfg = json.loads(raw) if raw else {}
    except Exception:
        cfg = {}

    citsci_path = cfg.get("citsci_path", "/root/data/citsci_train.csv")
    expert_path = cfg.get("expert_path", "/root/data/expert_train.csv")
    output_path = cfg.get("output_path", "/root/pareto_frontier.csv")
    n_jobs = int(cfg.get("n_jobs", 4))

    for p in (citsci_path, expert_path):
        if not os.path.exists(p):
            print(json.dumps({"status": "error",
                              "error": f"missing input file: {p}"}))
            return

    try:
        pf, n_images = cl.compute_pareto_frontier(
            citsci_path, expert_path, n_jobs=n_jobs
        )
        rows = cl.format_and_write(pf, output_path)
        print(json.dumps({
            "status": "ok",
            "output_path": output_path,
            "n_images": n_images,
            "n_pareto": len(rows),
            "rows": rows,
        }))
    except Exception as e:  # noqa
        import traceback
        print(json.dumps({
            "status": "error",
            "error": str(e),
            "trace": traceback.format_exc(),
        }))


if __name__ == "__main__":
    main()
