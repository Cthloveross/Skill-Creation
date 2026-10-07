#!/usr/bin/env python3
"""Pair games into consecutive head-to-head matches and count wins.

stdin:  {"games": [{"number": int, "score": number}, ...], "tie": "none|p1|p2"}

Games are sorted by `number`, then paired (first two, next two, ...). Within each
pair the lower game number is Player 1 (odd), the higher is Player 2 (even). The
higher score wins that match. Tie policy: "none" (default) credits neither player;
"p1"/"p2" force the tie to that player (only if the rules say so).

stdout: {"p1_wins", "p2_wins", "ties", "matches", "difference"}
where difference = p1_wins - p2_wins (Player 1 minus Player 2, per the question).
"""
import sys, json


def main():
    req = json.load(sys.stdin)
    games = sorted(req["games"], key=lambda g: g["number"])
    tie = req.get("tie", "none")
    p1 = p2 = ties = matches = 0
    for i in range(0, len(games) - 1, 2):
        a = games[i]      # lower number -> Player 1
        b = games[i + 1]  # higher number -> Player 2
        matches += 1
        sa, sb = a["score"], b["score"]
        if sa > sb:
            p1 += 1
        elif sb > sa:
            p2 += 1
        else:
            ties += 1
            if tie == "p1":
                p1 += 1
            elif tie == "p2":
                p2 += 1
    print(json.dumps({"p1_wins": p1, "p2_wins": p2, "ties": ties,
                      "matches": matches, "difference": p1 - p2}))


if __name__ == "__main__":
    main()
