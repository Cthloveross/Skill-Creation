#!/usr/bin/env python3
"""Select a documented, universal everyday cash-back recommendation.

Input JSON:
  {"candidates": [{"name": str, "available": bool,
                   "cash_back_percent": number|string,
                   "universal_everyday": bool, "evidence": str}, ...]}
Output JSON:
  {"status": "ok"|"tie"|"no_qualified_candidate"|"invalid_input", ...}

This helper intentionally ranks only facts supplied by the caller. It does not
perform eligibility decisions, access customer data, or infer missing terms.
"""

import json
import sys
from decimal import Decimal, InvalidOperation

REQUIRED = {"name", "available", "cash_back_percent", "universal_everyday", "evidence"}


def invalid(message):
    return {"status": "invalid_input", "error": message}


def normalize(candidate, index):
    if not isinstance(candidate, dict):
        raise ValueError(f"candidate {index} must be an object")
    missing = REQUIRED - candidate.keys()
    if missing:
        raise ValueError(f"candidate {index} missing fields: {', '.join(sorted(missing))}")
    if not isinstance(candidate["name"], str) or not candidate["name"].strip():
        raise ValueError(f"candidate {index} has an invalid name")
    if not isinstance(candidate["evidence"], str) or not candidate["evidence"].strip():
        raise ValueError(f"candidate {index} has empty evidence")
    if type(candidate["available"]) is not bool or type(candidate["universal_everyday"]) is not bool:
        raise ValueError(f"candidate {index} boolean fields must be true or false")
    try:
        rate = Decimal(str(candidate["cash_back_percent"]))
    except (InvalidOperation, ValueError):
        raise ValueError(f"candidate {index} has an invalid cash_back_percent")
    if not rate.is_finite() or rate < 0:
        raise ValueError(f"candidate {index} has an invalid cash_back_percent")
    return {
        "name": candidate["name"].strip(),
        "available": candidate["available"],
        "universal_everyday": candidate["universal_everyday"],
        "cash_back_percent": rate,
        "evidence": candidate["evidence"].strip(),
    }


def public_candidate(candidate):
    result = dict(candidate)
    result["cash_back_percent"] = format(result["cash_back_percent"], "f")
    return result


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return invalid("input must contain a candidates array")
    try:
        candidates = [normalize(c, i) for i, c in enumerate(payload["candidates"])]
    except ValueError as exc:
        return invalid(str(exc))

    qualified = [c for c in candidates if c["available"] and c["universal_everyday"]]
    qualified.sort(key=lambda c: (-c["cash_back_percent"], c["name"].casefold()))
    response = {"eligible_candidates": [public_candidate(c) for c in qualified]}
    if not qualified:
        response["status"] = "no_qualified_candidate"
        return response

    top_rate = qualified[0]["cash_back_percent"]
    leaders = [c for c in qualified if c["cash_back_percent"] == top_rate]
    if len(leaders) != 1:
        response["status"] = "tie"
        response["tied_candidates"] = [public_candidate(c) for c in leaders]
        return response

    response["status"] = "ok"
    response["recommendation"] = public_candidate(leaders[0])
    return response


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        output = main(raw)
    except json.JSONDecodeError as exc:
        output = invalid(f"invalid JSON: {exc.msg}")
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
