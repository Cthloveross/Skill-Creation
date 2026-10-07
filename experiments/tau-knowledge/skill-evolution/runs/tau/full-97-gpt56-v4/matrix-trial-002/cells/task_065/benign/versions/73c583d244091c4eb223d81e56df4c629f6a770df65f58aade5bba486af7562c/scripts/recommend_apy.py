#!/usr/bin/env python3
"""Rank factual savings/APY candidates supplied on stdin.

Input:
{
  "deposit_amount": 6000,
  "currency": "USD",
  "candidates": [{
    "savings_account": "official name",
    "checking_account": "official name or null",
    "minimum_opening": 100,
    "minimum_ongoing": 500,
    "tiers": [{"name": "standard", "apy": 4.0, "min_balance": 0}],
    "checking_bonuses": [{"source": "official checking name", "apy": 0.55}],
    "card_bonuses": [{"source": "held card", "apy": 0.5}],
    "other_bonuses": [{"source": "active documented benefit", "apy": 0.0}]
  }]
}

APY values are percentage points (e.g. 0.55 means +0.55%). The script uses
only the highest supplied checking and card bonus. `other_bonuses` are added
because the caller must include only bonuses proven to stack and be active.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be numeric")
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def best_bonus(entries, field):
    if entries is None:
        return Decimal("0"), None
    if not isinstance(entries, list):
        raise ValueError(f"{field} must be a list")
    best_value, best_source = Decimal("0"), None
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError(f"{field} entries must be objects")
        value = number(item.get("apy", 0), f"{field}.apy")
        if value > best_value:
            best_value = value
            best_source = item.get("source")
    return best_value, best_source


def choose_tier(tiers, amount):
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tiers must be a nonempty list")
    applicable = []
    for tier in tiers:
        if not isinstance(tier, dict):
            raise ValueError("tiers entries must be objects")
        threshold = number(tier.get("min_balance", 0), "tiers.min_balance")
        apy = number(tier.get("apy"), "tiers.apy")
        if threshold <= amount:
            applicable.append((threshold, apy, tier.get("name", "unnamed tier")))
    if not applicable:
        return None
    return max(applicable, key=lambda item: item[0])


def main(payload):
    amount = number(payload.get("deposit_amount"), "deposit_amount")
    if amount <= 0:
        raise ValueError("deposit_amount must be positive")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")

    eligible, ineligible = [], []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("candidate entries must be objects")
        name = candidate.get("savings_account")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each candidate needs savings_account")
        opening = number(candidate.get("minimum_opening", 0), "minimum_opening")
        ongoing = number(candidate.get("minimum_ongoing", 0), "minimum_ongoing")
        reasons = []
        if amount < opening:
            reasons.append(f"deposit is below opening minimum ({opening})")
        if amount < ongoing:
            reasons.append(f"deposit is below ongoing minimum ({ongoing})")
        tier = choose_tier(candidate.get("tiers"), amount)
        if tier is None:
            reasons.append("deposit does not reach a documented APY tier")
        if reasons:
            ineligible.append({"savings_account": name, "checking_account": candidate.get("checking_account"), "reasons": reasons})
            continue
        check_bonus, check_source = best_bonus(candidate.get("checking_bonuses", []), "checking_bonuses")
        card_bonus, card_source = best_bonus(candidate.get("card_bonuses", []), "card_bonuses")
        other_total = Decimal("0")
        other_sources = []
        for item in candidate.get("other_bonuses", []) or []:
            if not isinstance(item, dict):
                raise ValueError("other_bonuses entries must be objects")
            other_total += number(item.get("apy", 0), "other_bonuses.apy")
            if item.get("source"):
                other_sources.append(item["source"])
        effective = tier[1] + check_bonus + card_bonus + other_total
        eligible.append({
            "savings_account": name,
            "checking_account": candidate.get("checking_account"),
            "deposit_amount": str(amount),
            "tier": {"name": tier[2], "min_balance": str(tier[0]), "base_apy": str(tier[1])},
            "highest_checking_bonus": {"apy": str(check_bonus), "source": check_source},
            "highest_card_bonus": {"apy": str(card_bonus), "source": card_source},
            "other_stacking_bonus_total": str(other_total),
            "other_bonus_sources": other_sources,
            "effective_apy": str(effective),
        })
    eligible.sort(key=lambda item: Decimal(item["effective_apy"]), reverse=True)
    best = eligible[0]["effective_apy"] if eligible else None
    return {
        "currency": payload.get("currency", "USD"),
        "eligible": eligible,
        "ineligible": ineligible,
        "highest_effective_apy": best,
        "recommended": [x for x in eligible if x["effective_apy"] == best],
        "warnings": [
            "Only factual active bonuses supplied by the caller were considered.",
            "The result applies the highest supplied checking bonus and highest supplied card bonus; it does not stack bonuses of either type.",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
