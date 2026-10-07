#!/usr/bin/env python3
"""Produce deterministic guidance for missing direct-deposit conversations.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
only recommends a transfer; the executor must call the banking transfer tool.
"""
import json
import sys

GATE_OPENING = (
    "I understand your frustration, but I need to try to help you resolve this "
    "first before I can initiate a transfer. Let me see what else I can do for you...."
)


def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("must be a boolean")


def guidance(status, posted, partial):
    timing = (
        "Direct deposits usually post between 6 AM and 9 AM on the scheduled pay date. "
        "Employers may transmit payroll one to two business days early or on payday itself, "
        "and a deposit can take up to three days to arrive after payer processing."
    )
    if status:
        timing += " Based on the timing you provided, the pay-date status is: " + status + "."
    if posted and partial:
        return (
            "If the deposit has posted but not all of it is available, a temporary hold may "
            "apply to part of the paycheck while processing completes. " + timing
        )
    if posted:
        return "Since the deposit appears posted, please compare the posted and available balances. " + timing
    return (
        timing
        + " Please check the account again at the applicable posting time and confirm with "
        "your employer or other payer that it sent this pay cycle's deposit. Verify its payroll "
        "schedule and the account and routing details it has on file. If it is still missing, "
        "ask the payer for the deposit trace information; if the bank says it was rejected, "
        "have the payer correct the details and resubmit it."
    )


def main(data):
    explicit = as_bool(data.get("current_request_is_explicit_transfer"), False)
    posted = as_bool(data.get("deposit_posted"), False)
    partial = as_bool(data.get("partial_available"), False)
    status = data.get("scheduled_pay_date_status", "")
    if not isinstance(status, str):
        raise ValueError("scheduled_pay_date_status must be a string")

    count = data.get("transfer_requests_so_far", 0)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("transfer_requests_so_far must be a nonnegative integer")
    if not explicit and count:
        raise ValueError("a non-transfer message cannot add to the transfer-request count")

    helpful = guidance(status.strip(), posted, partial)
    if not explicit:
        return {"reply": helpful, "transfer": False, "transfer_arguments": None}
    if count == 0:
        raise ValueError("an explicit current transfer request must be counted")
    if count <= 7:
        return {
            "reply": GATE_OPENING + " " + helpful,
            "transfer": False,
            "transfer_arguments": None,
        }
    if count == 8:
        summary = (
            "Customer reports a missing direct deposit and has explicitly requested a human "
            "agent eight times. Provided scheduled-pay-date posting guidance (typically 6 AM–9 AM), "
            "explained payer payroll timing and possible three-day arrival window, and advised "
            "confirmation with the payer plus deposit trace information if still missing."
        )
        return {
            "reply": "I am transferring you to a human agent now.",
            "transfer": True,
            "transfer_arguments": {
                "reason": "customer_frustrated_demands_human",
                "summary": summary,
            },
        }
    return {
        "reply": (
            "The required transfer point was request eight. Do not initiate a duplicate transfer; "
            "confirm the earlier transfer status through the normal support workflow."
        ),
        "transfer": False,
        "transfer_arguments": None,
        "error": "transfer request count exceeds eight",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
