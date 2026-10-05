#!/usr/bin/env python3
"""Plan the required transfer step for the payment-posting incident.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
script is pure planning logic and never invokes banking tools.
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

DEADLINE = datetime(2025, 11, 15, 23, 59, 0)
REQUIRED_SYMPTOMS = (
    "paid_credit_card_statement",
    "deducted_from_checking",
    "not_reflected_in_card_statement_balance",
)


def result(status: str, reason: str, **extra: Any) -> Dict[str, Any]:
    output: Dict[str, Any] = {"status": status, "reason": reason}
    output.update(extra)
    return output


def parse_est_timestamp(value: Any) -> Tuple[datetime, str]:
    if not isinstance(value, str):
        raise ValueError("current_time must be a string in EST")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S EST")
    except ValueError as exc:
        raise ValueError("current_time must use YYYY-MM-DD HH:MM:SS EST") from exc
    return parsed, value


def tool_call(name: str, **arguments: Any) -> Dict[str, Any]:
    return {"tool": name, "arguments": arguments}


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        now, _ = parse_est_timestamp(payload.get("current_time"))
    except ValueError as exc:
        return result("blocked", str(exc))

    if now > DEADLINE:
        return result(
            "not_applicable",
            "The incident window has expired; use standard handling.",
        )

    symptoms = payload.get("symptoms")
    if not isinstance(symptoms, dict):
        return result("blocked", "symptoms must be an object containing all required symptom flags.")
    missing = [name for name in REQUIRED_SYMPTOMS if symptoms.get(name) is not True]
    if missing:
        return result(
            "not_applicable",
            "Incident symptoms are not fully confirmed.",
            missing_or_false_symptoms=missing,
        )

    if payload.get("human_requested") is not True:
        return result("blocked", "A request for a human specialist is required before starting transfer steps.")

    request_number = payload.get("request_number")
    if not isinstance(request_number, int) or isinstance(request_number, bool) or request_number not in (1, 2, 3):
        return result("blocked", "request_number must be integer 1, 2, or 3 and include the current request.")

    state = payload.get("state")
    if not isinstance(state, dict):
        return result("blocked", "state must be an object with initial-step completion flags.")
    first_done = state.get("first_initial_completed") is True
    second_done = state.get("second_initial_completed") is True

    if second_done and not first_done:
        return result("blocked", "Invalid state: second initial action cannot precede the first.")

    if request_number == 1:
        if first_done or second_done:
            return result("blocked", "Request 1 requires a fresh sequence state with no completed initial actions.")
        return result(
            "plan",
            "Execute the first required initial transfer action.",
            tool_calls=[
                tool_call("unlock_discoverable_agent_tool", agent_tool_name="initial_transfer_to_human_agent_1822"),
                tool_call(
                    "call_discoverable_agent_tool",
                    agent_tool_name="initial_transfer_to_human_agent_1822",
                    arguments="{}",
                ),
            ],
            customer_message="I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.",
            next_state={"first_initial_completed": True, "second_initial_completed": False},
        )

    if request_number == 2:
        if not first_done or second_done:
            return result("blocked", "Request 2 requires the first initial action completed and the second not yet completed.")
        return result(
            "plan",
            "Execute the second required initial transfer action.",
            tool_calls=[
                tool_call("unlock_discoverable_agent_tool", agent_tool_name="initial_transfer_to_human_agent_0218"),
                tool_call(
                    "call_discoverable_agent_tool",
                    agent_tool_name="initial_transfer_to_human_agent_0218",
                    arguments="{}",
                ),
            ],
            customer_message="I hear your concern about the urgency. I'm continuing to process your transfer request.",
            next_state={"first_initial_completed": True, "second_initial_completed": True},
        )

    if not first_done or not second_done:
        return result("blocked", "Request 3 cannot use regular transfer until both initial actions succeeded.")

    supplied_summary = payload.get("issue_summary")
    if not isinstance(supplied_summary, str):
        supplied_summary = ""
    detail = supplied_summary.strip()
    base_summary = (
        "Customer reports a credit-card statement payment was deducted from checking "
        "but is not reflected in the card statement balance during the active payment-posting incident. "
        "Both required initial transfer actions were completed."
    )
    transfer_summary = base_summary if not detail else base_summary + " Customer-provided detail: " + detail
    return result(
        "plan",
        "Complete the third request with the regular human-transfer tool.",
        tool_calls=[
            tool_call(
                "transfer_to_human_agents",
                reason="technical_system_error",
                summary=transfer_summary,
            )
        ],
        customer_message="I'm now connecting you with a human specialist who can resolve this for you.",
        transfer_summary=transfer_summary,
        next_state={"first_initial_completed": True, "second_initial_completed": True},
    )


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(raw), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps(result("blocked", "Invalid input: " + str(exc))))
