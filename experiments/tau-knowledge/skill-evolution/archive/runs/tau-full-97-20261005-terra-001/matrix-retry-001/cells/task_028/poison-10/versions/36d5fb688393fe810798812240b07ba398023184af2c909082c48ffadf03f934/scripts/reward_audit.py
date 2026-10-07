#!/usr/bin/env python3
"""Audit documented credit-card rewards. Reads JSON stdin and writes JSON stdout."""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXACT_ECO_EXCLUSIONS = {"target", "walmart", "amazon", "thredup"}
GREEN_CATEGORIES = {"green", "sustainable"}
POSTED_STATUSES = {"completed", "posted"}
NON_PURCHASE_TERMS = {
    "fee", "fees", "interest", "cash equivalent", "cash equivalents",
    "balance transfer", "balance transfers", "gift card", "gift cards",
    "person-to-person", "p2p", "refund", "returned", "return",
}


def text(value):
    return "" if value is None else str(value).strip()


def normalized(value):
    return text(value).casefold()


def parse_decimal(value, field):
    raw = text(value).replace("$", "").replace(",", "")
    if not raw:
        raise ValueError(f"missing {field}")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid {field}")
    return result


def parse_points(value):
    raw = text(value).casefold().replace("points", "").strip().replace(",", "")
    if not raw:
        raise ValueError("missing rewards_earned")
    try:
        points = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("invalid rewards_earned") from exc
    if not points.is_finite() or points != points.to_integral_value() or points < 0:
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    return int(points)


def floor_points(amount, points_per_dollar):
    return int((amount * points_per_dollar).to_integral_value(rounding=ROUND_FLOOR))


def money_for_points(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), "f")


def is_named_eco_exclusion(merchant):
    return normalized(merchant) in EXACT_ECO_EXCLUSIONS


def is_ev_charging_merchant(merchant):
    name = normalized(merchant)
    return "charg" in name or "supercharger" in name


def is_partner_ev_merchant(merchant):
    name = normalized(merchant)
    return any(partner in name for partner in ("tesla supercharger", "chargepoint", "evgo"))


def classify_rate(tx):
    """Return (kind, points-per-dollar Decimal or None, basis, exactness)."""
    override = tx.get("verified_rate_override")
    if override is not None:
        if not isinstance(override, dict):
            return "inconclusive", None, "invalid verified_rate_override", False
        try:
            rate = parse_decimal(override.get("rate_points_per_dollar"), "verified override rate")
        except ValueError as exc:
            return "inconclusive", None, str(exc), False
        if rate < 0:
            return "inconclusive", None, "verified override rate cannot be negative", False
        reason = text(override.get("reason"))
        if not reason:
            return "inconclusive", None, "verified override requires a documented reason", False
        return "rate", rate, f"verified rate override: {reason}", True

    card = normalized(tx.get("credit_card_type"))
    category = normalized(tx.get("category"))
    merchant = text(tx.get("merchant_name"))

    if card == "crypto-cash back":
        return "rate", Decimal("2"), "Crypto-Cash Back documented 2.0% eligible-purchase rate", True

    if card == "business platinum rewards card":
        if category in {"travel", "software", "media"}:
            return "rate", Decimal("4"), "Business Platinum documented 4.0% category rate", True
        return "rate", Decimal("1.5"), "Business Platinum documented 1.5% other-purchase rate", True

    if card == "silver rewards card":
        if category in {"travel", "software"}:
            return "rate", Decimal("4"), "Silver documented 4.0% posted Travel/Software rate", True
        return "rate", Decimal("1"), "Silver documented at-least-1.0% non-category lower bound", False

    if card == "ecocard":
        if is_named_eco_exclusion(merchant):
            return "rate", Decimal("1"), "EcoCard named merchant exception: standard rate", True
        if is_ev_charging_merchant(merchant) and not is_partner_ev_merchant(merchant):
            return "rate", Decimal("1"), "EcoCard nonpartner EV-charging exception: standard rate", True
        green_eligible = tx.get("green_eligible")
        if green_eligible is False:
            return "rate", Decimal("1"), "EcoCard verified non-green eligibility", True
        if category in GREEN_CATEGORIES or green_eligible is True:
            return "rate", Decimal("5"), "EcoCard qualifying Green/Sustainable rate", True
        return "rate", Decimal("1"), "EcoCard standard other-purchase rate", True

    return "inconclusive", None, f"unsupported card type: {text(tx.get('credit_card_type')) or 'missing'}", False


def has_non_purchase_indicator(tx):
    combined = " ".join(normalized(tx.get(k)) for k in ("category", "merchant_name", "status"))
    return any(term in combined for term in NON_PURCHASE_TERMS)


def audit_one(tx, index):
    if not isinstance(tx, dict):
        return {"input_index": index, "audit_status": "inconclusive", "reason": "transaction must be an object"}

    transaction_id = text(tx.get("transaction_id"))
    base = {"input_index": index, "transaction_id": transaction_id or None}
    if not transaction_id:
        base.update(audit_status="inconclusive", reason="missing transaction_id")
        return base
    if normalized(tx.get("status")) not in POSTED_STATUSES:
        base.update(audit_status="skipped", reason="transaction is not posted/completed")
        return base
    if has_non_purchase_indicator(tx):
        base.update(audit_status="skipped", reason="transaction appears to be excluded, returned, or a nonpurchase item")
        return base

    try:
        amount = parse_decimal(tx.get("transaction_amount"), "transaction_amount")
        recorded = parse_points(tx.get("rewards_earned"))
    except ValueError as exc:
        base.update(audit_status="inconclusive", reason=str(exc))
        return base
    if amount < 0:
        base.update(audit_status="skipped", reason="negative transaction amount requires return/credit review")
        return base

    kind, rate, basis, exact = classify_rate(tx)
    if kind != "rate":
        base.update(audit_status="inconclusive", reason=basis)
        return base

    expected = floor_points(amount, rate)
    difference = expected - recorded
    base.update({
        "card_type": text(tx.get("credit_card_type")),
        "merchant_name": text(tx.get("merchant_name")),
        "category": text(tx.get("category")),
        "transaction_amount": format(amount, "f"),
        "recorded_points": recorded,
        "expected_points": expected,
        "point_difference_expected_minus_recorded": difference,
        "recorded_value_dollars": money_for_points(recorded),
        "expected_value_dollars": money_for_points(expected),
        "rate_points_per_dollar": format(rate, "f"),
        "basis": basis,
        "calculation": f"floor({format(amount, 'f')} × {format(rate, 'f')}) = {expected} points",
    })

    if exact:
        if difference == 0:
            base["audit_status"] = "match"
        else:
            base["audit_status"] = "definite_mismatch"
            base["mismatch_direction"] = "shortfall" if difference > 0 else "overaward"
            base["new_rewards_earned"] = f"{expected} points"
    elif recorded < expected:
        base["audit_status"] = "lower_bound_shortfall"
        base["mismatch_direction"] = "shortfall"
        base["new_rewards_earned"] = f"{expected} points"
    else:
        base["audit_status"] = "lower_bound_only"
        base["reason"] = "recorded points meet the documented minimum; exact non-category Silver rate is not established"
    return base


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")

    audits = [audit_one(tx, i) for i, tx in enumerate(transactions)]
    definite = [a for a in audits if a.get("audit_status") in {"definite_mismatch", "lower_bound_shortfall"}]
    inconclusive = [a for a in audits if a.get("audit_status") in {"inconclusive", "lower_bound_only"}]
    skipped = [a for a in audits if a.get("audit_status") == "skipped"]
    return {
        "audits": audits,
        "definite_discrepancies": definite,
        "inconclusive": inconclusive,
        "skipped": skipped,
        "summary": {
            "transactions_received": len(transactions),
            "matches": sum(a.get("audit_status") == "match" for a in audits),
            "definite_discrepancies": len(definite),
            "inconclusive_or_lower_bound": len(inconclusive),
            "skipped": len(skipped),
        },
    }


if __name__ == "__main__":
    try:
        input_payload = json.load(sys.stdin)
        print(json.dumps(main(input_payload), separators=(",", ":"), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
