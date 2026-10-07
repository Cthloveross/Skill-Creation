#!/usr/bin/env python3
"""Conservatively match documented credit-card terms to customer constraints.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the input and output schemas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PACKAGE_ROOT / "references" / "card_catalog.json"


def load_catalog(path_value: Any) -> list[dict[str, Any]]:
    if path_value is None:
        path = DEFAULT_CATALOG
    elif isinstance(path_value, str) and path_value:
        candidate = Path(path_value)
        path = candidate if candidate.is_absolute() else PACKAGE_ROOT / candidate
    else:
        raise ValueError("catalog_path must be a nonempty string when provided")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("catalog must be a JSON array of card objects")
    return data


def numeric(value: Any, name: str, issues: list[str]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.append(f"{name} must be numeric")
        return None
    value = float(value)
    if value < 0:
        issues.append(f"{name} cannot be negative")
        return None
    return value


def boolean(value: Any, name: str, issues: list[str]) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        issues.append(f"{name} must be boolean")
        return None
    return value


def evaluate(card: dict[str, Any], requirements: dict[str, Any], applicant: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (documented conflicts, missing evidence)."""
    conflicts: list[str] = []
    unknown: list[str] = []
    name = str(card.get("name", "unnamed card"))

    checks = (
        ("max_foreign_transaction_fee_percent", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment_percent", "minimum payment"),
    )
    for requested_key, card_key, label in checks:
        maximum = requirements.get(requested_key)
        if maximum is None:
            continue
        actual = card.get(card_key)
        if actual is None:
            unknown.append(f"{name}: documented {label} is unavailable")
        elif float(actual) > float(maximum):
            conflicts.append(f"{name}: {label} is {actual}%, above requested maximum {maximum}%")

    virtual_needed = requirements.get("requires_virtual_card_management")
    if virtual_needed is not None:
        actual_virtual = card.get("virtual_card_management")
        if actual_virtual is None:
            unknown.append(f"{name}: virtual-card-management availability is undocumented")
        elif actual_virtual != virtual_needed:
            conflicts.append(f"{name}: virtual-card management is documented as {actual_virtual}")

    score = applicant.get("credit_score")
    if score is not None:
        minimum_score = card.get("minimum_credit_score")
        if minimum_score is None:
            unknown.append(f"{name}: minimum credit score is undocumented")
        elif float(score) < float(minimum_score):
            conflicts.append(f"{name}: minimum credit score is {minimum_score}, above applicant score {score}")

    has_subscription = applicant.get("has_rho_bank_plus")
    subscription_required = card.get("rho_bank_plus_required")
    if subscription_required is True:
        if has_subscription is None:
            unknown.append(f"{name}: Rho-Bank+ status is needed")
        elif has_subscription is False:
            conflicts.append(f"{name}: requires an active Rho-Bank+ subscription")
    # A customer subscription fact does not require a filter for cards without
    # a documented subscription prerequisite.
    return conflicts, unknown


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        requirements = payload.get("requirements", {})
        applicant = payload.get("applicant", {})
        if not isinstance(requirements, dict) or not isinstance(applicant, dict):
            raise ValueError("requirements and applicant must be JSON objects")

        issues: list[str] = []
        for key in ("max_foreign_transaction_fee_percent", "max_minimum_payment_percent"):
            requirements[key] = numeric(requirements.get(key), key, issues)
        applicant["credit_score"] = numeric(applicant.get("credit_score"), "credit_score", issues)
        requirements["requires_virtual_card_management"] = boolean(
            requirements.get("requires_virtual_card_management"),
            "requires_virtual_card_management", issues,
        )
        applicant["has_rho_bank_plus"] = boolean(
            applicant.get("has_rho_bank_plus"), "has_rho_bank_plus", issues,
        )
        if issues:
            print(json.dumps({"confirmed_matches": [], "possible_but_unconfirmed": [], "excluded": [], "input_issues": issues}))
            return

        catalog = load_catalog(payload.get("catalog_path"))
        confirmed: list[dict[str, Any]] = []
        possible: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for card in catalog:
            conflicts, unknown = evaluate(card, requirements, applicant)
            result = {"name": card.get("name"), "source_document_id": card.get("source_document_id"), "terms": card, "reasons": conflicts or unknown}
            if conflicts:
                excluded.append(result)
            elif unknown:
                possible.append(result)
            else:
                confirmed.append(result)
        print(json.dumps({
            "confirmed_matches": confirmed,
            "possible_but_unconfirmed": possible,
            "excluded": excluded,
            "input_issues": [],
        }, ensure_ascii=False))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"confirmed_matches": [], "possible_but_unconfirmed": [], "excluded": [], "input_issues": [str(exc)]}))


if __name__ == "__main__":
    main()
