#!/usr/bin/env python3
"""Evaluate supplied credit-card closure prerequisites without performing actions.

Reads a single JSON object from stdin and writes a single JSON object to stdout.
See SKILL.md for the input schema. Unknown or malformed prerequisite data fails
closed so callers cannot mistake incomplete evidence for eligibility.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "final", "completed", "cancelled", "canceled"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
ALLOWED_REASONS = {
    "annual_fee",
    "not_using_card",
    "found_better_card",
    "unhappy_with_rewards",
    "simplifying_finances",
    "negative_experience",
    "other",
}


def parse_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    candidates = [text[:10]]
    if "T" not in text and " " in text:
        candidates.append(text.split()[0])
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def parse_balance(value: Any) -> Optional[Decimal]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    # Accept simple currency strings only; avoid interpreting arbitrary text.
    if not re.fullmatch(r"[+-]?\d+(?:\.\d{1,2})?", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def normalized_status(record: Any) -> Optional[str]:
    if not isinstance(record, dict):
        return None
    status = record.get("status")
    if not isinstance(status, str) or not status.strip():
        return None
    return status.strip().lower().replace(" ", "_").replace("-", "_")


def normalize_reason(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", " ").replace("_", " ")
    compact = re.sub(r"\s+", " ", text)
    direct = compact.replace(" ", "_")
    if direct in ALLOWED_REASONS:
        return direct
    patterns = [
        ("annual_fee", ("annual fee", "fee")),
        ("not_using_card", ("not using", "dont use", "don't use", "rarely use")),
        ("found_better_card", ("better card", "another card", "other card")),
        ("unhappy_with_rewards", ("unhappy with reward", "rewards", "cash back", "cashback")),
        ("simplifying_finances", ("simplif", "consolidat", "too many card")),
        ("negative_experience", ("negative experience", "bad experience", "poor service", "complaint")),
    ]
    for reason, fragments in patterns:
        if any(fragment in compact for fragment in fragments):
            return reason
    return None


def evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    blockers: List[str] = []
    account = payload.get("account")
    if not isinstance(account, dict):
        account = {}
        blockers.append("missing_or_ambiguous_account")

    if payload.get("identity_verified") is not True:
        blockers.append("identity_not_verified")

    today = parse_date(payload.get("current_date"))
    opened = parse_date(account.get("date_of_account_open"))
    age_days: Optional[int] = None
    if today is None or opened is None:
        blockers.append("missing_or_ambiguous_account_age")
    elif opened > today:
        blockers.append("invalid_account_open_date")
    else:
        age_days = (today - opened).days
        if age_days < 60:
            blockers.append("account_age_less_than_60_days")

    balance = parse_balance(account.get("current_balance"))
    if balance is None:
        blockers.append("missing_or_ambiguous_balance")
    elif balance != Decimal("0"):
        blockers.append("outstanding_balance_not_zero")

    disputes = payload.get("account_disputes")
    active_dispute_count = 0
    if not isinstance(disputes, list):
        blockers.append("missing_or_ambiguous_account_disputes")
    else:
        for dispute in disputes:
            status = normalized_status(dispute)
            # A dispute with no clear final status is unsafe for closure.
            if status is None or status not in FINAL_DISPUTE_STATUSES:
                active_dispute_count += 1
        if active_dispute_count:
            blockers.append("active_or_pending_dispute")

    orders = payload.get("replacement_orders")
    blocking_order_count = 0
    if not isinstance(orders, list):
        blockers.append("missing_or_ambiguous_replacement_orders")
    else:
        for order in orders:
            status = normalized_status(order)
            if status is None or status not in FINAL_REPLACEMENT_STATUSES:
                blocking_order_count += 1
        if blocking_order_count:
            blockers.append("pending_replacement_card_order")

    eligible = not blockers
    recent_history = payload.get("closure_reason_history_recent")
    reason = normalize_reason(payload.get("closure_reason_text"))
    if not eligible:
        next_stage = "resolve_eligibility_blockers"
    elif recent_history is True:
        next_stage = "refresh_checks_then_close_without_retention"
    elif recent_history is False and reason in ALLOWED_REASONS:
        next_stage = "log_reason_and_follow_retention_protocol"
    elif recent_history is False:
        next_stage = "obtain_and_normalize_closure_reason"
    else:
        next_stage = "check_closure_reason_history"

    return {
        "account_id": account.get("account_id"),
        "user_id": account.get("user_id"),
        "account_age_days": age_days,
        "interpreted_balance": None if balance is None else format(balance, "f"),
        "active_or_ambiguous_dispute_count": active_dispute_count,
        "blocking_or_ambiguous_replacement_order_count": blocking_order_count,
        "closure_eligible": eligible,
        "blockers": blockers,
        "normalized_closure_reason": reason,
        "next_stage": next_stage,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:  # Structured failure is safer for workflow callers.
        print(json.dumps({"closure_eligible": False, "blockers": ["invalid_input"], "error": str(exc)}))


if __name__ == "__main__":
    main()
