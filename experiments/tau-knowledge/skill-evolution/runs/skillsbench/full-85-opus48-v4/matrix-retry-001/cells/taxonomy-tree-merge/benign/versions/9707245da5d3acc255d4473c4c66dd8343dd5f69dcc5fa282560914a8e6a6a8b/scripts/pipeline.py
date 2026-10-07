#!/usr/bin/env python3
"""End-to-end taxonomy merge entrypoint.

stdin JSON (all optional):
  {"data_dir":str, "output_dir":str,
   "files":{source_label:filename,...}, "embedding":"auto"|"tfidf"|"st"}
stdout JSON:
  {"status":"ok"|"error", "full_csv":path, "hierarchy_csv":path,
   "stats":{...}, "validation":{...}}

Defaults target the taxonomy-tree-merge task layout (/root/data -> /root/output
with amazon/fb/google CSVs) but every value is read at runtime; override via
stdin to match the live task.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import taxonomy_lib as T  # noqa: E402

DEFAULTS = {
    "data_dir": "/root/data",
    "output_dir": "/root/output",
    "files": {
        "amazon": "amazon_product_categories.csv",
        "facebook": "fb_product_categories.csv",
        "google": "google_shopping_product_categories.csv",
    },
    "embedding": "auto",
}


def read_config():
    cfg = dict(DEFAULTS)
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""
    if raw.strip():
        try:
            user = json.loads(raw)
            for k, v in user.items():
                cfg[k] = v
        except Exception:
            pass
    return cfg


def main():
    import numpy as np
    import pandas as pd

    cfg = read_config()
    data_dir = cfg["data_dir"]
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)

    lemmatizer = T.Lemmatizer()
    items, warnings = T.load_sources(data_dir, cfg["files"], lemmatizer)
    if not items:
        print(json.dumps({"status": "error",
                          "message": "no source rows loaded",
                          "warnings": warnings}))
        return 1

    # unique normalized strings for clustering
    str_to_idx = {}
    uniq_strings = []
    for it in items:
        s = it["norm_string"]
        if s not in str_to_idx:
            str_to_idx[s] = len(uniq_strings)
            uniq_strings.append(s)
        it["uidx"] = str_to_idx[s]

    item_tokens = [set(s.split()) for s in uniq_strings]
    emb = T.get_embeddings(uniq_strings, method=cfg.get("embedding", "auto"))
    emb = np.asarray(emb, dtype=np.float32)

    coverage_log = []
    assignment = T.recurse(list(range(len(uniq_strings))), 1, set(),
                           emb, item_tokens, coverage_log)

    # Build full mapping rows
    full_rows = []
    hier_set = set()
    for it in items:
        names = assignment.get(it["uidx"], [])
        padded = T.pad5(names)
        # depth = number of populated unified levels for this row (1-5), per the
        # task's "depth (1-5)" column spec (the unified-taxonomy depth, not the
        # original source path depth which can exceed 5).
        unified_depth = sum(1 for x in padded if x)
        row = {
            "source": it["source"],
            "category_path": it["category_path"],
            "depth": unified_depth,
            "unified_level_1": padded[0],
            "unified_level_2": padded[1],
            "unified_level_3": padded[2],
            "unified_level_4": padded[3],
            "unified_level_5": padded[4],
        }
        full_rows.append(row)
        # hierarchy: every prefix of the assigned path
        L = len([n for n in names if n])
        for p in range(1, L + 1):
            hier_set.add(tuple(T.pad5(names[:p])))

    full_df = pd.DataFrame(full_rows, columns=[
        "source", "category_path", "depth",
        "unified_level_1", "unified_level_2", "unified_level_3",
        "unified_level_4", "unified_level_5"])

    hier_rows = sorted(hier_set)
    hier_df = pd.DataFrame(hier_rows, columns=[
        "unified_level_1", "unified_level_2", "unified_level_3",
        "unified_level_4", "unified_level_5"])

    full_path = os.path.join(out_dir, "unified_taxonomy_full.csv")
    hier_path = os.path.join(out_dir, "unified_taxonomy_hierarchy.csv")
    full_df.to_csv(full_path, index=False)
    hier_df.to_csv(hier_path, index=False)

    validation = T.validate(full_rows, hier_rows)
    covs = [c for _, _, _, c in coverage_log]
    validation["min_name_coverage"] = round(min(covs), 3) if covs else None
    validation["mean_name_coverage"] = (
        round(sum(covs) / len(covs), 3) if covs else None)

    stats = {
        "n_source_rows": len(items),
        "n_unique_paths": len(uniq_strings),
        "n_full_rows": len(full_rows),
        "n_hierarchy_rows": len(hier_rows),
        "embedding_dim": int(emb.shape[1]) if emb.ndim == 2 else 0,
        "source_counts": {s: int((full_df["source"] == s).sum())
                           for s in full_df["source"].unique()},
        "warnings": warnings,
    }

    print(json.dumps({
        "status": "ok",
        "full_csv": full_path,
        "hierarchy_csv": hier_path,
        "stats": stats,
        "validation": validation,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        import traceback
        print(json.dumps({"status": "error", "message": str(e),
                          "trace": traceback.format_exc()}))
        rc = 1
    sys.exit(rc)
