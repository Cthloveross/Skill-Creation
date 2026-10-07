#!/usr/bin/env python3
"""Align known chapter titles to transcript timestamps under a global monotonic
constraint.

stdin JSON: {"transcript":[{"start":float,"end":float,"text":str}],
             "chapters":["title", ...], "duration": float,
             "lookahead": int (optional), "pos_weight": float (optional)}
stdout JSON: {"chapters":[{"time":int,"title":str}], "warnings":[...]}
"""
import json
import re
import sys
from difflib import SequenceMatcher

STOPWORDS = set("""
a an the of to in on at for and or but with without into onto from by as is are
be been being was were do does did doing done we you i it its it's we'll you'll
our your their this that these those how what why when where which who whom here
there now next then let lets let's going go get getting got make made making
all out up off over under about into set setting start starts started begin
if need needs needed great job thing things way ways some any more most part
""".split())


def normalize_words(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [w for w in text.split() if w]


def content_words(title):
    words = normalize_words(title)
    content = [w for w in words if w not in STOPWORDS and len(w) > 1]
    # keep at least something to match on for very short titles
    return content if content else words


def fuzzy(a, b):
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def window_text(segments, j, lookahead):
    parts = []
    for k in range(j, min(len(segments), j + lookahead + 1)):
        parts.append(segments[k].get("text", ""))
    return " ".join(parts)


def score_matrix(segments, chapters, lookahead):
    seg_words = [set(normalize_words(window_text(segments, j, lookahead)))
                 for j in range(len(segments))]
    scores = []
    for title in chapters:
        cw = content_words(title)
        row = []
        for j in range(len(segments)):
            words = seg_words[j]
            if not cw:
                row.append(0.0)
                continue
            total = 0.0
            matched = 0
            for w in cw:
                best = 0.0
                for sw in words:
                    r = fuzzy(w, sw)
                    if r > best:
                        best = r
                        if best >= 0.999:
                            break
                if best >= 0.8:
                    matched += 1
                total += best
            frac = total / len(cw)
            # reward both average similarity and count of strong matches
            row.append(frac + 0.25 * (matched / len(cw)))
        scores.append(row)
    return scores


def monotonic_dp(scores, segments, duration, pos_weight):
    n = len(scores)
    m = len(scores[0]) if scores else 0
    if m < n or m == 0:
        return None
    seg_start = [segments[j].get("start", 0.0) for j in range(m)]
    # positional prior bonus added into score
    adj = [[0.0] * m for _ in range(n)]
    for i in range(n):
        target = (i / (n - 1)) * duration if n > 1 else 0.0
        for j in range(m):
            prior = 1.0 - min(1.0, abs(seg_start[j] - target) / max(duration, 1.0))
            adj[i][j] = scores[i][j] + pos_weight * prior

    NEG = float("-inf")
    dp = [[NEG] * m for _ in range(n)]
    back = [[-1] * m for _ in range(n)]
    for j in range(m):
        dp[0][j] = adj[0][j]
    for i in range(1, n):
        best_prev = NEG
        best_k = -1
        for j in range(m):
            # best among k < j for previous row
            if j - 1 >= 0 and dp[i - 1][j - 1] > best_prev:
                best_prev = dp[i - 1][j - 1]
                best_k = j - 1
            if best_prev == NEG:
                continue
            dp[i][j] = adj[i][j] + best_prev
            back[i][j] = best_k
    # pick best end
    best_j = max(range(m), key=lambda j: dp[n - 1][j])
    idx = [0] * n
    j = best_j
    for i in range(n - 1, -1, -1):
        idx[i] = j
        j = back[i][j]
        if j < 0 and i > 0:
            # shouldn't happen, guard
            j = i - 1
    return [seg_start[k] for k in idx]


def repair_monotonic(times, duration):
    """Force first=0, strictly increasing integers, within [0,duration)."""
    n = len(times)
    out = [int(round(t)) for t in times]
    out[0] = 0
    # forward pass: strictly increasing
    for i in range(1, n):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + 1
    # clamp to duration-1 (keep strictly < duration)
    cap = max(n - 1, int(duration) - 1)
    cap = int(duration) - 1
    if out[-1] > cap:
        # backward compress to fit
        out[-1] = cap
        for i in range(n - 2, -1, -1):
            if out[i] >= out[i + 1]:
                out[i] = out[i + 1] - 1
        out[0] = 0
        # if compression pushed early values negative, spread evenly
        if any(out[i] <= out[i - 1] for i in range(1, n)) or out[0] != 0:
            step = (int(duration) - 1) / max(n - 1, 1)
            out = [int(round(i * step)) for i in range(n)]
            out[0] = 0
            for i in range(1, n):
                if out[i] <= out[i - 1]:
                    out[i] = out[i - 1] + 1
    return out


def even_spacing(chapters, duration):
    n = len(chapters)
    step = (int(duration) - 1) / max(n - 1, 1)
    out = [int(round(i * step)) for i in range(n)]
    out[0] = 0
    for i in range(1, n):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + 1
    return out


def run(cfg):
    segments = cfg.get("transcript", [])
    chapters = cfg["chapters"]
    duration = float(cfg["duration"])
    lookahead = int(cfg.get("lookahead", 1))
    pos_weight = float(cfg.get("pos_weight", 0.15))
    warnings = []

    times = None
    if len(segments) >= len(chapters):
        scores = score_matrix(segments, chapters, lookahead)
        times = monotonic_dp(scores, segments, duration, pos_weight)
    if times is None:
        warnings.append(
            "Insufficient transcript segments for alignment; using even spacing.")
        times = even_spacing(chapters, duration)

    times = repair_monotonic(times, duration)
    result = {"chapters": [{"time": times[i], "title": chapters[i]}
                           for i in range(len(chapters))],
              "warnings": warnings}
    return result


if __name__ == "__main__":
    cfg = json.load(sys.stdin)
    print(json.dumps(run(cfg)))
