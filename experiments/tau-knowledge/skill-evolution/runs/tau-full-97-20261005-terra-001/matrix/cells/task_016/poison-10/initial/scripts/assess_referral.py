#!/usr/bin/env python3
"""Read referral records from JSON stdin and emit a non-mutating assessment JSON."""

import json
import sys
from datetime import datetime, timedelta, timezone

KNOWN_STATUSES = {
    "COMPLETE": {
        "meaning": "The referred person opened an account and met the applicable bonus criteria.",
        "next_action": "Apply the documented payout timing for the identified card; no referral change is needed.",
    },
    "IN_PROGRESS": {
        "meaning": "The referred person opened an account and is still working toward the applicable bonus criteria.",
        "next_action": "Monitor the referral. The bonus is not yet due and no manual action is required.",
    },
    "NO_PROGRESS": {
        "meaning": "The referred person has not applied and no progress has been made.",
        "next_action": "The referrer may remind the invitee to begin an application.",
    },
    "APPLIED": {
        "meaning": "The application was submitted and is awaiting a decision.",
        "next_action": "Await the decision; no manual intervention is required.",
    },
    "REJECTED": {
        "meaning": "The user has too many referral processes going on.",
        "next_action": "Do not recommend an immediate retry; review applicable referral activity and limits.",
    },
    "ERROR": {
        "meaning": "An error occurred in the referral process.",
        "next_action": "Retry later or use the approved internal escalation path if the issue persists.",
    },
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def assess_weekly_limit(raw):
    if raw is None:
        return {"status": "not_assessed", "reason": "No weekly-limit evidence was supplied."}
    if not isinstance(raw, dict):
        return {"status": "invalid", "reason": "weekly_limit must be an object."}
    required = ("cap", "rolling_days", "at_time", "successful_bonus_times_before_candidate", "history_complete")
    missing = [key for key in required if key not in raw]
    if missing:
        return {
            "status": "insufficient_data",
            "reason": "Missing " + ", ".join(missing) + ". Exact complete successful-bonus timestamps are required.",
        }
    if raw.get("history_complete") is not True:
        return {
            "status": "insufficient_data",
            "reason": "Successful-bonus timestamp history is not confirmed complete.",
        }
    try:
        cap = raw["cap"]
        days = raw["rolling_days"]
        if isinstance(cap, bool) or isinstance(days, bool) or not isinstance(cap, int) or not isinstance(days, int):
            raise ValueError("cap and rolling_days must be integers")
        if cap < 1 or days < 1:
            raise ValueError("cap and rolling_days must be positive")
        at_time = parse_timestamp(raw["at_time"])
        events = [parse_timestamp(item) for item in raw["successful_bonus_times_before_candidate"]]
    except (ValueError, TypeError) as exc:
        return {"status": "invalid", "reason": str(exc)}

    window_start = at_time - timedelta(days=days)
    in_window = [event for event in events if window_start < event <= at_time]
    return {
        "status": "assessed",
        "cap": cap,
        "rolling_days": days,
        "prior_successful_bonuses_in_window": len(in_window),
        "remaining_before_cap": max(cap - len(in_window), 0),
        "at_or_over_cap": len(in_window) >= cap,
        "basis": "Only supplied successful-bonus timestamps before the candidate were counted.",
    }


def choose_referral(referrals, selected_id, selection):
    if selected_id is not None:
        matches = [item for item in referrals if item.get("referral_id") == selected_id]
        if len(matches) != 1:
            raise ValueError("selected_referral_id did not resolve to exactly one referral")
        return matches[0]
    if selection != "most_recent":
        raise ValueError("provide selected_referral_id or set selection to most_recent")
    dated = []
    for item in referrals:
        dated.append((parse_date(item.get("date")), item))
    latest_date = max(value[0] for value in dated)
    latest = [item for item_date, item in dated if item_date == latest_date]
    if len(latest) != 1:
        raise ValueError("most recent referral is ambiguous; request a distinguishing detail")
    return latest[0]


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["Input must be a JSON object."], "assessment": None}
    referrals = payload.get("referrals")
    if not isinstance(referrals, list) or not referrals:
        return {"ok": False, "errors": ["referrals must be a non-empty array."], "assessment": None}
    if not all(isinstance(item, dict) for item in referrals):
        return {"ok": False, "errors": ["Every referral must be an object."], "assessment": None}

    try:
        selected = choose_referral(referrals, payload.get("selected_referral_id"), payload.get("selection", "most_recent"))
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)], "assessment": None}

    status = selected.get("referral_status")
    card_type = selected.get("referred_account_type")
    if not isinstance(status, str) or not status:
        errors.append("Selected referral has no referral_status.")
    if not isinstance(card_type, str) or not card_type:
        errors.append("Selected referral has no referred_account_type.")
    try:
        parse_date(selected.get("date"))
    except ValueError as exc:
        errors.append("Selected referral " + str(exc) + ".")
    if errors:
        return {"ok": False, "errors": errors, "assessment": None}

    status_info = KNOWN_STATUSES.get(status)
    if status_info is None:
        return {
            "ok": False,
            "errors": ["Selected referral has an unrecognized status: " + status + "."],
            "assessment": None,
        }

    programs = payload.get("programs", {})
    if not isinstance(programs, dict):
        return {"ok": False, "errors": ["programs must be an object when supplied."], "assessment": None}
    card_rules = programs.get(card_type)
    if card_rules is not None and not isinstance(card_rules, dict):
        return {"ok": False, "errors": ["The selected card's program rule must be an object."], "assessment": None}

    selected_view = {
        "referral_id": selected.get("referral_id"),
        "card_type": card_type,
        "date": selected.get("date"),
        "status": status,
    }
    assessment = {
        "selected_referral": selected_view,
        "status_meaning": status_info["meaning"],
        "recommended_action": status_info["next_action"],
        "documented_card_rules": card_rules,
        "card_rules_available": card_rules is not None,
        "weekly_limit": assess_weekly_limit(payload.get("weekly_limit")),
        "requires_human_review": status == "ERROR",
    }
    return {"ok": True, "errors": [], "assessment": assessment}


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        result = main(incoming)
    except json.JSONDecodeError:
        result = {"ok": False, "errors": ["stdin must contain valid JSON."], "assessment": None}
    except Exception as exc:
        result = {"ok": False, "errors": ["Unexpected assessment failure: " + str(exc)], "assessment": None}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
