#!/usr/bin/env python3
"""Structural self-consistency check for the two deliverables.

stdin JSON: {"instructions": path, "masks": path}
stdout JSON: {"ok": bool, "num_frames": N, "shape": [H,W], "errors": [...]}

Checks derive only from the public task contract, not any reference answer.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import numpy as np  # noqa: E402
import common  # noqa: E402


def main():
    cfg = json.loads(sys.stdin.read() or "{}")
    instr_path = cfg.get("instructions", "/root/pred_instructions.json")
    masks_path = cfg.get("masks", "/root/pred_dyn_masks.npz")
    errors = []

    with open(instr_path) as f:
        instr = json.load(f)

    covered = {}
    max_end = 0
    valid = set(common.VALID_LABELS)
    for key, labs in instr.items():
        try:
            s, e = key.split("->")
            s, e = int(s), int(e)
        except Exception:
            errors.append("bad key: %r" % key)
            continue
        if not (s < e):
            errors.append("non-increasing interval: %s" % key)
        if not isinstance(labs, list) or len(labs) == 0:
            errors.append("empty/invalid labels for %s" % key)
        for lab in (labs or []):
            if lab not in valid:
                errors.append("invalid label %r in %s" % (lab, key))
        max_end = max(max_end, e)
        for i in range(s, e):
            covered[i] = covered.get(i, 0) + 1

    n_instr = max_end
    for i in range(n_instr):
        if covered.get(i, 0) == 0:
            errors.append("frame %d not covered" % i)
        elif covered[i] > 1:
            errors.append("frame %d covered %d times" % (i, covered[i]))
    extra = [i for i in covered if i >= n_instr]
    if extra:
        errors.append("indices beyond N-1 present: %s" % extra)

    npz = np.load(masks_path)
    if "shape" not in npz:
        errors.append("npz missing 'shape'")
        shape = None
    else:
        shape = [int(x) for x in npz["shape"]]
    h, w = (shape if shape else (None, None))

    i = 0
    n_masks = 0
    while ("f_%d_data" % i) in npz or ("f_%d_indptr" % i) in npz:
        n_masks += 1
        indptr = npz.get("f_%d_indptr" % i)
        indices = npz.get("f_%d_indices" % i)
        data = npz.get("f_%d_data" % i)
        if indptr is None or indices is None or data is None:
            errors.append("frame %d missing a CSR key" % i)
            i += 1
            continue
        if h is not None and len(indptr) != h + 1:
            errors.append("frame %d indptr len %d != H+1" % (i, len(indptr)))
        if len(indptr) and indptr[0] != 0:
            errors.append("frame %d indptr[0] != 0" % i)
        if len(indptr) and int(indptr[-1]) != len(indices):
            errors.append("frame %d indptr[-1] != len(indices)" % i)
        if np.any(np.diff(indptr) < 0):
            errors.append("frame %d indptr not monotonic" % i)
        if w is not None and len(indices) and int(np.max(indices)) >= w:
            errors.append("frame %d column index >= W" % i)
        if len(data) != len(indices):
            errors.append("frame %d data/indices length mismatch" % i)
        # per-row sorted check and reconstructability
        if h is not None:
            for r in range(h):
                seg = indices[indptr[r]:indptr[r + 1]]
                if len(seg) > 1 and np.any(np.diff(seg) < 0):
                    errors.append("frame %d row %d indices unsorted" % (i, r))
                    break
        i += 1

    if n_masks != n_instr:
        errors.append("num masks %d != num instruction frames %d"
                      % (n_masks, n_instr))

    out = {
        "ok": len(errors) == 0,
        "num_frames": n_instr,
        "num_masks": n_masks,
        "shape": shape,
        "errors": errors,
    }
    print(json.dumps(out))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
