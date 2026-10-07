"""Shared helpers for grayscale template-match counting.

All functions operate on single-channel uint8 grayscale images so that the
scene and every template pass through the identical image pipeline before
comparison, as the task background requires.
"""
import cv2
import numpy as np


def read_gray(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError("cannot read image: %s" % path)
    return img


def read_template_gray(path):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError("cannot read template: %s" % path)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax + aw, bx + bw)
    iy2 = min(ay + ah, by + bh)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / float(union)


def nms(boxes, scores, iou_thresh=0.3):
    """Greedy non-maximum suppression. Returns kept indices."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    keep = []
    for i in order:
        drop = False
        for k in keep:
            if _iou(boxes[i], boxes[k]) > iou_thresh:
                drop = True
                break
        if not drop:
            keep.append(i)
    return keep


def _resize(templ, scale):
    if abs(scale - 1.0) < 1e-9:
        return templ
    h, w = templ.shape[:2]
    nh = max(1, int(round(h * scale)))
    nw = max(1, int(round(w * scale)))
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    return cv2.resize(templ, (nw, nh), interpolation=interp)


def match_detections(frame_gray, templ_gray, threshold, scales):
    """Return list of (x, y, w, h, score) above threshold across scales."""
    H, W = frame_gray.shape[:2]
    dets = []
    for s in scales:
        t = _resize(templ_gray, s)
        th, tw = t.shape[:2]
        if th > H or tw > W or th < 2 or tw < 2:
            continue
        res = cv2.matchTemplate(frame_gray, t, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= threshold)
        for x, y in zip(xs.tolist(), ys.tolist()):
            dets.append((int(x), int(y), int(tw), int(th), float(res[y, x])))
    return dets


def count_objects(frame_gray, templ_gray, threshold, scales, iou_thresh=0.3):
    dets = match_detections(frame_gray, templ_gray, threshold, scales)
    if not dets:
        return 0
    boxes = [(d[0], d[1], d[2], d[3]) for d in dets]
    scores = [d[4] for d in dets]
    keep = nms(boxes, scores, iou_thresh)
    return len(keep)


def best_peak(frame_gray, templ_gray, scales):
    H, W = frame_gray.shape[:2]
    best = -1.0
    for s in scales:
        t = _resize(templ_gray, s)
        th, tw = t.shape[:2]
        if th > H or tw > W or th < 2 or tw < 2:
            continue
        res = cv2.matchTemplate(frame_gray, t, cv2.TM_CCOEFF_NORMED)
        m = float(res.max())
        if m > best:
            best = m
    return best
