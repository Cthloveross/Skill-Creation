#!/usr/bin/env python3
"""Optimal per-game dice scoring utilities.

MODES (via stdin {"mode": ...}):

1) {"mode": "score", "rounds": [[d,...], ...], "categories": [name, ...]}
   Assign each round to a distinct category to MAXIMIZE total score. Returns the
   optimal total and assignment. Category scoring comes from CATEGORY_SCORERS below
   -- a Yahtzee-style REFERENCE. EDIT these to match the authoritative PDF rules
   before trusting results. len(rounds) must be <= len(categories).

2) {"mode": "selfcheck"}  -- compares exhaustive vs DP optimum on synthetic cases.

stdout: JSON with results. All logic is task-independent; rules are supplied/edited.
"""
import sys, json
from functools import lru_cache
from itertools import permutations
from collections import Counter


# ---- Reference Yahtzee-style category library (ADAPT to the PDF) ----
def _counts(dice):
    return Counter(dice)


def upper(n):
    def f(dice):
        return sum(d for d in dice if d == n)
    return f


def n_of_a_kind(k):
    def f(dice):
        c = _counts(dice)
        return sum(dice) if any(v >= k for v in c.values()) else 0
    return f


def full_house(dice):
    c = sorted(_counts(dice).values())
    return 25 if c == [2, 3] else 0


def small_straight(dice):
    s = set(dice)
    for run in ({1,2,3,4}, {2,3,4,5}, {3,4,5,6}):
        if run <= s:
            return 30
    return 0


def large_straight(dice):
    s = set(dice)
    return 40 if s in ({1,2,3,4,5}, {2,3,4,5,6}) else 0


def yahtzee(dice):
    return 50 if len(set(dice)) == 1 else 0


def chance(dice):
    return sum(dice)


CATEGORY_SCORERS = {
    "ones": upper(1), "twos": upper(2), "threes": upper(3),
    "fours": upper(4), "fives": upper(5), "sixes": upper(6),
    "three_of_a_kind": n_of_a_kind(3), "four_of_a_kind": n_of_a_kind(4),
    "full_house": full_house, "small_straight": small_straight,
    "large_straight": large_straight, "yahtzee": yahtzee, "chance": chance,
}


def build_matrix(rounds, categories):
    mat = []
    for dice in rounds:
        row = []
        for cat in categories:
            scorer = CATEGORY_SCORERS.get(cat)
            row.append(scorer(dice) if scorer else 0)
        mat.append(row)
    return mat


def dp_assign(mat):
    """Max-weight assignment of rounds (rows) to distinct categories (cols).
    DP over used-column bitmask. rows <= cols."""
    R = len(mat)
    if R == 0:
        return 0, []
    C = len(mat[0])
    NEG = float("-inf")

    @lru_cache(maxsize=None)
    def rec(i, used):
        if i == R:
            return 0, ()
        best = NEG
        best_pick = None
        for j in range(C):
            if used & (1 << j):
                continue
            sub, path = rec(i + 1, used | (1 << j))
            val = mat[i][j] + sub
            if val > best:
                best = val
                best_pick = (j,) + path
        return best, best_pick

    total, path = rec(0, 0)
    rec.cache_clear()
    return total, list(path)


def exhaustive_assign(mat):
    R = len(mat)
    if R == 0:
        return 0, []
    C = len(mat[0])
    best = float("-inf")
    best_path = None
    for perm in permutations(range(C), R):
        s = sum(mat[i][perm[i]] for i in range(R))
        if s > best:
            best = s
            best_path = list(perm)
    return best, best_path


def selfcheck():
    import random
    rng = random.Random(0)
    results = []
    ok = True
    for _ in range(50):
        R = rng.randint(1, 6)
        C = rng.randint(R, 7)
        mat = [[rng.randint(0, 50) for _ in range(C)] for _ in range(R)]
        d, _ = dp_assign(mat)
        e, _ = exhaustive_assign(mat)
        agree = (d == e)
        ok = ok and agree
        results.append({"R": R, "C": C, "dp": d, "exh": e, "agree": agree})
    return {"all_agree": ok, "cases": results}


def main():
    req = json.load(sys.stdin)
    mode = req.get("mode", "score")
    if mode == "selfcheck":
        print(json.dumps(selfcheck()))
        return
    if mode == "score":
        rounds = req["rounds"]
        categories = req["categories"]
        mat = build_matrix(rounds, categories)
        total, path = dp_assign(mat)
        assignment = [{"round": i, "category": categories[path[i]],
                       "score": mat[i][path[i]]} for i in range(len(path))]
        print(json.dumps({"total": total, "assignment": assignment,
                          "matrix": mat}))
        return
    print(json.dumps({"error": "unknown_mode", "mode": mode}))


if __name__ == "__main__":
    main()
