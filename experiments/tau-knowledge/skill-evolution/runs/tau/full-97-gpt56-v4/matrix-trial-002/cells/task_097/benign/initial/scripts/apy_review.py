#!/usr/bin/env python3
"""Calculate a documented, provisional savings-interest review from JSON stdin."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
D = Decimal

CARD_BONUSES = {
    "silver": {
        "Bronze Rewards Card": D("0"), "Silver Rewards Card": D("0.1"),
        "Gold Rewards Card": D("0.5"), "EcoCard": D("2.2"),
        "Green Rewards Card": D("0"), "Crypto-Cash Back Card": D("0.5"),
    },
    "silver plus": {
        "Bronze Rewards Card": D("0.15"), "Silver Rewards Card": D("0.15"),
        "Gold Rewards Card": D("0.2"), "Platinum Rewards Card": D("0.15"),
        "Diamond Elite Card": D("0.4"), "EcoCard": D("0.45"),
        "Green Rewards Card": D("0.1"), "Crypto-Cash Back Card": D("0"),
    },
    "platinum": {
        "Bronze Rewards Card": D("0"), "Silver Rewards Card": D("0"),
        "Gold Rewards Card": D("0.15"), "Platinum Rewards Card": D("0.25"),
        "Diamond Elite Card": D("0.35"), "EcoCard": D("0"),
        "Green Rewards Card": D("0"), "Crypto-Cash Back Card": D("0"),
    },
    "diamond elite": {
        "Bronze Rewards Card": D("0"), "Silver Rewards Card": D("0"),
        "Gold Rewards Card": D("0"), "Platinum Rewards Card": D("0.1"),
        "Diamond Elite Card": D("0.5"), "EcoCard": D("0"),
        "Green Rewards Card": D("0"), "Crypto-Cash Back Card": D("0.15"),
    },
}

# Only pairings whose numerical boost is supplied by the packaged evidence are encoded.
CHECKING_BONUSES = {
    "silver": {"Bluest Account": D("0.45")},
    "silver plus": {"Blue Account": D("0.35")},
    "platinum": {"Blue Account": D("0.8"), "Light Green Account": D("0.65")},
    "diamond elite": {"Evergreen Account": D("0.15"), "Light Green Account": D("0.2")},
}


def money(value):
    return D(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def out_decimal(value):
    return format(value, "f")


def normalize_account(value):
    return " ".join(str(value).strip().lower().split())


def base_apy(account, balance):
    if account == "silver":
        return D("4.0") if balance >= D("10000") else D("2.5")
    if account == "silver plus":
        return D("4.5") if balance >= D("15000") else D("3.0")
    if account == "platinum":
        return D("6.5")
    if account == "diamond elite":
        return D("7.5")
    raise ValueError("Unsupported account_type")


def active_qualified(item, needs_link=False):
    return (str(item.get("status", "")).upper() == "ACTIVE" and
            item.get("same_profile") is True and
            (not needs_link or item.get("linked") is True))


def run(data):
    account = normalize_account(data.get("account_type", ""))
    if account not in CARD_BONUSES:
        raise ValueError("account_type must be Silver, Silver Plus, Platinum, or Diamond Elite")
    raw_days = data.get("balance_days")
    if not isinstance(raw_days, list) or not raw_days:
        raise ValueError("balance_days must be a nonempty list with one entry per statement day")
    days_per_year = D(str(data.get("days_per_year", 365)))
    if days_per_year <= 0:
        raise ValueError("days_per_year must be positive")

    unresolved = []
    card_candidates = []
    for card in data.get("credit_cards", []):
        card_type = card.get("type")
        if card.get("status") is None or card.get("same_profile") is None:
            unresolved.append("Credit-card status or same-profile qualification is unknown for %s." % card_type)
        if active_qualified(card) and card_type in CARD_BONUSES[account]:
            card_candidates.append((CARD_BONUSES[account][card_type], card_type))
    card_bonus, card_name = max(card_candidates, default=(D("0"), None), key=lambda x: x[0])

    age = data.get("profile_age")
    checking_candidates = []
    for checking in data.get("checking_accounts", []):
        checking_type = checking.get("type")
        if any(checking.get(k) is None for k in ("status", "same_profile", "linked")):
            unresolved.append("Checking status, linkage, or same-profile qualification is unknown for %s." % checking_type)
        if checking_type == "Light Green Account":
            if age is None:
                unresolved.append("Primary-holder age is required before applying a Light Green Account boost.")
                continue
            if not (13 <= int(age) <= 24):
                continue
        if active_qualified(checking, needs_link=True) and checking_type in CHECKING_BONUSES[account]:
            checking_candidates.append((CHECKING_BONUSES[account][checking_type], checking_type))
    checking_bonus, checking_name = max(checking_candidates, default=(D("0"), None), key=lambda x: x[0])

    other_bonus = D("0")
    direct_deposit = data.get("direct_deposit_active")
    relationship = data.get("relationship_eligible")
    if account == "silver plus":
        if direct_deposit is True:
            other_bonus += D("0.25")
        elif direct_deposit is None:
            unresolved.append("Silver Plus direct-deposit status is unknown.")
    if account in ("silver", "silver plus"):
        if relationship is True:
            other_bonus += D("0.025")
        elif relationship is None:
            unresolved.append("Relationship-bonus eligibility is unknown.")

    accrued = D("0")
    rates = []
    prior_date = None
    for entry in raw_days:
        if not isinstance(entry, dict) or "date" not in entry or "balance" not in entry:
            raise ValueError("Every balance_days entry needs date and balance")
        date = str(entry["date"])
        if prior_date is not None and date <= prior_date:
            raise ValueError("balance_days dates must be strictly ascending ISO dates")
        prior_date = date
        balance = D(str(entry["balance"]))
        if balance < 0:
            raise ValueError("daily balance cannot be negative")
        base = base_apy(account, balance)
        total_apy = base + card_bonus + checking_bonus + other_bonus
        daily_rate = (D("1") + total_apy / D("100")) ** (D("1") / days_per_year) - D("1")
        daily_interest = (balance + accrued) * daily_rate
        accrued += daily_interest
        rates.append({
            "date": date, "balance": out_decimal(balance), "base_apy_pct": out_decimal(base),
            "total_apy_pct": out_decimal(total_apy), "daily_interest_unrounded": out_decimal(daily_interest)
        })

    warnings = []
    if account == "diamond elite" and any(D(str(x["balance"])) < D("250000") for x in raw_days):
        warnings.append("One or more Diamond Elite balances are below the stated $250,000 ongoing minimum; review account standing, but do not infer an APY change from that fact alone.")
    return {
        "ok": True,
        "account_type": account,
        "selected_card_bonus_pct": out_decimal(card_bonus),
        "selected_card": card_name,
        "selected_checking_bonus_pct": out_decimal(checking_bonus),
        "selected_checking": checking_name,
        "other_confirmed_bonus_pct": out_decimal(other_bonus),
        "estimated_compounded_interest": out_decimal(money(accrued)),
        "calculation_assumption": "Daily effective rate = (1 + total_APY/100)^(1/days_per_year)-1; daily accrual compounds on balance plus prior accrued interest.",
        "daily_rates": rates,
        "unresolved": list(dict.fromkeys(unresolved)),
        "warnings": warnings,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("Input must be a JSON object")
        print(json.dumps(run(data), separators=(",", ":")))
    except (ValueError, InvalidOperation, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
