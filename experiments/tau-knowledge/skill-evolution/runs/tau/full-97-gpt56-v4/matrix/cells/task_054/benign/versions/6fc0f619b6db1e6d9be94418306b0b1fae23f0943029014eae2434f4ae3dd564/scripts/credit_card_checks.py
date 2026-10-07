#!/usr/bin/env python3
"""Deterministic policy calculations for a credit-card case.

Input JSON schema:
{
  "today": "YYYY-MM-DD" | "MM/DD/YYYY",
  "account": {"card_type": str, "opened_on": date, "current_limit": number,
              "current_balance": number, "past_due_amount": number},
  "dispute": {"reason": str, "amount": number, "purchase_date": date,
              "contacted_merchant": bool,
              "prior_disputes_past_12_months": integer},
  "cli": {"requested_increase": number,
          "last_approved_request_date": date|null,
          "consecutive_on_time_months": integer|null},
  "pending_replacement": bool|null,
  "replacement_requests_past_60_days": integer|null
}

The script emits tier-derived values and eligibility booleans/blockers. It cannot
query bank systems; null/missing tool-derived facts are reported as unknown.
"""
import json
import sys
from datetime import datetime, date


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    raise ValueError("dates must use YYYY-MM-DD or MM/DD/YYYY")


def as_number(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} is required and must be numeric")
    if number < 0:
        raise ValueError(f"{label} cannot be negative")
    return number


def tier_for(card_type):
    text = (card_type or "").lower()
    if "diamond elite" in text:
        return "invitation"
    if "platinum" in text:
        return "elite"
    if "gold" in text:
        return "premium"
    if any(x in text for x in ("silver", "green rewards")):
        return "mid"
    if any(x in text for x in ("bronze", "ecocard", "crypto-cash")):
        return "entry"
    return None


def status(value, blockers):
    if any(x.startswith("unknown:") for x in blockers):
        return "unknown"
    return "eligible" if not blockers else "ineligible"


def main(data):
    account = data.get("account") or {}
    dispute = data.get("dispute") or {}
    cli = data.get("cli") or {}
    today = parse_date(data.get("today"))
    if today is None:
        raise ValueError("today is required")
    tier = tier_for(account.get("card_type"))
    if tier is None:
        raise ValueError("unsupported card_type; cannot infer a policy tier")

    opened = parse_date(account.get("opened_on"))
    if opened is None:
        raise ValueError("account.opened_on is required")
    age_days = (today - opened).days
    limit = as_number(account.get("current_limit"), "account.current_limit")
    balance = as_number(account.get("current_balance"), "account.current_balance")
    past_due = as_number(account.get("past_due_amount"), "account.past_due_amount")
    if limit <= 0:
        raise ValueError("account.current_limit must be greater than zero")

    provisional_limit = {"entry": 2500, "mid": 5000, "premium": 10000,
                         "elite": 15000, "invitation": 25000}[tier]
    reason = dispute.get("reason")
    amount = as_number(dispute.get("amount"), "dispute.amount")
    purchase = parse_date(dispute.get("purchase_date"))
    if purchase is None:
        raise ValueError("dispute.purchase_date is required")
    prior = dispute.get("prior_disputes_past_12_months")
    pblock = []
    if age_days < 60:
        pblock.append("account_age_under_60_days")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        pblock.append("reason_not_provisionally_eligible")
    if reason == "goods_services_not_received" and (today - purchase).days <= 30:
        pblock.append("goods_not_received_purchase_not_more_than_30_days_ago")
    if amount < 25 or amount > provisional_limit:
        pblock.append("amount_outside_provisional_limit")
    if prior is None:
        pblock.append("unknown:prior_disputes_past_12_months")
    elif not isinstance(prior, int) or isinstance(prior, bool) or prior < 0:
        raise ValueError("prior_disputes_past_12_months must be a nonnegative integer")
    elif prior > 2:
        pblock.append("more_than_two_prior_disputes")
    contacted = dispute.get("contacted_merchant")
    if reason != "unauthorized_fraudulent_charge":
        if contacted is None:
            pblock.append("unknown:contacted_merchant")
        elif contacted is not True:
            pblock.append("merchant_not_contacted_for_nonfraud_dispute")

    replacement_cap = {"entry": 2, "mid": 3, "premium": 4,
                       "elite": 4, "invitation": 4}[tier]
    rblock = []
    pending = data.get("pending_replacement")
    recent_replacements = data.get("replacement_requests_past_60_days")
    if pending is None:
        rblock.append("unknown:pending_replacement")
    elif pending is True:
        rblock.append("pending_replacement_order")
    if recent_replacements is None:
        rblock.append("unknown:replacement_requests_past_60_days")
    elif not isinstance(recent_replacements, int) or isinstance(recent_replacements, bool) or recent_replacements < 0:
        raise ValueError("replacement_requests_past_60_days must be a nonnegative integer")
    elif recent_replacements >= replacement_cap:
        rblock.append("replacement_limit_reached")

    cli_age_min = {"entry": 120, "mid": 90, "premium": 60,
                   "elite": 60, "invitation": 60}[tier]
    # Elite/invitation are treated as premium-and-above where only premium policy is published.
    cli_util_max = {"entry": 70, "mid": 80, "premium": 90,
                    "elite": 90, "invitation": 90}[tier]
    cli_cooldown = {"entry": 120, "mid": 90, "premium": 60,
                    "elite": 60, "invitation": 60}[tier]
    cli_fraction = 0.25 if tier == "entry" else 0.50
    payment_required = 6 if tier == "entry" else 3
    increase = as_number(cli.get("requested_increase"), "cli.requested_increase")
    utilization = balance / limit * 100
    cblock = []
    if increase > limit * cli_fraction:
        cblock.append("requested_amount_exceeds_limit")
    if age_days < cli_age_min:
        cblock.append("insufficient_account_age")
    last_approved = parse_date(cli.get("last_approved_request_date"))
    if last_approved is None:
        cblock.append("unknown:last_approved_request_date_or_no_approved_history")
    elif (today - last_approved).days < cli_cooldown:
        cblock.append("cooldown_period_active")
    if past_due > 0:
        cblock.append("past_due_balance")
    if utilization >= cli_util_max:
        cblock.append("high_utilization")
    on_time = cli.get("consecutive_on_time_months")
    if on_time is None:
        cblock.append("unknown:consecutive_on_time_months")
    elif not isinstance(on_time, int) or isinstance(on_time, bool) or on_time < 0:
        raise ValueError("consecutive_on_time_months must be a nonnegative integer")
    elif on_time < payment_required:
        cblock.append("insufficient_payment_history")
    # Pending replacement and active disputes must be supplied after their tool checks.
    active_disputes = data.get("active_disputes")
    if active_disputes is None:
        cblock.append("unknown:active_disputes")
    elif active_disputes is True:
        cblock.append("pending_disputes")
    if pending is None:
        cblock.append("unknown:pending_replacement")
    elif pending is True:
        cblock.append("pending_replacement_card")

    return {
        "tier": tier,
        "account_age_days": age_days,
        "utilization_percent": round(utilization, 4),
        "provisional_credit": {
            "maximum_amount": provisional_limit,
            "status": status(None, pblock),
            "eligible": not pblock,
            "blockers": pblock,
        },
        "replacement": {
            "requests_allowed_per_60_days": replacement_cap,
            "status": status(None, rblock),
            "eligible": not rblock,
            "blockers": rblock,
        },
        "cli": {
            "maximum_increase": round(limit * cli_fraction, 2),
            "new_limit_if_approved": round(limit + increase, 2),
            "minimum_account_age_days": cli_age_min,
            "cooldown_days": cli_cooldown,
            "utilization_must_be_below_percent": cli_util_max,
            "on_time_months_required": payment_required,
            "status": status(None, cblock),
            "eligible": not cblock,
            "blockers": cblock,
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
