#!/usr/bin/env python3
"""Solve a linear system for unknown (placeholder) variables.

stdin:  {"equations": [{"terms": {"var": coeff, ...}, "const": number}],
         "knowns": {"var": value, ...}}
        Each equation means sum(coeff*var) == const.
stdout: {"solution": {var: value}, "unique": bool, "residual": number}
"""
import sys, json


def main():
    req = json.load(sys.stdin)
    equations = req.get("equations", [])
    knowns = req.get("knowns", {}) or {}

    import numpy as np

    # Collect unknown variable names (anything not in knowns).
    unknowns = []
    seen = set()
    for eq in equations:
        for v in eq.get("terms", {}):
            if v not in knowns and v not in seen:
                seen.add(v)
                unknowns.append(v)

    if not unknowns:
        json.dump({"solution": {}, "unique": True, "residual": 0.0}, sys.stdout)
        sys.stdout.write("\n")
        return

    idx = {v: i for i, v in enumerate(unknowns)}
    rows = []
    b = []
    for eq in equations:
        terms = eq.get("terms", {})
        const = float(eq.get("const", 0.0))
        row = [0.0] * len(unknowns)
        rhs = const
        for v, coeff in terms.items():
            coeff = float(coeff)
            if v in knowns:
                rhs -= coeff * float(knowns[v])
            else:
                row[idx[v]] += coeff
        rows.append(row)
        b.append(rhs)

    A = np.array(rows, dtype=float)
    bb = np.array(b, dtype=float)
    sol, residuals, rank, sv = np.linalg.lstsq(A, bb, rcond=None)
    unique = rank >= len(unknowns)
    resid = float(np.linalg.norm(A.dot(sol) - bb))
    solution = {v: float(sol[idx[v]]) for v in unknowns}
    json.dump({"solution": solution, "unique": bool(unique),
               "residual": resid}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
