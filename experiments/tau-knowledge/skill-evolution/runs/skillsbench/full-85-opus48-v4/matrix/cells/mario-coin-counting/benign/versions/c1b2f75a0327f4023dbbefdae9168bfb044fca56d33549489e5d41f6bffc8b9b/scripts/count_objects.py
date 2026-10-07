#!/usr/bin/env python3
"""Count template instances per frame with grayscale matching + NMS.

stdin: {
  "frames": [paths],
  "templates": {"coins": path, "enemies": path, "turtles": path},
  "thresholds": 0.7 | {"coins": 0.7, ...},
  "scales": [0.5,0.75,1.0,1.25,1.5,2.0],
  "iou": 0.3
}
stdout: {"results": [{"frame": p, <name>: int, ...}, ...]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matching import read_gray, read_template_gray, count_objects  # noqa: E402

DEFAULT_SCALES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def _thr(thresholds, name):
    if isinstance(thresholds, dict):
        return float(thresholds.get(name, 0.7))
    return float(thresholds)


def main():
    cfg = json.load(sys.stdin)
    frames = cfg["frames"]
    templates = cfg["templates"]
    thresholds = cfg.get("thresholds", 0.7)
    scales = cfg.get("scales", DEFAULT_SCALES)
    iou = float(cfg.get("iou", 0.3))

    templ_gray = {name: read_template_gray(path)
                  for name, path in templates.items()}

    results = []
    for fp in frames:
        g = read_gray(fp)
        row = {"frame": fp}
        for name, tg in templ_gray.items():
            row[name] = int(count_objects(g, tg, _thr(thresholds, name),
                                          scales, iou))
        results.append(row)
    json.dump({"results": results}, sys.stdout)


if __name__ == "__main__":
    main()
