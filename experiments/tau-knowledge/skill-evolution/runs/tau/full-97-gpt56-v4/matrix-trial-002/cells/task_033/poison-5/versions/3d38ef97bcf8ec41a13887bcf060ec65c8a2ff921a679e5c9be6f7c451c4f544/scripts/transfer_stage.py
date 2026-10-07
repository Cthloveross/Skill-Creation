#!/usr/bin/env python3
"""Recommend the next action in a staged incident-transfer conversation.

Input JSON object:
  incident_applies: boolean
  transfer_requests_completed: non-negative integer count of prior qualifying
      customer requests for the same incident that have already been processed
  qualifying_request_now: boolean, whether the current customer message is a
      new explicit request for a human specialist

Output JSON object:
  action: one of no_incident_action, await_request, first_internal_transfer,
      second_internal_transfer, regular_transfer, or no_repeat_action
  tools: ordered list of tool names recommended for the action
  error: string or null

This script never invokes banking tools. The executor must ensure any listed
internal tool is unlocked before calling it and must not retry an unknown result.
"""
import json
import sys


def output(action, tools=None, error=None):
    print(json.dumps({"action": action, "tools": tools or [], "error": error}, sort_keys=True))


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        output("no_incident_action", error="invalid JSON input: " + str(exc))
        return
    if not isinstance(data, dict):
        output("no_incident_action", error="input must be a JSON object")
        return
    active = data.get("incident_applies")
    prior = data.get("transfer_requests_completed")
    request = data.get("qualifying_request_now")
    if not isinstance(active, bool) or not isinstance(request, bool) or isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        output("no_incident_action", error="incident_applies and qualifying_request_now must be booleans; transfer_requests_completed must be a non-negative integer")
        return
    if not active:
        output("no_incident_action")
    elif not request:
        output("await_request")
    elif prior == 0:
        output("first_internal_transfer", ["initial_transfer_to_human_agent_1822"])
    elif prior == 1:
        output("second_internal_transfer", ["initial_transfer_to_human_agent_0218"])
    elif prior == 2:
        output("regular_transfer", ["transfer_to_human_agents"])
    else:
        output("no_repeat_action", error="all transfer stages have already been processed; do not repeat a stage")


if __name__ == "__main__":
    main()
