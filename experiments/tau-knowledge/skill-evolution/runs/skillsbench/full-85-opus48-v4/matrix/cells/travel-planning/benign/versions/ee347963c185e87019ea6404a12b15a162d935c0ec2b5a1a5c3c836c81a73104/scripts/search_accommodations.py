"""stdin: {"data_root":..., "city":..., "people":2, "max_nights":2, "pet_friendly":true}
stdout: {"accommodations":[{name,price,occupancy,min_nights,rules,city}, ...]}
When pet_friendly is false, returns all rows for the city.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from travel_db import TravelDB  # noqa: E402


def main():
    p = json.load(sys.stdin)
    db = TravelDB(p.get("data_root", "/app/data"))
    city = p["city"]
    people = int(p.get("people", 1))
    max_nights = int(p.get("max_nights", 99))
    if p.get("pet_friendly", True):
        res = db.pet_friendly_accommodations(city, people=people, max_nights=max_nights)
    else:
        res = [a for a in db.accommodations() if a["city"].lower() == city.lower()]
    print(json.dumps({"accommodations": res}, ensure_ascii=False))


if __name__ == "__main__":
    main()
