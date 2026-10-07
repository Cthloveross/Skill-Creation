#!/usr/bin/env python3
"""Convert frames to grayscale in place (overwrite originals).

stdin:  {"frames": [paths]}
stdout: {"converted": [paths], "all_grayscale": bool, "shapes": [[h,w,...]]}
"""
import json
import sys

import cv2


def main():
    cfg = json.load(sys.stdin)
    frames = cfg["frames"]
    converted = []
    shapes = []
    all_gray = True
    for p in frames:
        img = cv2.imread(p, cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError("cannot read frame: %s" % p)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if not cv2.imwrite(p, gray):
            raise IOError("failed to overwrite %s" % p)
        check = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        shapes.append(list(check.shape))
        if check.ndim != 2:
            all_gray = False
        converted.append(p)
    json.dump({"converted": converted, "all_grayscale": all_gray,
               "shapes": shapes}, sys.stdout)


if __name__ == "__main__":
    main()
