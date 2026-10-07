#!/usr/bin/env python3
"""Rank evidence-supplied checking and savings products for an advisory reply.

Input JSON schema:
{
  "profile": {
    "international_travel": bool, "frequent_foreign_atm_use": bool,
    "foreign_currency_purchases": bool, "desired_currency_holding": bool,
    "reliable_daily_checking_balance": number|null,
    "interested_in_eco_savings": bool, "savings_priority": str|null,
    "expected_savings_balance": number|null
  },
  "catalog": {
    "checking": [{
      "name": str, "monthly_fee": number|null,
      "fee_waiver_daily_balance": number|null,
      "opening_deposit": number|null, "benefit_daily_balance": number|null,
      "foreign_transaction_fee_percent": number|null,
      "foreign_atm_bank_fee": number|null,
      "atm_operator_rebate_cap_monthly": number|null,
      "currency_conversion_markup_percent": number|null,
      "multi_currency_wallet": bool|null, "wallet_currencies": number|null
    }],
    "savings": [{
      "name": str, "apy_percent": number|null, "opening_deposit": number|null,
      "ongoing_minimum_balance": number|null, "monthly_fee": number|null,
      "eco_features": [str], "paperless_required": bool|null,
      "free_withdrawals_per_month": number|null
    }]
  }
}

Output JSON contains ranked choices and disclosure prompts. It intentionally does
not invent products or source facts omitted from the supplied catalogue.
"""
import json
import sys


def n(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def fits_balance(product, balance):
    required = n(product.get("benefit_daily_balance"))
    if required is None:
        required = n(product.get("fee_waiver_daily_balance"))
    if balance is None or required is None:
        return None
    return balance >= required


def score_checking(product, profile):
    score = 0
    reasons = []
    warnings = []
    balance = n(profile.get("reliable_daily_checking_balance"))
    feasible = fits_balance(product, balance)
    opening = n(product.get("opening_deposit"))
    benefit = n(product.get("benefit_daily_balance"))

    if opening is not None and balance is not None and opening > balance:
        return -10000, ["opening-deposit requirement exceeds stated available balance"], ["not suitable based on stated funds"]
    if benefit is not None and balance is not None and benefit > balance:
        return -10000, ["ongoing benefit-balance requirement exceeds stated reliable balance"], ["not suitable based on stated funds"]
    if feasible is False:
        warnings.append("Customer may not meet the stated balance threshold reliably.")
        score -= 20
    elif feasible is True:
        score += 4
        reasons.append("stated balance meets the documented daily-balance threshold")

    travel = bool(profile.get("international_travel"))
    if travel or profile.get("foreign_currency_purchases"):
        ftx = n(product.get("foreign_transaction_fee_percent"))
        if ftx == 0:
            score += 12
            reasons.append("has a 0% foreign transaction fee")
        elif ftx is not None:
            score -= 8
            warnings.append("foreign transaction fee is not 0%")
    if travel or profile.get("frequent_foreign_atm_use"):
        atm_fee = n(product.get("foreign_atm_bank_fee"))
        if atm_fee == 0:
            score += 12
            reasons.append("has a $0 bank foreign-ATM withdrawal fee")
        elif atm_fee is not None:
            score -= 8
            warnings.append("charges a bank fee for foreign ATM withdrawals")
        rebate = n(product.get("atm_operator_rebate_cap_monthly"))
        if rebate is not None and rebate > 0:
            score += 7
            reasons.append("offers a capped monthly operator-fee rebate")
            warnings.append("ATM operator surcharges remain separate and rebates are capped monthly")
    if profile.get("desired_currency_holding"):
        if product.get("multi_currency_wallet") is True:
            score += 10
            count = n(product.get("wallet_currencies"))
            reasons.append("includes a multi-currency wallet" + (f" supporting {count:g} currencies" if count is not None else ""))
        else:
            score -= 5
            warnings.append("no supported multi-currency wallet is documented")
    markup = n(product.get("currency_conversion_markup_percent"))
    if markup is not None and (travel or profile.get("foreign_currency_purchases")):
        warnings.append(f"documented currency conversion markup: {markup:g}% above the interbank rate")
    fee = n(product.get("monthly_fee"))
    waive = n(product.get("fee_waiver_daily_balance"))
    if fee is not None and fee > 0:
        if waive is not None and feasible is True:
            warnings.append(f"monthly fee is waived only while the daily balance stays at least {waive:g}")
        else:
            warnings.append(f"monthly fee: {fee:g}")
    return score, reasons, warnings


def score_savings(product, profile):
    score = 0
    reasons = []
    warnings = []
    expected = n(profile.get("expected_savings_balance"))
    minimum = n(product.get("ongoing_minimum_balance"))
    opening = n(product.get("opening_deposit"))
    if expected is not None and minimum is not None and expected < minimum:
        score -= 50
        warnings.append("expected savings balance is below the ongoing minimum")
    apy = n(product.get("apy_percent"))
    priority = (profile.get("savings_priority") or "").lower()
    if apy is not None:
        score += 6 if priority in ("highest apy", "yield", "highest yield") else 2
        reasons.append(f"documented APY: {apy:g}%")
    if product.get("eco_features") and profile.get("interested_in_eco_savings"):
        score += 8
        reasons.append("has documented eco-focused features")
    fee = n(product.get("monthly_fee"))
    if fee == 0:
        score += 3
        reasons.append("has no documented monthly maintenance fee")
    elif fee is not None:
        warnings.append(f"monthly fee: {fee:g}")
    if opening is not None:
        warnings.append(f"opening deposit requirement: {opening:g}")
    if minimum is not None:
        warnings.append(f"ongoing minimum balance: {minimum:g}")
    if product.get("paperless_required") is True:
        warnings.append("paperless statements are required")
    return score, reasons, warnings


def rank(items, scorer, profile):
    output = []
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        score, reasons, warnings = scorer(item, profile)
        output.append({"name": item["name"], "score": score, "reasons": reasons, "warnings": warnings})
    return sorted(output, key=lambda x: (-x["score"], x["name"]))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc.msg}"}))
        return
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    catalog = data.get("catalog") if isinstance(data.get("catalog"), dict) else {}
    checking = rank(catalog.get("checking", []), score_checking, profile)
    savings = rank(catalog.get("savings", []), score_savings, profile)
    missing = []
    if not profile.get("savings_priority"):
        missing.append("Savings priority is not stated (yield, low minimum/fees, or access).")
    if n(profile.get("expected_savings_balance")) is None:
        missing.append("Expected savings balance is not stated.")
    errors = []
    if not checking:
        errors.append("No usable checking products were supplied in the catalogue.")
    if not savings:
        errors.append("No usable savings products were supplied in the catalogue.")
    warnings = []
    if checking:
        warnings.extend(checking[0]["warnings"])
    if savings:
        warnings.extend(savings[0]["warnings"])
    print(json.dumps({
        "checking": checking,
        "savings": savings,
        "missing_information": missing,
        "warnings": list(dict.fromkeys(warnings)),
        "validation_errors": errors
    }, indent=2))


if __name__ == "__main__":
    main()
