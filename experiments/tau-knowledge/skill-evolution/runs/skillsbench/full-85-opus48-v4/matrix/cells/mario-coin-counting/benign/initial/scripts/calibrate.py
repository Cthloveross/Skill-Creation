#!/usr/bin/env python3
"""Diagnostic: report best match peak per frame per template.

Use to choose thresholds by comparing object peaks vs background responses.
Does not write any task output.

stdin: {"frames": [paths], "templates": {name: path},
        "scales": [...], "top": 5}
stdout: {"peaks": {name: [best_score_per_frame...]},
         "suggested": {name: float}}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matching import read_gray, read_template_gray, best_peak  # noqa: E402

DEFAULT_SCALES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def main():
    cfg = json.load(sys.stdin)
    frames = cfg["frames"]
    templates = cfg["templates"]
    scales = cfg.get("scales", DEFAULT_SCALES)

    peaks = {}
    suggested = {}
    for name, path in templates.items():
        tg = read_template_gray(path)
        vals = [best_peak(read_gray(fp), tg, scales) for fp in frames]
        peaks[name] = vals
        # A simple starting point: midway between the max observed peak and a
        # conservative 0.6 floor. Inspect the distribution before trusting it.
        if vals:
            hi = max(vals)
            suggested[name] = round(max(0.6, 0.6 + 0.4 * (hi - 0.6)), 3)
        else:
            suggested[name] = 0.7
    json.dump({"peaks": peaks, "suggested": suggested}, sys.stdout)


if __name__ == "__main__":
    main()
