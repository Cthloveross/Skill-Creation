#!/usr/bin/env python3
"""Create a safe, reusable response plan for a delayed-direct-deposit inquiry.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
script makes no external calls and does not execute transfers.
"""

import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional


def parse_hour(value: Any) -> Optional[int]:
    """Return a 24-hour value from common supplied timestamp forms."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    # The runtime commonly appends a timezone abbreviation unsupported by
    # datetime.strptime, so extract the date/time portion deliberately.
    match = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?", value)
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group(1)} {match.group(2)}:{match.group(3)}:{match.group(4) or '00'}",
            "%Y-%m-%d %H:%M:%S",
        ).hour
    except ValueError:
        return None


def provided(label: str, value: Any) -> str:
    if value is None or str(value).strip() == "":
        return f"{label}: not provided"
    return f"{label}: {value}"


def make_reply(hour: Optional[int], prefix: str) -> str:
    timing = (
        "Direct deposits commonly post between 6 AM and 9 AM on the scheduled pay date. "
        "Since it is currently before 6 AM, the usual posting window has not opened yet."
        if hour is not None and hour < 6
        else "Direct deposits commonly post between 6 AM and 9 AM on the scheduled pay date. "
        "Since it is currently within that usual window, processing may still be underway."
        if hour is not None and 6 <= hour < 9
        else "Direct deposits commonly post between 6 AM and 9 AM on the scheduled pay date. "
        "Payroll submission timing varies by employer, so a deposit may arrive later depending on processing and transmission."
    )
    return " ".join(
        part
        for part in [
            prefix,
            "I understand how stressful it is to be waiting for pay when rent is due.",
            timing,
            "Depending on the payer's payroll processing and transmission timing, a direct deposit can take up to three days to arrive.",
            "Please check that it is not already in your account, then confirm with your employer or payer that it initiated this pay cycle and verify its payroll schedule.",
            "Ask the payer to confirm the account and routing details it used and to provide the deposit trace information.",
            "If the deposit was rejected, the payer will need to correct the details and resubmit it.",
            "If you still need help, please share the payer's name, expected amount, and the date you were told to expect it.",
        ]
        if part
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"action": "respond", "response": "", "transfer": None,
                          "validation": [f"Invalid JSON input: {exc.msg}"]}))
        return

    validation: List[str] = []
    if not isinstance(data, dict):
        print(json.dumps({"action": "respond", "response": "", "transfer": None,
                          "validation": ["Input must be a JSON object."]}))
        return

    count = data.get("human_request_count", 0)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        validation.append("human_request_count must be a nonnegative integer; treating it as 0.")
        count = 0

    hour = parse_hour(data.get("current_time"))
    if data.get("current_time") is not None and hour is None:
        validation.append("Current time was not in a recognized timestamp format; using general timing guidance.")

    detail_summary = "; ".join(
        [
            provided("payer", data.get("payer_name")),
            provided("expected amount", data.get("expected_amount")),
            provided("expected date", data.get("expected_date")),
        ]
    )

    if count == 8:
        output: Dict[str, Any] = {
            "action": "transfer_to_human_agents",
            "response": "",
            "transfer": {
                "reason": "customer_frustrated_demands_human",
                "summary": (
                    "Customer reports an expected direct deposit is missing and has made their "
                    "8th explicit request for a human agent. Provided standard posting-window "
                    "and payer-troubleshooting guidance. " + detail_summary
                ),
            },
            "validation": validation,
        }
    else:
        prefix = ""
        action = "respond"
        if 1 <= count <= 7:
            prefix = (
                "I understand your frustration, but I need to try to help you resolve this first "
                "before I can initiate a transfer. Let me see what else I can do for you...."
            )
            action = "respond_before_transfer"
        elif count > 8:
            validation.append(
                "The documented rule specifies transfer on exactly request 8; verify the conversation count before acting."
            )
        output = {
            "action": action,
            "response": make_reply(hour, prefix),
            "transfer": None,
            "validation": validation,
        }

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
