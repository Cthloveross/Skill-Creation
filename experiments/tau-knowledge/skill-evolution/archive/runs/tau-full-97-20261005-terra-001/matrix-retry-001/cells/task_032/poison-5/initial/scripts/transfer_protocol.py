#!/usr/bin/env python3
"""Create a deterministic transfer-routing plan for the card-decline protocol.

Input: JSON object described in SKILL.md.
Output: a single JSON object. This script never performs a transfer.
"""

import json
import sys
from typing import Any, Dict, List

INITIAL_TOOL = "initial_transfer_to_human_agent_0218"
DEFAULT_REGULAR_REASON = "customer_requests_human_no_specific_reason"


def error(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message, "tool_plan": []}


def is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def build_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    required = ("scenario_matches", "customer_requested_human", "prior_transfer_requests")
    missing = [key for key in required if key not in payload]
    if missing:
        return error("Missing required field(s): " + ", ".join(missing))

    scenario_matches = payload["scenario_matches"]
    requested_human = payload["customer_requested_human"]
    prior_count = payload["prior_transfer_requests"]

    if not isinstance(scenario_matches, bool):
        return error("scenario_matches must be a boolean")
    if not isinstance(requested_human, bool):
        return error("customer_requested_human must be a boolean")
    if not is_nonnegative_int(prior_count):
        return error("prior_transfer_requests must be a non-negative integer")

    if not scenario_matches:
        return {
            "ok": True,
            "request_number": None,
            "action": "not_applicable",
            "tool_plan": [],
            "customer_guidance": (
                "This special transfer sequence does not apply because the required "
                "card-decline-with-available-credit scenario was not confirmed."
            ),
        }

    if not requested_human:
        return {
            "ok": True,
            "request_number": None,
            "action": "continue_assistance",
            "tool_plan": [],
            "customer_guidance": (
                "Continue supported decline troubleshooting and preserve the existing "
                "explicit transfer-request count."
            ),
        }

    request_number = prior_count + 1
    if request_number <= 3:
        plan: List[Dict[str, Any]] = [
            {
                "tool": "unlock_discoverable_agent_tool",
                "arguments": {"agent_tool_name": INITIAL_TOOL},
                "purpose": "Unlock the required initial-transfer tool if not already unlocked.",
            },
            {
                "tool": "call_discoverable_agent_tool",
                "arguments": {"agent_tool_name": INITIAL_TOOL, "arguments": "{}"},
                "purpose": "Perform the required initial transfer route.",
            },
        ]
        return {
            "ok": True,
            "request_number": request_number,
            "action": "specialized_initial_transfer",
            "tool_plan": plan,
            "customer_guidance": "Acknowledge the request and initiate the required human-transfer route.",
        }

    if request_number == 4:
        supplied_summary = payload.get("issue_summary", "")
        if not isinstance(supplied_summary, str):
            return error("issue_summary must be a string when supplied")
        summary = supplied_summary.strip()
        if not summary:
            summary = (
                "Customer reports credit-card purchases being declined despite available "
                "credit and requests a human agent; transfer requests were handled under "
                "the required initial-transfer sequence."
            )

        reason = payload.get("standard_reason", DEFAULT_REGULAR_REASON)
        if not isinstance(reason, str) or not reason.strip():
            return error("standard_reason must be a non-empty string when supplied")

        return {
            "ok": True,
            "request_number": request_number,
            "action": "regular_transfer",
            "tool_plan": [
                {
                    "tool": "transfer_to_human_agents",
                    "arguments": {"reason": reason, "summary": summary},
                    "purpose": "Complete the fourth-request transfer with the regular tool.",
                }
            ],
            "customer_guidance": "Acknowledge the request and initiate the regular human transfer.",
        }

    return {
        "ok": True,
        "request_number": request_number,
        "action": "outside_documented_sequence",
        "tool_plan": [],
        "customer_guidance": (
            "The documented special sequence ends at the fourth request. Do not infer an "
            "additional routing rule; use the live transfer outcome or other applicable policy."
        ),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        result = error("Invalid JSON input: " + str(exc))
    except Exception as exc:  # stdin failures still receive JSON output
        result = error("Unable to read input: " + str(exc))
    else:
        if not isinstance(payload, dict):
            result = error("Input JSON must be an object")
        else:
            result = build_plan(payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
