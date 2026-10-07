#!/usr/bin/env python3
"""Produce conservative personal cash-back-card advice from JSON stdin."""
import json
import sys
from datetime import date


def normalize_score(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if text in {"", "unknown", "n/a", "none", "not available"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def is_yes(value):
    return str(value).strip().lower() in {"yes", "true", "y", "provided", "included"}


def after_platinum_promo(current_date):
    if not current_date:
        return False
    try:
        return date.fromisoformat(str(current_date)[:10]) > date(2024, 12, 31)
    except ValueError:
        return False


def main(data):
    focus = str(data.get("spending_focus", "general")).strip().lower()
    no_fee = bool(data.get("avoid_annual_fee", True))
    subscription = is_yes(data.get("premium_subscription_access", "unknown"))
    score = normalize_score(data.get("credit_score"))
    current_date = data.get("current_date")
    warnings = []
    alternatives = []
    facts = []

    # Specialized spending changes the lead only when annual card fees are not
    # the customer's controlling requirement. Silver remains useful context.
    if focus == "travel_software" and no_fee:
        recommendation = (
            "For travel and software/SaaS purchases, Silver Rewards Card can be worth "
            "considering because qualifying transactions earn 4.0% back and the card "
            "annual fee is $0. For general purchases outside its top categories, it earns 1.0%."
        )
        card = "Silver Rewards Card"
        eligibility = "eligible_if_score_at_least_680" if score is None or score >= 680 else "score_below_documented_minimum"
        facts.extend(["Silver: $0 annual fee", "Silver: 4.0% qualifying travel/software; 1.0% general", "Silver: minimum score 680"])
        if score is None:
            warnings.append("Silver requires a minimum 680 credit score; the score was not provided, so approval cannot be predicted.")
        elif score < 680:
            warnings.append("The provided score is below Silver's documented 680 minimum.")
    elif no_fee and subscription:
        card = "Gold Rewards Card"
        eligibility = "eligible_if_score_at_least_720" if score is None or score >= 720 else "score_below_documented_minimum"
        recommendation = (
            "Gold Rewards Card is the strongest fit for broad everyday purchases: it has a "
            "$0 card annual fee and earns 2.5% cash back on all purchases. It requires an "
            "active Rho-Bank+ subscription and a minimum 720 credit score."
        )
        facts.extend(["Gold: $0 card annual fee", "Gold: 2.5% on all purchases", "Gold: active Rho-Bank+ and minimum score 720"])
        if score is None:
            warnings.append("Because the credit score is unknown, Gold is a conditional recommendation; underwriting and the 720 minimum determine eligibility.")
        elif score < 720:
            warnings.append("The provided score is below Gold's documented 720 minimum, so Gold is not a realistic current option.")
        alternatives.append("If the 720 minimum is not met, Bronze has a $0 annual fee, requires at least 640, and earns 1.0% on eligible purchases.")
    elif no_fee:
        card = "Bronze Rewards Card"
        eligibility = "eligible_if_score_at_least_640" if score is None or score >= 640 else "score_below_documented_minimum"
        recommendation = (
            "Without confirmed Rho-Bank+ access, Bronze Rewards Card is the straightforward "
            "no-card-annual-fee fallback for general purchases: it earns 1.0% cash back on "
            "eligible purchases and has a 640 minimum credit-score requirement."
        )
        facts.extend(["Bronze: $0 annual fee", "Bronze: 1.0% on eligible purchases", "Bronze: minimum score 640"])
        alternatives.append("Gold is better for general spending at 2.5% with a $0 card annual fee if active Rho-Bank+ access and a 720 minimum score are met.")
    else:
        card = "Gold Rewards Card"
        eligibility = "eligible_if_score_at_least_720"
        recommendation = (
            "For general everyday purchases, compare Gold Rewards Card first: it earns 2.5% "
            "cash back on all purchases with a $0 card annual fee, but requires active "
            "Rho-Bank+ and a minimum 720 credit score."
        )
        facts.extend(["Gold: 2.5% on all purchases", "Gold: $0 card annual fee", "Gold: active Rho-Bank+ and minimum score 720"])

    if after_platinum_promo(current_date):
        warnings.append("The Platinum first-year annual-fee waiver ended December 31, 2024; it should not be treated as available.")
    if score is not None and score < 640:
        warnings.append("The provided score is below the documented 640 minimum for Bronze; no listed no-fee option can be presented as likely eligible.")
    if focus != "travel_software":
        alternatives.append("Silver has a $0 annual fee and 4.0% only on qualifying travel/software purchases; its general-purchase rate outside top categories is 1.0%.")

    return {
        "recommendation": recommendation,
        "recommended_card": card,
        "eligibility_status": eligibility,
        "alternatives": alternatives,
        "warnings": warnings,
        "facts_used": facts,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
