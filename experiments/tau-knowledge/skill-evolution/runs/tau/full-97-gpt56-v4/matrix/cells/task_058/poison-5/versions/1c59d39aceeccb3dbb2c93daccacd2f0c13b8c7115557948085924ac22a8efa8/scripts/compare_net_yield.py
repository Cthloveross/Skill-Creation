#!/usr/bin/env python3
"""Rank documented savings/card combinations for constant-balance net yield.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. This program is advisory and performs no banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
ZERO = Decimal("0")
HUNDRED = Decimal("100")
DAYS_IN_YEAR = Decimal("365")
CENT = Decimal("0.01")


def dec(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a finite number")
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite number")
    return number


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def pct(value):
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def index_bonuses(entries, key_field, target_name):
    return [entry for entry in entries if entry.get(key_field) == target_name]


def best_entry(entries):
    if not entries:
        return None
    return max(entries, key=lambda item: dec(item.get("apy_percent", 0), "apy_percent"))


def selected_tier(savings, deposit):
    tiers = savings.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError(f"savings {savings.get('name', '<unnamed>')} needs nonempty tiers")
    usable = []
    for tier in tiers:
        threshold = dec(tier.get("minimum_balance"), "tier.minimum_balance")
        apy = dec(tier.get("apy_percent"), "tier.apy_percent")
        if threshold < ZERO or apy < ZERO:
            raise ValueError("tier thresholds and APYs cannot be negative")
        if threshold <= deposit:
            usable.append((threshold, apy))
    if not usable:
        return None
    return max(usable, key=lambda pair: pair[0])


def validate_name(item, kind):
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"each {kind} needs a nonempty name")
    return name


def main(data):
    deposit = dec(data.get("deposit"), "deposit")
    days = dec(data.get("days", 365), "days")
    fixed_fees = dec(data.get("fixed_annual_fees", 0), "fixed_annual_fees")
    if deposit < ZERO or days <= ZERO or fixed_fees < ZERO:
        raise ValueError("deposit and fixed_annual_fees must be nonnegative; days must be positive")

    savings_list = data.get("savings")
    cards = data.get("cards")
    if not isinstance(savings_list, list) or not savings_list:
        raise ValueError("savings must be a nonempty array")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty array")

    checking_name = data.get("checking_account")
    if checking_name is not None and not isinstance(checking_name, str):
        raise ValueError("checking_account must be a string when supplied")
    require_minimum = bool(data.get("require_ongoing_minimum", True))
    checking_boosts = data.get("checking_boosts", [])
    existing_card_bonuses = data.get("existing_card_bonuses", [])
    if not isinstance(checking_boosts, list) or not isinstance(existing_card_bonuses, list):
        raise ValueError("checking_boosts and existing_card_bonuses must be arrays")

    excluded = []
    ranked = []
    warnings = []
    seen_savings = set()

    for savings in savings_list:
        sname = validate_name(savings, "savings account")
        if sname in seen_savings:
            raise ValueError(f"duplicate savings name: {sname}")
        seen_savings.add(sname)
        opening_minimum = dec(savings.get("opening_minimum", 0), "opening_minimum")
        ongoing_minimum = dec(savings.get("ongoing_minimum", 0), "ongoing_minimum")
        below_min_fee = dec(savings.get("annual_maintenance_fee_below_minimum", 0), "annual_maintenance_fee_below_minimum")
        extra_apy = dec(savings.get("extra_apy_percent", 0), "extra_apy_percent")
        if min(opening_minimum, ongoing_minimum, below_min_fee, extra_apy) < ZERO:
            raise ValueError("minimums, fees, and bonuses cannot be negative")
        if deposit < opening_minimum:
            excluded.append({"savings": sname, "reason": "deposit is below opening minimum"})
            continue
        if deposit < ongoing_minimum and require_minimum:
            excluded.append({"savings": sname, "reason": "deposit is below ongoing minimum"})
            continue
        tier = selected_tier(savings, deposit)
        if tier is None:
            excluded.append({"savings": sname, "reason": "no APY tier applies to deposit"})
            continue
        threshold, base_apy = tier

        matching_checking = []
        if checking_name:
            matching_checking = [x for x in checking_boosts if x.get("checking") == checking_name and x.get("savings") == sname]
        top_checking = best_entry(matching_checking)
        checking_apy = dec(top_checking.get("apy_percent", 0), "checking boost") if top_checking else ZERO

        for card in cards:
            cname = validate_name(card, "card")
            annual_fee = dec(card.get("annual_fee", 0), "card.annual_fee")
            if annual_fee < ZERO:
                raise ValueError("card annual_fee cannot be negative")
            card_options = list(index_bonuses(card.get("bonuses", []), "savings", sname))
            for existing in index_bonuses(existing_card_bonuses, "savings", sname):
                card_options.append(existing)
            top_card = best_entry(card_options)
            card_apy = dec(top_card.get("apy_percent", 0), "card bonus") if top_card else ZERO
            effective_apy = base_apy + extra_apy + checking_apy + card_apy
            daily_rate = (Decimal(1) + effective_apy / HUNDRED) ** (Decimal(1) / DAYS_IN_YEAR) - Decimal(1)
            gross_interest = deposit * ((Decimal(1) + daily_rate) ** days - Decimal(1))
            account_fee = below_min_fee if deposit < ongoing_minimum else ZERO
            total_fees = annual_fee + account_fee + fixed_fees
            net = gross_interest - total_fees
            bonus_source = None
            if top_card:
                bonus_source = top_card.get("source") or (cname if top_card in card_options[:len(card.get("bonuses", []))] else "existing eligible card")
            ranked.append({
                "savings": sname,
                "card": cname,
                "tier_minimum_balance": str(threshold),
                "base_apy_percent": pct(base_apy),
                "independent_extra_apy_percent": pct(extra_apy),
                "checking_boost_apy_percent": pct(checking_apy),
                "checking_boost_source": checking_name if top_checking else None,
                "highest_card_bonus_apy_percent": pct(card_apy),
                "highest_card_bonus_source": bonus_source,
                "effective_apy_percent": pct(effective_apy),
                "projected_gross_interest": money(gross_interest),
                "selected_card_annual_fee": money(annual_fee),
                "account_annual_fee": money(account_fee),
                "other_fixed_annual_fees": money(fixed_fees),
                "projected_net_one_year": money(net)
            })

    ranked.sort(key=lambda row: Decimal(row["projected_net_one_year"]), reverse=True)
    if not checking_name:
        warnings.append("No checking account was supplied; no linked-checking boost was included.")
    elif not any(row["checking_boost_apy_percent"] != "0.000000" for row in ranked):
        warnings.append("No documented qualifying linked-checking boost was found for the supplied checking account and ranked savings accounts.")
    if not ranked:
        warnings.append("No eligible combination was ranked. Review opening/ongoing minimums and input documentation.")
    return {"assumptions": {"constant_balance": str(deposit), "days": str(days), "daily_compounding": True}, "ranked_combinations": ranked, "excluded_savings": excluded, "warnings": warnings}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
