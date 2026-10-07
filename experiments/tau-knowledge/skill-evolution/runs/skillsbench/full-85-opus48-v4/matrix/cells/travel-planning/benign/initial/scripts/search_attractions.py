"""stdin: {"data_root":..., "city":...} -> stdout: {"attractions":[name, ...]}"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from travel_db import TravelDB  # noqa: E402


def main():
    p = json.load(sys.stdin)
    db = TravelDB(p.get("data_root", "/app/data"))
    print(json.dumps({"attractions": db.attractions_in(p["city"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
