#!/usr/bin/env python3
"""Rank documented savings/checking/card combinations from JSON stdin.

The script is intentionally catalog-driven: callers supply all product facts at
runtime. It performs no banking action and does not decide customer eligibility.
"""

import itertools
import json
import sys


def error(message):
    return {"ok": False, "errors": [message]}


def number(value, field, errors, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append("%s must be a number" % field)
        return None
    value = float(value)
    if minimum is not None and value < minimum:
        errors.append("%s must be at least %s" % (field, minimum))
    return value


def usable(product, allow_unknown):
    if product.get("available", True) is False:
        return False, "unavailable"
    status = product.get("eligible", "unknown")
    if status is True:
        status = "true"
    if status is False:
        status = "false"
    if status not in ("true", "false", "unknown"):
        return False, "invalid eligibility value"
    if status == "false":
        return False, "ineligible"
    if status == "unknown" and not allow_unknown:
        return False, "eligibility unknown"
    return True, None


def boost(product, savings_name):
    boosts = product.get("boosts", product.get("bonuses", {}))
    value = boosts.get(savings_name, 0)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def card_sets(cards, minimum, maximum):
    for size in range(minimum, maximum + 1):
        yield from itertools.combinations(cards, size)


def main(payload):
    if not isinstance(payload, dict):
        return error("input must be a JSON object")
    savings = payload.get("savings")
    checking = payload.get("checking")
    cards = payload.get("cards", [])
    constraints = payload.get("constraints", {})
    if not isinstance(savings, list) or not isinstance(checking, list) or not isinstance(cards, list):
        return error("savings, checking, and cards must be arrays")
    if not isinstance(constraints, dict):
        return error("constraints must be an object")

    errors = []
    balance = number(constraints.get("balance"), "constraints.balance", errors, 0)
    early_required = number(constraints.get("minimum_early_direct_deposit_days", 0),
                            "constraints.minimum_early_direct_deposit_days", errors, 0)
    coverage_required = number(constraints.get("minimum_travel_coverage_limit", 0),
                               "constraints.minimum_travel_coverage_limit", errors, 0)
    if errors:
        return {"ok": False, "errors": errors}

    require_card = bool(constraints.get("require_card", False))
    require_travel = bool(constraints.get("require_travel_insurance", False))
    allow_unknown = bool(constraints.get("allow_unknown_eligibility", True))
    require_ongoing = bool(constraints.get("require_ongoing_minimum", True))
    max_cards = constraints.get("max_cards", 1)
    if isinstance(max_cards, bool) or not isinstance(max_cards, int) or max_cards < 0:
        return error("constraints.max_cards must be a non-negative integer")
    if require_card and max_cards == 0:
        return error("max_cards cannot be zero when require_card is true")

    names = set()
    for group_name, group in (("savings", savings), ("checking", checking), ("cards", cards)):
        for index, product in enumerate(group):
            if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
                errors.append("%s[%d] requires a nonempty name" % (group_name, index))
            elif (group_name, product["name"]) in names:
                errors.append("duplicate %s name: %s" % (group_name, product["name"]))
            else:
                names.add((group_name, product["name"]))
    if errors:
        return {"ok": False, "errors": errors}

    rejected = {}
    plans = []
    min_cards = 1 if require_card else 0
    max_cards = min(max_cards, len(cards))

    for saving in savings:
        ok, why = usable(saving, allow_unknown)
        if not ok:
            rejected["savings_" + why] = rejected.get("savings_" + why, 0) + 1
            continue
        base = number(saving.get("base_apy"), "savings.base_apy", errors, 0)
        opening = number(saving.get("opening_minimum", 0), "savings.opening_minimum", errors, 0)
        ongoing = number(saving.get("ongoing_minimum", 0), "savings.ongoing_minimum", errors, 0)
        if errors:
            return {"ok": False, "errors": errors}
        if balance < opening:
            rejected["below_opening_minimum"] = rejected.get("below_opening_minimum", 0) + 1
            continue
        if require_ongoing and balance < ongoing:
            rejected["below_ongoing_minimum"] = rejected.get("below_ongoing_minimum", 0) + 1
            continue

        for check in checking:
            ok, why = usable(check, allow_unknown)
            if not ok:
                rejected["checking_" + why] = rejected.get("checking_" + why, 0) + 1
                continue
            early_days = check.get("early_direct_deposit_days", 0)
            if isinstance(early_days, bool) or not isinstance(early_days, (int, float)):
                early_days = 0
            early_days = float(early_days)
            if early_days < early_required:
                rejected["early_direct_deposit_requirement"] = rejected.get("early_direct_deposit_requirement", 0) + 1
                continue
            check_boost = boost(check, saving["name"])

            for selected in card_sets(cards, min_cards, max_cards):
                card_reasons = []
                for card in selected:
                    card_ok, card_why = usable(card, allow_unknown)
                    if not card_ok:
                        card_reasons.append(card_why)
                if card_reasons:
                    reason = "card_" + card_reasons[0]
                    rejected[reason] = rejected.get(reason, 0) + 1
                    continue
                insured = [card for card in selected if card.get("travel_insurance", False) is True]
                if require_travel and not insured:
                    rejected["travel_insurance_requirement"] = rejected.get("travel_insurance_requirement", 0) + 1
                    continue
                if require_travel and coverage_required > 0:
                    if not any(isinstance(card.get("travel_coverage_limit", 0), (int, float)) and
                               not isinstance(card.get("travel_coverage_limit", 0), bool) and
                               float(card.get("travel_coverage_limit", 0)) >= coverage_required
                               for card in insured):
                        rejected["travel_coverage_limit_requirement"] = rejected.get("travel_coverage_limit_requirement", 0) + 1
                        continue
                bonuses = [boost(card, saving["name"]) for card in selected]
                card_boost = max(bonuses) if bonuses else 0.0
                uncertainty = []
                for product in (saving, check) + selected:
                    if product.get("eligible", "unknown") == "unknown":
                        uncertainty.append(product["name"] + ": eligibility must be confirmed")
                conditions = []
                for card in insured:
                    for condition in card.get("travel_coverage_conditions", []):
                        if isinstance(condition, str) and condition not in conditions:
                            conditions.append(condition)
                plans.append({
                    "savings": saving["name"],
                    "checking": check["name"],
                    "cards": [card["name"] for card in selected],
                    "apy": round(base + check_boost + card_boost, 6),
                    "apy_components": {
                        "base_apy": base,
                        "selected_checking_boost": check_boost,
                        "selected_card_bonus": card_boost,
                        "checking_boost_policy": "highest applicable checking boost only",
                        "card_bonus_policy": "highest applicable card bonus only"
                    },
                    "balance_checks": {
                        "balance": balance,
                        "opening_minimum": opening,
                        "ongoing_minimum": ongoing,
                        "ongoing_minimum_required": require_ongoing
                    },
                    "early_direct_deposit_days": early_days,
                    "travel_coverage_conditions": conditions,
                    "uncertainties": uncertainty
                })

    plans.sort(key=lambda p: (-p["apy"], -p["early_direct_deposit_days"], len(p["cards"]),
                              p["savings"], p["checking"], ",".join(p["cards"])))
    return {
        "ok": True,
        "recommended": plans[0] if plans else None,
        "alternatives": plans[:10],
        "plan_count": len(plans),
        "rejected_summary": rejected,
        "policy": {
            "checking_boosts": "Only the highest applicable checking boost is included.",
            "card_bonuses": "Only the highest applicable card bonus is included.",
            "cross_type_stacking": "The selected checking boost and selected card bonus are added to base APY."
        },
        "next_step": "Confirm eligibility and obtain explicit authorization before any account, transfer, closure, or card-application action."
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["invalid JSON input: " + str(exc)]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["planner failed: " + str(exc)]}))
