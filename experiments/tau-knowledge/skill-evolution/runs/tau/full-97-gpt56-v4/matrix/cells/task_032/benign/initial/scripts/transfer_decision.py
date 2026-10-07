#!/usr/bin/env python3
"""Plan the staged transfer action; read one JSON object from stdin, emit one JSON object."""
import json
import sys


def fail(message):
    print(json.dumps({"supported": False, "error": message}, sort_keys=True))
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        return fail("input must be one JSON object: " + str(exc))
    if not isinstance(data, dict):
        return fail("input must be a JSON object")

    count = data.get("explicit_transfer_requests_so_far")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return fail("explicit_transfer_requests_so_far must be a non-negative integer")
    if data.get("declines_despite_available_credit") is not True:
        return fail("special protocol applies only to purchase declines despite available credit")
    if data.get("new_request_is_explicit") is not True:
        return fail("no new explicit transfer request to process")

    updated = count + 1
    result = {
        "supported": True,
        "updated_transfer_request_count": updated,
    }
    if updated <= 3:
        result.update({
            "action": "special_discoverable_transfer",
            "unlock_agent_tool_name": "initial_transfer_to_human_agent_0218",
            "call_agent_tool_name": "initial_transfer_to_human_agent_0218",
            "arguments": {},
            "standard_transfer_allowed": False,
        })
    elif updated == 4:
        frustrated = data.get("customer_frustrated") is True
        result.update({
            "action": "standard_transfer",
            "standard_transfer_allowed": True,
            "recommended_reason": (
                "customer_frustrated_demands_human" if frustrated
                else "customer_requests_human_no_specific_reason"
            ),
        })
    else:
        result.update({
            "action": "standard_transfer",
            "standard_transfer_allowed": True,
            "note": "Use the highest-priority currently applicable reason code; later requests are outside the special first-three restriction.",
        })
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
