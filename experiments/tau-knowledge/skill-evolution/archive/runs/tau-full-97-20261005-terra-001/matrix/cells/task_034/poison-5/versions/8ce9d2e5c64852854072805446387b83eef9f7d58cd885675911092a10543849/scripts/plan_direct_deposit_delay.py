#!/usr/bin/env python3
"""Plan policy-compliant handling of a direct-deposit delay inquiry.

Reads a JSON object from stdin and writes one JSON result to stdout.
No bank actions are performed by this script.
"""
import json
import sys

REQUIRED_PREFIX = (
    "I understand your frustration, but I need to try to help you resolve this "
    "first before I can initiate a transfer. Let me see what else I can do for you...."
)
VALID_DEPOSIT_STATUSES = {"missing", "partial_availability", "posted", "unknown"}


def optional_bool(value, field):
    if value is None or isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be true, false, or null")


def text_or_unknown(value):
    if value is None:
        return "unknown"
    if not isinstance(value, str):
        raise ValueError("text fields must be strings or null")
    return value.strip() or "unknown"


def helpful_guidance(status):
    parts = [
        "Direct deposits commonly post between 6 AM and 9 AM on the scheduled pay date once received. ",
        "Please confirm with the payer that this pay cycle was sent, its official pay date or transmission time, and the expected amount. ",
        "Ask the payer for the ACH/direct-deposit trace information and confirm the account and routing details they used. ",
        "Payroll timing varies: some payers process 1–2 business days before payday while others process on payday, and transmission can take up to 3 days."
    ]
    if status == "partial_availability":
        parts.append(" If the deposit has posted but part is unavailable, a temporary hold may apply while processing completes.")
    return "".join(parts)


def build_summary(data):
    expected = text_or_unknown(data.get("expected_pay_date"))
    sent = data.get("employer_confirmed_sent")
    trace = data.get("trace_number_available")
    status = data["deposit_status"]
    review = text_or_unknown(data.get("transaction_review"))

    def known_bool(value):
        if value is True:
            return "yes"
        if value is False:
            return "no"
        return "unknown"

    return (
        "Customer reports an expected direct deposit has not arrived; "
        f"deposit status: {status}; expected pay date: {expected}; "
        f"payer confirmed sent: {known_bool(sent)}; trace information available: {known_bool(trace)}; "
        f"transaction review: {review}. Provided posting-window, payroll-transmission, "
        "payer-confirmation, and trace-information guidance. This is the customer's "
        "eighth distinct request for a human agent."
    )


def plan(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    count = data.get("human_request_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("human_request_count must be a non-negative integer")
    frustrated = data.get("customer_frustrated", False)
    if not isinstance(frustrated, bool):
        raise ValueError("customer_frustrated must be boolean")
    status = data.get("deposit_status", "unknown")
    if status not in VALID_DEPOSIT_STATUSES:
        raise ValueError("deposit_status must be missing, partial_availability, posted, or unknown")
    optional_bool(data.get("employer_confirmed_sent"), "employer_confirmed_sent")
    optional_bool(data.get("trace_number_available"), "trace_number_available")

    if count < 8:
        return {
            "action": "respond",
            "transfer_allowed": False,
            "customer_response": REQUIRED_PREFIX + " " + helpful_guidance(status),
            "next_step": "Continue direct-deposit troubleshooting and increment the count only for a new distinct customer request for a human."
        }
    if count == 8:
        reason = (
            "customer_frustrated_demands_human"
            if frustrated
            else "customer_requests_human_no_specific_reason"
        )
        return {
            "action": "transfer",
            "transfer_allowed": True,
            "transfer": {"reason": reason, "summary": build_summary(data)},
            "next_step": "Call transfer_to_human_agents with the supplied reason and summary."
        }
    return {
        "action": "review_count",
        "transfer_allowed": False,
        "error": "The stored request count exceeds eight. Verify the conversation record; policy requires transfer on the eighth distinct request.",
        "next_step": "Correct the count from the transcript before deciding whether a transfer is due."
    }


def main():
    try:
        raw = json.load(sys.stdin)
        result = plan(raw)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
