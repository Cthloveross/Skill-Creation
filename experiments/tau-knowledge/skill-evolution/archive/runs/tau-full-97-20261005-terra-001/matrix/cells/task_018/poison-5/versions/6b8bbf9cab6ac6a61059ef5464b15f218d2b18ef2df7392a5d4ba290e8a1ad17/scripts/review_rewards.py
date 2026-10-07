#!/usr/bin/env python3
"""Read-only deterministic credit-card rewards review helper.

Read one JSON object from stdin and write one JSON object to stdout. The schema
is documented in SKILL.md. This program performs no banking-tool calls.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

FINAL_STATUSES = {"completed", "posted"}
BUSINESS_BONUS = {"travel", "software", "media"}
SILVER_BONUS = {"travel", "software"}
ECO_EXCLUDED = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def number(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    text = re.sub(r"\s*points?\s*$", "", str(value).strip(), flags=re.I)
    text = text.replace("$", "").replace(",", "")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not numeric") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return parsed


def points_for(amount, points_per_dollar):
    return int((amount * points_per_dollar).to_integral_value(rounding=ROUND_DOWN))


def dollars_for(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), "f")


def eco_rate(category, merchant):
    merchant_key = norm(merchant)
    if any(merchant_key == x or merchant_key.startswith(x + " ") for x in ECO_EXCLUDED):
        return Decimal("1"), "explicit EcoCard merchant exclusion"
    is_ev = "charg" in merchant_key or "supercharger" in merchant_key
    is_partner = any(x in merchant_key for x in ECO_EV_PARTNERS)
    if is_ev and not is_partner:
        return Decimal("1"), "non-certified EV charging receives the standard EcoCard rate"
    if norm(category) in {"green", "sustainable"}:
        return Decimal("5"), "qualifying Green/Sustainable category"
    return Decimal("1"), "EcoCard standard rate for a non-green purchase"


def determine_rate(tx, silver_base):
    override = tx.get("rate_override_percent")
    if override is not None:
        return number(override, "rate_override_percent"), "verified supplied rate override", "determinate"
    card = norm(tx.get("card_type") or tx.get("credit_card_type"))
    category = norm(tx.get("category"))
    if card == "crypto cash back":
        return Decimal("2"), "Crypto-Cash Back eligible-purchase rate", "determinate"
    if card == "business platinum rewards card":
        if category in {"cash equivalent", "cash equivalents", "balance transfer", "fee", "fees"}:
            return Decimal("0"), "Business Platinum excluded transaction type", "determinate"
        if category in BUSINESS_BONUS:
            return Decimal("4"), "Business Platinum Travel, Software, or Media rate", "determinate"
        return Decimal("1.5"), "Business Platinum other-purchase rate", "determinate"
    if card == "silver rewards card":
        if category in SILVER_BONUS:
            return Decimal("4"), "Silver Travel or Software rate", "determinate"
        if silver_base is not None:
            return silver_base, "supplied exact Silver base rate", "determinate"
        return None, "Silver non-bonus exact base rate is not supplied", "minimum_only"
    if card == "ecocard":
        rate, reason = eco_rate(tx.get("category"), tx.get("merchant_name"))
        return rate, reason, "determinate"
    return None, "no documented rate rule for this card", "unsupported"


def base_result(tx, card, recorded):
    return {
        "transaction_id": tx["transaction_id"],
        "transaction_date": str(tx.get("transaction_date", "")),
        "card_type": card,
        "merchant_name": tx["merchant_name"],
        "category": tx["category"],
        "recorded_rewards_points": str(recorded),
        "recorded_rewards_dollars": dollars_for(recorded),
    }


def review(tx, silver_base):
    required = ("transaction_id", "merchant_name", "category", "transaction_amount", "rewards_earned", "status")
    missing = [key for key in required if tx.get(key) in (None, "")]
    if not (tx.get("card_type") or tx.get("credit_card_type")):
        missing.append("card_type or credit_card_type")
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))
    amount = number(tx["transaction_amount"], "transaction_amount")
    recorded_decimal = number(tx["rewards_earned"], "rewards_earned")
    if recorded_decimal != recorded_decimal.to_integral_value():
        raise ValueError("rewards_earned must contain whole-number points")
    recorded = int(recorded_decimal)
    card = str(tx.get("card_type") or tx.get("credit_card_type"))
    result = base_result(tx, card, recorded)

    if norm(tx["status"]) not in FINAL_STATUSES:
        result.update(state="not_final", reason="transaction is not completed or posted")
        return result
    if tx.get("reward_eligible") is False:
        result.update(state="ineligible_with_rewards" if recorded else "matches",
                      applicable_rate_percent="0", expected_rewards_points="0",
                      expected_rewards_dollars="0.00",
                      reason="transaction independently marked ineligible for rewards")
        if recorded:
            result["recommended_new_rewards_earned"] = "0 points"
        return result

    rate, reason, kind = determine_rate(tx, silver_base)
    if kind == "unsupported":
        result.update(state="unsupported_card", reason=reason)
        return result
    if kind == "minimum_only":
        minimum = points_for(amount, Decimal("1"))
        result.update(applicable_rate_percent="at least 1", minimum_rewards_points=str(minimum),
                      minimum_rewards_dollars=dollars_for(minimum), reason=reason)
        if recorded < minimum:
            result.update(state="under_credited", expected_rewards_points=str(minimum),
                          expected_rewards_dollars=dollars_for(minimum),
                          recommended_new_rewards_earned=f"{minimum} points")
        else:
            result["state"] = "needs_rate_confirmation"
        return result

    expected = points_for(amount, rate)
    result.update(applicable_rate_percent=format(rate, "f"), expected_rewards_points=str(expected),
                  expected_rewards_dollars=dollars_for(expected), reason=reason)
    if recorded == expected:
        result["state"] = "matches"
    elif recorded < expected:
        result.update(state="under_credited", recommended_new_rewards_earned=f"{expected} points")
    else:
        result.update(state="over_credited", recommended_new_rewards_earned=f"{expected} points")
    return result


def customer_line(item):
    if item["state"] not in {"under_credited", "over_credited", "ineligible_with_rewards"}:
        return None
    locator = item["merchant_name"]
    if item.get("transaction_date"):
        locator += " on " + item["transaction_date"]
    expected = item.get("expected_rewards_points", "0")
    expected_dollars = item.get("expected_rewards_dollars", "0.00")
    return (f"{locator} ({item['transaction_id']}): recorded {item['recorded_rewards_points']} points "
            f"(${item['recorded_rewards_dollars']}); calculated {expected} points "
            f"(${expected_dollars}) at {item.get('applicable_rate_percent', '0')} points per dollar. "
            f"Reason: {item['reason']}.")


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object with a transactions array")
        silver_base = None
        if payload.get("silver_base_rate_percent") is not None:
            silver_base = number(payload["silver_base_rate_percent"], "silver_base_rate_percent")
        results, errors, seen = [], [], set()
        for index, tx in enumerate(payload["transactions"]):
            if not isinstance(tx, dict):
                errors.append({"index": index, "error": "transaction must be an object"})
                continue
            transaction_id = tx.get("transaction_id")
            if transaction_id in seen:
                errors.append({"index": index, "transaction_id": transaction_id, "error": "duplicate transaction_id"})
                continue
            seen.add(transaction_id)
            try:
                results.append(review(tx, silver_base))
            except (ValueError, KeyError) as exc:
                errors.append({"index": index, "transaction_id": transaction_id, "error": str(exc)})
        counts = {}
        for item in results:
            counts[item["state"]] = counts.get(item["state"], 0) + 1
        lines = [line for item in results if (line := customer_line(item))]
        print(json.dumps({
            "results": results,
            "summary": {"input_transaction_count": len(payload["transactions"]),
                        "reviewed_transaction_count": len(results), "state_counts": counts,
                        "calculation": "whole points truncated toward zero", "point_value_dollars": "0.01"},
            "customer_report_lines": lines,
            "errors": errors,
        }, indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"results": [], "summary": {}, "customer_report_lines": [], "errors": [{"error": str(exc)}]}))
        sys.exit(2)


if __name__ == "__main__":
    main()
