#!/usr/bin/env python3
"""Fail-closed interpretation of replacement-order results.

Input: {"orders": [{"status": "delivered"}, ...]}
Output: {"clear_to_proceed": bool, "order_count": int|null, "blockers": [string]}
Only delivered and cancelled orders are final. An empty orders array passes.
"""
import json
import sys

FINAL = {"delivered", "cancelled"}


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or not isinstance(data.get("orders"), list):
            raise ValueError("expected an object containing an orders array")
        orders = data["orders"]
    except Exception as exc:
        print(json.dumps({"clear_to_proceed": False, "order_count": None,
                          "blockers": [f"ambiguous replacement-order response: {exc}"]}))
        return

    blockers = []
    for index, order in enumerate(orders):
        if not isinstance(order, dict):
            blockers.append(f"order {index} is malformed")
            continue
        status = order.get("status")
        if not isinstance(status, str) or status.strip().lower() not in FINAL:
            label = status if status is not None else "missing status"
            blockers.append(f"order {index} has non-final status: {label}")

    print(json.dumps({"clear_to_proceed": not blockers, "order_count": len(orders),
                      "blockers": blockers}))


if __name__ == "__main__":
    main()
