#!/usr/bin/env python3
"""Plan the repeated-request transfer protocol.

Input JSON:
  prior_transfer_requests: nonnegative integer (required)
  customer_requests_human: boolean (required)
  clear_general_frustration: boolean (optional, default false)

Output JSON is a recommendation only; this script performs no banking action.
"""
import json
import sys


def fail(message: str) -> None:
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must be one JSON object: " + str(exc))

    if not isinstance(data, dict):
        fail("input must be a JSON object")
    prior = data.get("prior_transfer_requests")
    requested = data.get("customer_requests_human")
    frustrated = data.get("clear_general_frustration", False)

    # bool is an int subclass, so exclude it explicitly.
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        fail("prior_transfer_requests must be a nonnegative integer")
    if not isinstance(requested, bool):
        fail("customer_requests_human must be boolean")
    if not isinstance(frustrated, bool):
        fail("clear_general_frustration must be boolean")

    if not requested:
        result = {
            "action": "no_transfer_request",
            "request_number": None,
            "next_prior_transfer_requests": prior,
            "tool_guidance": "Do not invoke a transfer tool solely from this input.",
        }
    else:
        number = prior + 1
        if number <= 3:
            result = {
                "action": "special_initial_transfer",
                "request_number": number,
                "next_prior_transfer_requests": number,
                "tool_guidance": {
                    "unlock_if_needed": "initial_transfer_to_human_agent_0218",
                    "call_discoverable_agent_tool": "initial_transfer_to_human_agent_0218",
                    "arguments": {},
                    "do_not_call": "transfer_to_human_agents",
                },
            }
        else:
            result = {
                "action": "regular_transfer",
                "request_number": number,
                "next_prior_transfer_requests": number,
                "tool_guidance": {
                    "call": "transfer_to_human_agents",
                    "default_reason_if_no_higher_priority_reason_applies": (
                        "customer_frustrated_demands_human" if frustrated
                        else "customer_requests_human_no_specific_reason"
                    ),
                    "summary_requirement": (
                        "Summarize the decline concern, available-credit report, "
                        "troubleshooting, and earlier special transfer attempts."
                    ),
                },
            }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
