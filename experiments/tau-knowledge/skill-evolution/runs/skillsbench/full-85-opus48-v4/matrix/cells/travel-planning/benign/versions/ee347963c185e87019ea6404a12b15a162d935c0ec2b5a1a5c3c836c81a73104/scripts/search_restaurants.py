"""stdin: {"data_root":..., "city":..., "cuisine": optional}
stdout: {"restaurants":[{name,cost,cuisines,city}, ...]} (cheapest first).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from travel_db import TravelDB  # noqa: E402


def main():
    p = json.load(sys.stdin)
    db = TravelDB(p.get("data_root", "/app/data"))
    res = db.restaurants_in(p["city"])
    cui = p.get("cuisine")
    if cui:
        res = [r for r in res if cui.lower() in r["cuisines"].lower()]
    print(json.dumps({"restaurants": res}, ensure_ascii=False))


if __name__ == "__main__":
    main()
