"""Reusable loaders and queries over TravelPlanner-style CSV databases.

Schema is discovered at runtime: column names are matched case-insensitively
with exact-then-substring candidates, so no fixed layout is assumed.
"""
import csv
import math
import os
import re

csv.field_size_limit(10 ** 7)


def _read_csv(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def find_col(fieldnames, *cands):
    fn = [c for c in fieldnames if c is not None]
    low = {c.lower().strip(): c for c in fn}
    for cand in cands:
        if cand.lower() in low:
            return low[cand.lower()]
    for cand in cands:
        for k, v in low.items():
            if cand.lower() in k:
                return v
    return None


def parse_number(val):
    if val is None:
        return None
    s = str(val).replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def load_cities_by_state(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if "\t" in line:
                parts = line.split("\t")
            else:
                parts = line.rsplit(" ", 1)
            if len(parts) < 2:
                continue
            city, state = parts[0].strip(), parts[1].strip()
            out.setdefault(state, []).append(city)
    return out


class TravelDB:
    def __init__(self, data_root="/app/data"):
        self.root = data_root
        self._acc = None
        self._res = None
        self._att = None
        self._dist = None
        self._cities = None

    # ---- paths ----
    def _p(self, *parts):
        return os.path.join(self.root, *parts)

    # ---- cities ----
    def cities_by_state(self):
        if self._cities is None:
            path = self._p("background", "citySet_with_states.txt")
            self._cities = load_cities_by_state(path)
        return self._cities

    def cities_in_state(self, state):
        d = self.cities_by_state()
        if state in d:
            return list(d[state])
        for k, v in d.items():
            if k.lower() == state.lower():
                return list(v)
        return []

    # ---- accommodations ----
    def accommodations(self):
        if self._acc is None:
            rows = _read_csv(self._p("accommodations", "clean_accommodations_2022.csv"))
            fn = list(rows[0].keys()) if rows else []
            c = {
                "name": find_col(fn, "NAME", "name", "accommodation"),
                "price": find_col(fn, "price"),
                "occ": find_col(fn, "maximum occupancy", "occupancy", "max occupancy"),
                "minn": find_col(fn, "minimum nights", "minimum night", "min nights"),
                "rules": find_col(fn, "house_rules", "house rules", "rules", "rule"),
                "city": find_col(fn, "city"),
            }
            out = []
            for r in rows:
                out.append({
                    "name": (r.get(c["name"]) or "").strip(),
                    "price": parse_number(r.get(c["price"])),
                    "occupancy": parse_number(r.get(c["occ"])),
                    "min_nights": parse_number(r.get(c["minn"])),
                    "rules": (r.get(c["rules"]) or "").strip(),
                    "city": (r.get(c["city"]) or "").strip(),
                })
            self._acc = out
        return self._acc

    def pet_friendly_accommodations(self, city, people=1, max_nights=99):
        res = []
        for a in self.accommodations():
            if a["city"].lower() != city.lower():
                continue
            if "no pets" in a["rules"].lower():
                continue
            if a["occupancy"] is not None and a["occupancy"] < people:
                continue
            if a["min_nights"] is not None and a["min_nights"] > max_nights:
                continue
            if not a["name"]:
                continue
            res.append(a)
        res.sort(key=lambda a: (a["price"] if a["price"] is not None else 1e12))
        return res

    # ---- restaurants ----
    def restaurants(self):
        if self._res is None:
            rows = _read_csv(self._p("restaurants", "clean_restaurant_2022.csv"))
            fn = list(rows[0].keys()) if rows else []
            c = {
                "name": find_col(fn, "Name", "NAME", "name", "restaurant"),
                "cost": find_col(fn, "Average Cost", "average_cost", "cost", "price"),
                "cuis": find_col(fn, "Cuisines", "cuisine", "cuisines"),
                "city": find_col(fn, "City", "city"),
            }
            out = []
            for r in rows:
                out.append({
                    "name": (r.get(c["name"]) or "").strip(),
                    "cost": parse_number(r.get(c["cost"])),
                    "cuisines": (r.get(c["cuis"]) or "").strip(),
                    "city": (r.get(c["city"]) or "").strip(),
                })
            self._res = out
        return self._res

    def restaurants_in(self, city):
        res = [r for r in self.restaurants()
               if r["city"].lower() == city.lower() and r["name"]]
        res.sort(key=lambda r: (r["cost"] if r["cost"] is not None else 1e12))
        return res

    # ---- attractions ----
    def attractions(self):
        if self._att is None:
            rows = _read_csv(self._p("attractions", "attractions.csv"))
            fn = list(rows[0].keys()) if rows else []
            c = {
                "name": find_col(fn, "Name", "NAME", "name"),
                "city": find_col(fn, "City", "city"),
            }
            out = []
            for r in rows:
                out.append({
                    "name": (r.get(c["name"]) or "").strip(),
                    "city": (r.get(c["city"]) or "").strip(),
                })
            self._att = out
        return self._att

    def attractions_in(self, city):
        seen = set()
        res = []
        for a in self.attractions():
            if a["city"].lower() == city.lower() and a["name"]:
                if a["name"].lower() in seen:
                    continue
                seen.add(a["name"].lower())
                res.append(a["name"])
        return res

    # ---- distance matrix ----
    def distance_map(self):
        if self._dist is None:
            rows = _read_csv(self._p("googleDistanceMatrix", "distance.csv"))
            fn = list(rows[0].keys()) if rows else []
            c = {
                "src": find_col(fn, "source", "origin", "from"),
                "dst": find_col(fn, "destination", "dest", "to"),
                "dist": find_col(fn, "distance"),
                "dur": find_col(fn, "duration"),
                "cost": find_col(fn, "cost"),
            }
            m = {}
            for r in rows:
                s = (r.get(c["src"]) or "").strip()
                d = (r.get(c["dst"]) or "").strip()
                if not s or not d:
                    continue
                m[(s.lower(), d.lower())] = {
                    "distance": parse_number(r.get(c["dist"])),
                    "duration": r.get(c["dur"]),
                    "cost": parse_number(r.get(c["cost"])),
                }
            self._dist = m
        return self._dist

    def leg(self, a, b):
        return self.distance_map().get((a.lower(), b.lower()))

    def driving_cost(self, a, b, people=1):
        """Self-driving cost: distance_km * 0.05 per car; 1 car per 5 people."""
        info = self.leg(a, b)
        if not info or info.get("distance") is None:
            return None
        cars = math.ceil(people / 5) or 1
        return int(round(cars * info["distance"] * 0.05))


def cuisines_of(restaurant):
    return restaurant["cuisines"].lower()
