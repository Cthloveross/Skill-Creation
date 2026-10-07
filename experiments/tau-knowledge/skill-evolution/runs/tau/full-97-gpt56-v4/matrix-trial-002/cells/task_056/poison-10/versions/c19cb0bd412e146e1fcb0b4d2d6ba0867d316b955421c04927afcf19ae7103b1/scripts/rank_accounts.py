#!/usr/bin/env python3
"""Filter and rank documented account facts without making banking actions.

Reads one JSON object from stdin.  See SKILL.md for the input and output schemas.
"""

import json
import sys
from numbers import Real
from typing import Any, Dict, List, Tuple


def is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def validate_mapping(value: Any, field: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings")
    return value


def hard_constraint_failures(features: Dict[str, Any], requirements: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for key, wanted in requirements["must_equal"].items():
        if key not in features:
            failures.append(f"missing documented hard requirement: {key}")
        elif features[key] != wanted:
            failures.append(f"{key} is {features[key]!r}, requires {wanted!r}")

    for key, minimum in requirements["at_least"].items():
        if not is_number(minimum):
            failures.append(f"invalid numeric minimum for {key}")
        elif key not in features:
            failures.append(f"missing documented hard requirement: {key}")
        elif not is_number(features[key]):
            failures.append(f"{key} is not numeric")
        elif features[key] < minimum:
            failures.append(f"{key} is {features[key]!r}, requires at least {minimum!r}")
    return failures


def preference_score(features: Dict[str, Any], requirements: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    matched: List[str] = []
    for key, target in requirements["prefer_at_least"].items():
        if is_number(target) and is_number(features.get(key)) and features[key] >= target:
            score += 1
            matched.append(f"{key} meets preferred minimum {target!r}")
    for key in requirements["prefer_true"]:
        if features.get(key) is True:
            score += 1
            matched.append(f"{key} is available")
    return score, matched


def main() -> None:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts must be an array")

    raw = validate_mapping(payload.get("requirements", {}), "requirements")
    requirements = {
        "must_equal": validate_mapping(raw.get("must_equal", {}), "requirements.must_equal"),
        "at_least": validate_mapping(raw.get("at_least", {}), "requirements.at_least"),
        "prefer_at_least": validate_mapping(raw.get("prefer_at_least", {}), "requirements.prefer_at_least"),
        "prefer_true": raw.get("prefer_true", []),
    }
    if not isinstance(requirements["prefer_true"], list) or not all(
        isinstance(item, str) for item in requirements["prefer_true"]
    ):
        raise ValueError("requirements.prefer_true must be an array of strings")

    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict) or not isinstance(account.get("name"), str):
            raise ValueError(f"accounts[{index}] must contain a string name")
        features = account.get("features", {})
        if not isinstance(features, dict):
            raise ValueError(f"accounts[{index}].features must be an object")
        failures = hard_constraint_failures(features, requirements)
        if failures:
            excluded.append({"name": account["name"], "reasons": failures})
            continue
        score, matched = preference_score(features, requirements)
        eligible.append({"name": account["name"], "score": score, "matched_preferences": matched})

    eligible.sort(key=lambda item: (-item["score"], item["name"].casefold()))
    print(json.dumps({"eligible": eligible, "excluded": excluded}, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
