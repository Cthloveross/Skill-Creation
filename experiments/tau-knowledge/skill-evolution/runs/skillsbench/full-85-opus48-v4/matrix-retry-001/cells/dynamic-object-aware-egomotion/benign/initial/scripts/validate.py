#!/usr/bin/env python3
"""Validate the two deliverables against the public contract.

Stdin JSON: {"instructions": path, "masks": path, "n_frames": optional int}
Stdout JSON: {"ok": bool, "errors": [...], "n_frames": int, "shape": [H,W]}
Exits non-zero if any check fails.
"""
import sys, json, re

VALID = {
    "Stay", "Dolly In", "Dolly Out", "Pan Left", "Pan Right",
    "Tilt Up", "Tilt Down", "Roll Left", "Roll Right",
}
KEY_RE = re.compile(r"^(\d+)->(\d+)$")


def main():
    try:
        cfg = json.loads(sys.stdin.read() or "{}")
    except Exception as e:
        print(json.dumps({"ok": False, "errors": ["bad config: %s" % e]}))
        return 2
    inst_path = cfg.get("instructions", "/root/pred_instructions.json")
    masks_path = cfg.get("masks", "/root/pred_dyn_masks.npz")

    import numpy as np
    errors = []

    # instructions
    n_from_inst = None
    try:
        with open(inst_path) as f:
            inst = json.load(f)
        intervals = []
        for k, v in inst.items():
            m = KEY_RE.match(k)
            if not m:
                errors.append("bad interval key: %s" % k)
                continue
            s, e = int(m.group(1)), int(m.group(2))
            if s >= e:
                errors.append("non-positive interval: %s" % k)
            intervals.append((s, e))
            if not isinstance(v, list) or not v:
                errors.append("labels not a non-empty list for %s" % k)
                continue
            for lab in v:
                if lab not in VALID:
                    errors.append("invalid label %r in %s" % (lab, k))
            if "Stay" in v and len(v) > 1:
                errors.append("Stay co-occurs with other labels in %s" % k)
        intervals.sort()
        if intervals:
            if intervals[0][0] != 0:
                errors.append("intervals do not start at 0")
            cur = intervals[0][0]
            for s, e in intervals:
                if s != cur:
                    errors.append("gap/overlap at %d (expected %d)" % (s, cur))
                cur = e
            n_from_inst = cur
        else:
            errors.append("no intervals")
    except Exception as e:
        errors.append("instructions error: %s" % e)

    # masks
    H = W = None
    n_from_masks = None
    try:
        d = np.load(masks_path)
        if "shape" not in d.files:
            errors.append("missing shape key in npz")
        else:
            shp = d["shape"]
            H, W = int(shp[0]), int(shp[1])
        # count frames
        frame_ids = set()
        for key in d.files:
            m = re.match(r"^f_(\d+)_(data|indices|indptr)$", key)
            if m:
                frame_ids.add(int(m.group(1)))
        n_from_masks = (max(frame_ids) + 1) if frame_ids else 0
        for i in range(n_from_masks):
            for suf in ("data", "indices", "indptr"):
                key = "f_%d_%s" % (i, suf)
                if key not in d.files:
                    errors.append("missing %s" % key)
            if H is not None and ("f_%d_indptr" % i) in d.files:
                indptr = d["f_%d_indptr" % i]
                indices = d["f_%d_indices" % i] if ("f_%d_indices" % i) in d.files else np.array([])
                if len(indptr) != H + 1:
                    errors.append("indptr length %d != H+1 for frame %d" % (len(indptr), i))
                if len(indptr) and indptr[0] != 0:
                    errors.append("indptr[0] != 0 for frame %d" % i)
                if len(indptr) and indptr[-1] != len(indices):
                    errors.append("indptr[-1] != len(indices) for frame %d" % i)
                if len(indptr) > 1 and np.any(np.diff(indptr) < 0):
                    errors.append("indptr not non-decreasing for frame %d" % i)
                if W is not None and len(indices) and (indices.min() < 0 or indices.max() >= W):
                    errors.append("indices out of range for frame %d" % i)
    except Exception as e:
        errors.append("masks error: %s" % e)

    if n_from_inst is not None and n_from_masks is not None and n_from_inst != n_from_masks:
        errors.append("frame count mismatch: instructions=%s masks=%s" % (n_from_inst, n_from_masks))
    want = cfg.get("n_frames")
    if want is not None:
        if n_from_inst is not None and n_from_inst != want:
            errors.append("instructions N=%s != expected %s" % (n_from_inst, want))
        if n_from_masks is not None and n_from_masks != want:
            errors.append("masks N=%s != expected %s" % (n_from_masks, want))

    ok = not errors
    print(json.dumps({
        "ok": ok,
        "errors": errors,
        "n_frames": n_from_inst if n_from_inst is not None else n_from_masks,
        "shape": [H, W],
    }))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
