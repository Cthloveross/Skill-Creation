"""stdin: {"data_root":..., "from":A, "to":B, "people":2}
stdout: {"leg": {distance,duration,cost} or null, "self_driving_cost": int or null}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from travel_db import TravelDB  # noqa: E402


def main():
    p = json.load(sys.stdin)
    db = TravelDB(p.get("data_root", "/app/data"))
    a, b = p["from"], p["to"]
    print(json.dumps({
        "leg": db.leg(a, b),
        "self_driving_cost": db.driving_cost(a, b, people=int(p.get("people", 1))),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
