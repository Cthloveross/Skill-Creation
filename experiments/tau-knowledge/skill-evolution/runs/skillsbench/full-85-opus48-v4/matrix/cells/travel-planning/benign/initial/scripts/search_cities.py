"""stdin: {"data_root":..., "state":"Ohio"} -> stdout: {"cities":[...]}"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from travel_db import TravelDB  # noqa: E402


def main():
    p = json.load(sys.stdin)
    db = TravelDB(p.get("data_root", "/app/data"))
    print(json.dumps({"cities": db.cities_in_state(p["state"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
