"""Deterministic CVSS v3.0/3.1 base-score computation from a vector string.

``base_score_from_vector`` returns a float base score rounded with the CVSS 3.1
roundup rule, or ``None`` if the vector lacks the required base metrics.
``severity_bucket`` maps a numeric score to the CVSS qualitative label.
"""
import math

_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"N": 0.0, "L": 0.22, "H": 0.56}
_PR_U = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_C = {"N": 0.85, "L": 0.68, "H": 0.5}

_REQUIRED = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")


def _roundup(value):
    i = int(round(value * 100000))
    if i % 10000 == 0:
        return i / 100000.0
    return (math.floor(i / 10000.0) + 1) / 10.0


def _parse(vector):
    metrics = {}
    for part in str(vector).split("/"):
        if ":" in part:
            key, val = part.split(":", 1)
            metrics[key] = val
    return metrics


def base_score_from_vector(vector):
    if not vector:
        return None
    m = _parse(vector)
    if not all(k in m for k in _REQUIRED):
        return None
    scope_changed = m["S"] == "C"
    pr_tab = _PR_C if scope_changed else _PR_U
    try:
        iss = 1 - (1 - _CIA[m["C"]]) * (1 - _CIA[m["I"]]) * (1 - _CIA[m["A"]])
        if scope_changed:
            impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)
        else:
            impact = 6.42 * iss
        expl = 8.22 * _AV[m["AV"]] * _AC[m["AC"]] * pr_tab[m["PR"]] * _UI[m["UI"]]
    except KeyError:
        return None
    if impact <= 0:
        return 0.0
    raw = 1.08 * (impact + expl) if scope_changed else (impact + expl)
    return _roundup(min(raw, 10.0))


def severity_bucket(score):
    if score is None:
        return None
    if score == 0:
        return "NONE"
    if score < 4.0:
        return "LOW"
    if score < 7.0:
        return "MEDIUM"
    if score < 9.0:
        return "HIGH"
    return "CRITICAL"
