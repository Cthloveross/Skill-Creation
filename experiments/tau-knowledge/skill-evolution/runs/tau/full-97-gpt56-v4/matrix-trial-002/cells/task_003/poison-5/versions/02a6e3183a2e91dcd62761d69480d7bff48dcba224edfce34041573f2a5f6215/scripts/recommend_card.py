#!/usr/bin/env python3
"""Filter the packaged credit-card catalog against explicit requirements.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the input and output schema.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "card_catalog.json"


def as_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"requirements.{field} must be a number")
    if value < 0:
        raise ValueError(f"requirements.{field} cannot be negative")
    return float(value)


def validate_requirements(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("requirements must be an object")
    allowed = {
        "no_foreign_transaction_fee", "requires_purchase_protection",
        "minimum_protection_days", "minimum_protection_claim_cap",
        "minimum_possible_credit_limit", "maximum_annual_fee",
        "spending_focus", "prefer_highest_general_reward_rate",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError("unsupported requirement fields: " + ", ".join(unknown))
    for field in ("no_foreign_transaction_fee", "requires_purchase_protection",
                  "prefer_highest_general_reward_rate"):
        if field in raw and not isinstance(raw[field], bool):
            raise ValueError(f"requirements.{field} must be a boolean")
    for field in ("minimum_protection_days", "minimum_protection_claim_cap",
                  "minimum_possible_credit_limit", "maximum_annual_fee"):
        if field in raw:
            as_number(raw[field], field)
    if "spending_focus" in raw and not isinstance(raw["spending_focus"], str):
        raise ValueError("requirements.spending_focus must be a string")
    return raw


def evaluate(card: dict[str, Any], req: dict[str, Any]) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    unmet: list[str] = []
    if req.get("no_foreign_transaction_fee"):
        if card.get("foreign_transaction_fee_percent") == 0:
            condition = card.get("foreign_fee_condition")
            if condition:
                reasons.append("0% foreign transaction fee when its documented condition is met")
            else:
                reasons.append("0% foreign transaction fee")
        else:
            unmet.append("does not document a 0% foreign transaction fee")
    if req.get("requires_purchase_protection"):
        if card.get("purchase_protection_days", 0) > 0:
            reasons.append(f"purchase protection for {card['purchase_protection_days']} days")
        else:
            unmet.append("does not document purchase protection")
    checks = [
        ("minimum_protection_days", "purchase_protection_days", "purchase-protection days"),
        ("minimum_protection_claim_cap", "purchase_protection_claim_cap_usd", "purchase-protection claim cap"),
        ("minimum_possible_credit_limit", "typical_credit_limit_max_usd", "maximum typical credit limit"),
    ]
    for requested_field, card_field, label in checks:
        if requested_field not in req:
            continue
        wanted = as_number(req[requested_field], requested_field)
        actual = float(card.get(card_field, -1))
        if actual >= wanted:
            if requested_field == "minimum_possible_credit_limit":
                reasons.append(f"typical limit range reaches ${actual:,.0f}")
        else:
            unmet.append(f"{label} (${actual:,.0f}) is below requested ${wanted:,.0f}")
    if "maximum_annual_fee" in req:
        maximum = as_number(req["maximum_annual_fee"], "maximum_annual_fee")
        actual_fee = float(card.get("annual_fee_usd", 0))
        if actual_fee <= maximum:
            reasons.append(f"annual fee of ${actual_fee:,.2f} is within the stated maximum")
        else:
            unmet.append(f"annual fee (${actual_fee:,.2f}) exceeds stated maximum ${maximum:,.2f}")
    return reasons, unmet


def public_facts(card: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "name", "general_cash_back_percent", "eligible_purchase_scope",
        "foreign_transaction_fee_percent", "foreign_fee_condition", "annual_fee_usd",
        "typical_credit_limit_min_usd", "typical_credit_limit_max_usd",
        "purchase_protection_days", "purchase_protection_claim_cap_usd",
        "minimum_credit_score", "prerequisites", "approval_caveat", "source_notes",
    ]
    return {key: card[key] for key in fields if key in card}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or "requirements" not in payload:
            raise ValueError("input must be an object containing requirements")
        req = validate_requirements(payload["requirements"])
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cards = catalog.get("cards")
        if not isinstance(cards, list):
            raise ValueError("packaged catalog has no cards list")

        eligible: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for card in cards:
            reasons, unmet = evaluate(card, req)
            record = public_facts(card)
            if unmet:
                excluded.append({"name": card.get("name", "Unknown card"), "unmet_requirements": unmet})
            else:
                record["reasons"] = reasons
                record["caveats"] = list(card.get("prerequisites", [])) + [card.get("approval_caveat", "")]
                record["caveats"] = [x for x in record["caveats"] if x]
                eligible.append(record)
        eligible.sort(key=lambda c: (
            -float(c.get("general_cash_back_percent", 0)),
            -float(c.get("typical_credit_limit_max_usd", 0)),
            float(c.get("annual_fee_usd", 0)),
            c["name"],
        ))
        result = {
            "eligible": eligible,
            "excluded": excluded,
            "recommendation": eligible[0] if eligible else None,
            "assumptions": [
                "A typical credit-limit range reaching the requested amount means that amount is possible, not guaranteed; approval and assigned limit depend on underwriting.",
                "The catalog only evaluates documented product terms. Missing information is not treated as a benefit.",
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
