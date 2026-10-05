#!/usr/bin/env python3
"""Deterministic reward-rate assessment for supported credit-card transactions.

Reads one JSON object from stdin and writes one JSON object to stdout. No external
packages, files, network access, or account actions are used.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

BRONZE = "business bronze rewards card"
ECO = "ecocard"
BRONZE_ZERO = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling"
}
BRONZE_SUBSCRIPTION = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"amazon", "walmart", "target", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
POSTED = {"completed", "posted"}


def norm(value):
    return " ".join(str(value or "").casefold().split())


def amount(value):
    # Strip common presentation characters while retaining a conventional decimal.
    raw = str(value).strip().replace("$", "").replace(",", "")
    return Decimal(raw)


def points(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a point value")
    raw = str(value).strip().casefold().replace("points", "").strip()
    parsed = Decimal(raw)
    if parsed != parsed.to_integral_value():
        raise ValueError("recorded rewards must be whole points")
    return int(parsed)


def whole_points(value):
    """Truncate fractional transaction points, matching whole-point storage."""
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def result_base(tx):
    return {
        "transaction_id": tx.get("transaction_id"),
        "card_type": tx.get("credit_card_type"),
        "merchant_name": tx.get("merchant_name"),
    }


def assess(tx):
    out = result_base(tx)
    transaction_id = tx.get("transaction_id")
    if not transaction_id:
        out.update(review_status="needs_review", reason="Missing transaction_id.")
        return out

    card = norm(tx.get("credit_card_type"))
    if card not in {BRONZE, ECO}:
        out.update(review_status="needs_review", reason="Unsupported or missing card type.")
        return out

    status = norm(tx.get("status"))
    if status not in POSTED:
        out.update(
            review_status="not_posted",
            reason="Rewards are assessed only after a transaction is completed or posted.",
        )
        return out

    try:
        spent = amount(tx.get("net_amount", tx.get("transaction_amount")))
        recorded = points(tx.get("rewards_earned"))
    except (InvalidOperation, ValueError, TypeError):
        out.update(
            review_status="needs_review",
            reason="A valid net transaction amount and whole recorded reward-points value are required.",
        )
        return out

    if spent < 0:
        out.update(
            review_status="needs_review",
            reason="A return or credit requires the original transaction rate to verify the reward reversal.",
        )
        return out

    merchant = norm(tx.get("merchant_name"))
    category = norm(tx.get("category"))
    rate = None
    rationale = ""

    if card == BRONZE:
        if merchant in BRONZE_ZERO:
            rate = Decimal("0")
            rationale = "Merchant is excluded from Business Bronze cash back."
        elif merchant in BRONZE_SUBSCRIPTION:
            months = tx.get("subscription_months")
            if months is None:
                out.update(
                    review_status="needs_review",
                    reason="Subscription age is needed to determine whether this SaaS payment is after month 12.",
                )
                return out
            try:
                months = Decimal(str(months))
            except InvalidOperation:
                out.update(review_status="needs_review", reason="subscription_months is not numeric.")
                return out
            if months > 12:
                rate = Decimal("0")
                rationale = "Business Bronze SaaS subscription is after its first 12 months."
            elif months >= 0:
                rate = Decimal("1")
                rationale = "Business Bronze eligible purchase during the first 12 subscription months."
            else:
                out.update(review_status="needs_review", reason="subscription_months cannot be negative.")
                return out
        else:
            rate = Decimal("1")
            rationale = "Business Bronze eligible purchase earns 1.0% cash back (1 point per dollar)."
    else:
        if merchant in ECO_STANDARD:
            rate = Decimal("1")
            rationale = "EcoCard merchant exclusion overrides the green rate."
        elif merchant in ECO_EV_PARTNERS:
            rate = Decimal("5")
            rationale = "Certified EV charging partner earns EcoCard's green rate."
        elif "qualifies_as_green" in tx and tx.get("qualifies_as_green") is not None:
            if isinstance(tx["qualifies_as_green"], bool):
                green = tx["qualifies_as_green"]
            else:
                out.update(review_status="needs_review", reason="qualifies_as_green must be true or false when supplied.")
                return out
            rate = Decimal("5") if green else Decimal("1")
            rationale = "Explicit green-qualification evidence supplied by the transaction source."
        elif category == "green":
            rate = Decimal("5")
            rationale = "Transaction source classified this EcoCard purchase as Green."
        else:
            rate = Decimal("1")
            rationale = "No qualifying green evidence; EcoCard standard rate applies."

    expected = whole_points(spent * rate)
    out.update(
        review_status="evaluated",
        transaction_amount=str(spent),
        applicable_rate_points_per_dollar=str(rate),
        expected_rewards_points=expected,
        recorded_rewards_points=recorded,
        difference_points=expected - recorded,
        expected_redemption_value_usd=format(Decimal(expected) * Decimal("0.01"), ".2f"),
        rationale=rationale,
    )
    return out


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload["transactions"]
        if not isinstance(transactions, list):
            raise ValueError("transactions must be an array")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        json.dump({"error": "Invalid input: " + str(exc), "results": []}, sys.stdout)
        return

    results = []
    for item in transactions:
        if not isinstance(item, dict):
            results.append({
                "transaction_id": None,
                "review_status": "needs_review",
                "reason": "Transaction record must be an object.",
            })
        else:
            results.append(assess(item))

    evaluated = [r for r in results if r.get("review_status") == "evaluated"]
    summary = {
        "input_transaction_count": len(transactions),
        "result_count": len(results),
        "evaluated_count": len(evaluated),
        "likely_under_rewarded_count": sum(r["difference_points"] > 0 for r in evaluated),
        "matched_count": sum(r["difference_points"] == 0 for r in evaluated),
        "higher_than_rules_estimate_count": sum(r["difference_points"] < 0 for r in evaluated),
        "needs_review_count": sum(r.get("review_status") == "needs_review" for r in results),
        "not_posted_count": sum(r.get("review_status") == "not_posted" for r in results),
    }
    json.dump({"results": results, "summary": summary}, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
