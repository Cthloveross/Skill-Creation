#!/usr/bin/env python3
"""Rank normalized account options supplied as JSON on stdin.

The program is deliberately catalog-free: callers provide current terms and
customer preferences. It emits JSON only and performs no banking action.
"""
import json
import sys


def number(value, field, errors, allow_unlimited=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number when supplied")
        return None
    if value < 0 and not (allow_unlimited and value == -1):
        errors.append(f"{field} must be non-negative" + (" or -1" if allow_unlimited else ""))
        return None
    return value


def option_name(option, section, index, errors):
    name = option.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{section}[{index}].name is required")
        return f"Unnamed {section} option {index + 1}"
    return name.strip()


def source_of(option, field, errors):
    source = option.get("source")
    if isinstance(source, str) and source.strip():
        return source.strip()
    errors.append(field + ".source is required so recommendations remain traceable")
    return None


def checking_rank(option, preferences, index, errors):
    name = option_name(option, "checking_options", index, errors)
    prefix = f"checking_options[{index}]"
    reasons, cautions = [], []
    score, fit = 0, True
    travel = preferences.get("international_travel") is True
    want_zero_fx = preferences.get("requires_zero_foreign_transaction_fee") is True
    wants_rebates = preferences.get("needs_atm_rebates") is True
    balance = preferences.get("checking_balance")
    fx_fee = number(option.get("foreign_transaction_fee_percent"), prefix + ".foreign_transaction_fee_percent", errors)
    foreign_atm_fee = number(option.get("foreign_atm_bank_fee"), prefix + ".foreign_atm_bank_fee", errors)
    rebates = number(option.get("atm_rebate_monthly"), prefix + ".atm_rebate_monthly", errors)
    monthly_fee = number(option.get("monthly_fee"), prefix + ".monthly_fee", errors)
    waiver = number(option.get("fee_waiver_minimum_daily_balance"), prefix + ".fee_waiver_minimum_daily_balance", errors)

    if want_zero_fx or travel:
        if fx_fee == 0:
            reasons.append("has a 0% stated foreign transaction fee")
            score += 4
        elif fx_fee is None:
            cautions.append("foreign transaction fee was not supplied")
        else:
            fit = False
            cautions.append(f"has a stated foreign transaction fee of {fx_fee}%")
    if travel:
        if foreign_atm_fee == 0:
            reasons.append("has no stated bank foreign-ATM withdrawal fee")
            score += 3
        elif foreign_atm_fee is None:
            cautions.append("foreign ATM bank fee was not supplied")
        else:
            cautions.append(f"has a stated foreign ATM bank fee of {foreign_atm_fee}")
    if wants_rebates:
        if rebates is not None and rebates > 0:
            reasons.append(f"offers ATM-fee rebates up to {rebates} per month")
            cautions.append("rebates remain subject to the supplied eligibility and monthly-cap terms")
            score += 3
        elif rebates is None:
            cautions.append("ATM rebate cap was not supplied")
        else:
            fit = False
            cautions.append("does not have a supplied positive ATM rebate cap")
    if monthly_fee == 0:
        reasons.append("has no stated monthly maintenance fee")
        score += 2
    elif monthly_fee is not None:
        if balance is not None and waiver is not None:
            if balance >= waiver:
                reasons.append("the stated balance can meet the supplied fee-waiver threshold")
                score += 2
            else:
                cautions.append(f"stated balance is below the supplied fee-waiver threshold of {waiver}; a monthly fee may apply")
                score -= 2
        elif waiver is not None:
            cautions.append(f"monthly fee is conditional on a {waiver} fee-waiver threshold; customer balance is unknown")
        else:
            cautions.append("monthly fee is stated but its waiver condition was not supplied")
    return {"name": name, "score": score, "fit": fit, "reasons": reasons, "cautions": cautions, "source": source_of(option, prefix, errors)}


def savings_rank(option, preferences, index, errors):
    name = option_name(option, "savings_options", index, errors)
    prefix = f"savings_options[{index}]"
    reasons, cautions = [], []
    score, fit = 0, True
    withdrawals = preferences.get("savings_withdrawals_per_month")
    balance = preferences.get("savings_balance")
    requires_no_fee = preferences.get("requires_no_savings_withdrawal_fee") is True
    avoid_maintenance = preferences.get("avoids_savings_maintenance_fee") is True
    requires_daily = preferences.get("requires_daily_compounding") is True
    minimum_apy = preferences.get("minimum_savings_apy")
    wants_atm_rebates = preferences.get("needs_savings_atm_rebates") is True
    free = number(option.get("free_withdrawals_per_month"), prefix + ".free_withdrawals_per_month", errors, allow_unlimited=True)
    withdrawal_limit = number(option.get("withdrawal_limit_per_month"), prefix + ".withdrawal_limit_per_month", errors, allow_unlimited=True)
    opening = number(option.get("opening_deposit_minimum"), prefix + ".opening_deposit_minimum", errors)
    ongoing = number(option.get("ongoing_minimum_balance"), prefix + ".ongoing_minimum_balance", errors)
    maintenance = number(option.get("monthly_fee_below_minimum"), prefix + ".monthly_fee_below_minimum", errors)
    excess = number(option.get("excess_withdrawal_fee"), prefix + ".excess_withdrawal_fee", errors)
    apy = number(option.get("apy"), prefix + ".apy", errors)
    atm_rebates = number(option.get("atm_rebate_monthly"), prefix + ".atm_rebate_monthly", errors)
    daily = option.get("compounds_daily")
    if daily is not None and not isinstance(daily, bool):
        errors.append(prefix + ".compounds_daily must be a boolean when supplied")
        daily = None
    if withdrawals is not None:
        if free == -1:
            reasons.append("has an explicitly unlimited free-withdrawal allowance")
            score += 4
        elif free is not None and withdrawals <= free:
            reasons.append(f"covers the stated maximum of {withdrawals} withdrawals within {free} free withdrawals")
            score += 4
        elif free is not None:
            fit = False if requires_no_fee else fit
            caution = f"stated use of {withdrawals} withdrawals exceeds the supplied free allowance of {free}"
            if excess is not None:
                caution += f"; stated excess-withdrawal fee is {excess}"
            else:
                caution += "; excess-withdrawal fee was not supplied"
            cautions.append(caution)
            score -= 4
        elif withdrawal_limit == -1:
            reasons.append("has an explicitly unlimited permitted-withdrawal limit")
            cautions.append("terms do not state whether withdrawals are fee-free")
        elif withdrawal_limit is not None and withdrawals <= withdrawal_limit:
            reasons.append(f"permits the stated maximum of {withdrawals} withdrawals within a limit of {withdrawal_limit}")
            cautions.append("terms do not state whether withdrawals within that limit are fee-free")
        elif withdrawal_limit is not None:
            fit = False
            cautions.append(f"stated use of {withdrawals} withdrawals exceeds the permitted monthly limit of {withdrawal_limit}")
            score -= 4
        else:
            cautions.append("free withdrawal allowance and permitted withdrawal limit were not supplied")
    if requires_daily:
        if daily is True:
            reasons.append("has stated daily interest compounding")
            score += 2
        elif daily is False:
            fit = False
            cautions.append("does not have stated daily interest compounding")
        else:
            cautions.append("interest compounding frequency was not supplied")
    if minimum_apy is not None:
        if apy is None:
            cautions.append("APY was not supplied")
        elif apy >= minimum_apy:
            reasons.append(f"has a stated APY of {apy}, meeting the requested minimum")
            score += 2
        else:
            fit = False
            cautions.append(f"stated APY of {apy} is below the requested minimum of {minimum_apy}")
    if wants_atm_rebates:
        if atm_rebates is not None and atm_rebates > 0:
            reasons.append(f"offers stated ATM-fee rebates up to {atm_rebates} per month")
            score += 1
        elif atm_rebates == 0:
            fit = False
            cautions.append("does not have a stated positive ATM rebate cap")
        else:
            cautions.append("ATM rebate cap was not supplied")
    if opening is not None:
        cautions.append(f"requires a stated opening deposit of {opening}")
    if ongoing is not None:
        cautions.append(f"has a stated ongoing minimum balance of {ongoing}")
        if balance is not None and balance < ongoing:
            cautions.append(f"stated savings balance is below the ongoing minimum of {ongoing}")
            score -= 2
            if avoid_maintenance and maintenance not in (None, 0):
                fit = False
    if maintenance == 0:
        reasons.append("has no stated monthly maintenance fee")
        score += 1
    elif maintenance is not None:
        cautions.append(f"a monthly maintenance fee of {maintenance} may apply when its balance condition is not met")
    return {"name": name, "score": score, "fit": fit, "reasons": reasons, "cautions": cautions, "source": source_of(option, prefix, errors)}


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc.msg}"}))
        return 2
    if not isinstance(request, dict):
        print(json.dumps({"error": "input must be a JSON object"}))
        return 2
    errors = []
    preferences = request.get("preferences", {})
    if not isinstance(preferences, dict):
        errors.append("preferences must be an object")
        preferences = {}
    for field in ("checking_balance", "savings_withdrawals_per_month", "savings_balance", "minimum_savings_apy"):
        value = number(preferences.get(field), "preferences." + field, errors)
        preferences[field] = value
    checking_options = request.get("checking_options", [])
    savings_options = request.get("savings_options", [])
    if not isinstance(checking_options, list) or not all(isinstance(x, dict) for x in checking_options):
        errors.append("checking_options must be an array of objects")
        checking_options = []
    if not isinstance(savings_options, list) or not all(isinstance(x, dict) for x in savings_options):
        errors.append("savings_options must be an array of objects")
        savings_options = []
    checking = [checking_rank(x, preferences, i, errors) for i, x in enumerate(checking_options)]
    savings = [savings_rank(x, preferences, i, errors) for i, x in enumerate(savings_options)]
    checking.sort(key=lambda x: (not x["fit"], -x["score"], x["name"]))
    savings.sort(key=lambda x: (not x["fit"], -x["score"], x["name"]))
    missing = []
    if checking_options and preferences.get("checking_balance") is None and any(
        option.get("monthly_fee") not in (None, 0) and option.get("fee_waiver_minimum_daily_balance") is not None
        for option in checking_options
    ):
        missing.append("checking_balance is needed to assess conditional fee waivers")
    if savings_options and preferences.get("savings_withdrawals_per_month") is None:
        missing.append("savings_withdrawals_per_month is needed to assess withdrawal-fee fit")
    if savings_options and preferences.get("savings_balance") is None and any(
        option.get("ongoing_minimum_balance") is not None for option in savings_options
    ):
        missing.append("savings_balance is needed to assess ongoing-balance fit")
    if errors:
        print(json.dumps({"error": "validation failed", "details": errors}, sort_keys=True))
        return 2
    print(json.dumps({"checking": checking, "savings": savings, "missing_information": missing}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
