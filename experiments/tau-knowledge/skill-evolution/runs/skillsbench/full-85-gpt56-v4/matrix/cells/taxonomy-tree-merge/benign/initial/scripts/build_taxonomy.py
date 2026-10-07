#!/usr/bin/env python3
"""Create a normalized, traceable five-column product taxonomy.

Read one JSON request from stdin and write one JSON result to stdout.  No third
party packages are required.  See ../SKILL.md for the request schema.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

FULL_COLUMNS = [
    "source", "category_path", "depth", "unified_level_1", "unified_level_2",
    "unified_level_3", "unified_level_4", "unified_level_5",
]
HIER_COLUMNS = FULL_COLUMNS[3:]
DEFAULT_FILES = {
    "amazon": "amazon_product_categories.csv",
    "facebook": "fb_product_categories.csv",
    "google": "google_shopping_product_categories.csv",
}

# The vocabulary is deliberately generic reusable commerce vocabulary, rather
# than a table of current input labels.  Ordered keyword scoring resolves paths
# that contain terms belonging to more than one domain.
DOMAINS = {
    "Apparel | Accessories": "apparel clothing shoe boot sandal sneaker dress shirt pant jean jacket coat underwear sock hat handbag purse wallet belt eyewear sunglass fashion".split(),
    "Beauty | Personal | Care": "beauty cosmetic makeup skin hair fragrance perfume grooming shaving nail lotion personal care".split(),
    "Home | Garden": "home garden furniture kitchen bedding bath decor lighting appliance patio lawn household cookware".split(),
    "Electronics | Computing": "electronic computer laptop desktop tablet phone mobile television audio video camera printer network software component".split(),
    "Sports | Outdoors": "sport fitness exercise outdoor camping hunting fishing cycling bicycle golf team athletic recreation".split(),
    "Toys | Games": "toy game puzzle doll hobby model playset gaming boardgame".split(),
    "Automotive | Industrial": "automotive vehicle car truck motorcycle tire wheel engine industrial tool hardware material safety".split(),
    "Food | Beverage": "food beverage grocery drink snack candy coffee tea pantry meal ingredient".split(),
    "Health | Wellness": "health wellness medical medicine pharmacy supplement vitamin therapy mobility dental".split(),
    "Baby | Kids": "baby infant toddler nursery child kids juvenile stroller diaper".split(),
    "Pet | Supplies": "pet dog cat bird fish aquarium reptile animal veterinary".split(),
    "Books | Media": "book magazine music movie film media cd dvd vinyl instrument publication".split(),
    "Office | School": "office school stationery paper writing pen classroom education business filing".split(),
    "Jewelry | Watches": "jewelry jewellery watch ring necklace bracelet earring gemstone".split(),
    "Arts | Crafts": "art craft sewing fabric yarn knitting scrapbook paint drawing handmade".split(),
    "Travel | Luggage": "travel luggage suitcase bag backpack luggage travelgear".split(),
}

# Families avoid the words used in their parent domain.  They cap direct root
# breadth well below 20, while keyword matching still uses a broad vocabulary.
FAMILIES = {
    "Apparel | Accessories": [
        ("Women", "women woman ladies female"), ("Men", "men man male"),
        ("Children", "child children kid boys girls infant"), ("Footwear", "shoe boot sandal sneaker slipper"),
        ("Bags | Wallets", "bag handbag purse wallet"), ("Headwear", "hat cap headwear"),
        ("Belts | Gloves", "belt glove scarf"), ("Intimates", "underwear bra lingerie sleepwear"),
        ("Outerwear", "coat jacket rainwear"), ("Clothing", "dress shirt pant jean skirt sweater apparel clothing"),
    ],
    "Beauty | Personal | Care": [
        ("Skin", "skin face lotion cream cleanser"), ("Hair", "hair shampoo conditioner styling"),
        ("Makeup", "makeup cosmetic lipstick foundation mascara"), ("Fragrance", "fragrance perfume cologne"),
        ("Nails", "nail manicure pedicure"), ("Shaving", "shaving razor beard"),
        ("Bath", "bath soap body wash"), ("Tools", "brush applicator mirror tool"),
    ],
    "Home | Garden": [
        ("Furniture", "furniture chair table sofa bed desk"), ("Kitchen", "kitchen cookware dining bakeware"),
        ("Bedding", "bedding mattress pillow blanket linen"), ("Bath", "bath towel shower toilet"),
        ("Decor", "decor decoration rug curtain candle"), ("Lighting", "lighting lamp bulb"),
        ("Garden", "garden lawn plant patio outdoor"), ("Storage", "storage organization container"),
        ("Household", "cleaning laundry household"), ("Appliances", "appliance vacuum refrigerator washer"),
    ],
    "Electronics | Computing": [
        ("Computers", "computer laptop desktop monitor keyboard mouse"), ("Mobile | Devices", "phone mobile tablet smartwatch"),
        ("Audio", "audio speaker headphone microphone"), ("Television | Video", "television tv video projector"),
        ("Cameras", "camera camcorder lens photography"), ("Gaming", "gaming console controller videogame"),
        ("Networking", "network router modem wireless"), ("Components", "component memory processor drive motherboard"),
        ("Printing", "printer ink toner scanner"), ("Cables | Power", "cable charger battery power adapter"),
    ],
    "Sports | Outdoors": [
        ("Fitness", "fitness exercise workout gym"), ("Team | Sports", "baseball basketball football soccer hockey tennis"),
        ("Cycling", "cycling bicycle bike"), ("Golf", "golf"), ("Camping", "camping tent hiking"),
        ("Fishing", "fishing tackle"), ("Hunting", "hunting shooting"), ("Water | Sports", "swim swimming boating kayak surf"),
        ("Athletic | Gear", "athletic sport equipment"),
    ],
    "Toys | Games": [
        ("Games", "game boardgame cardgame puzzle"), ("Dolls", "doll figure plush"),
        ("Building", "building block construction"), ("Models", "model miniature"),
        ("Learning", "learning educational science"), ("Outdoor | Play", "outdoor play swing"),
        ("Hobbies", "hobby collectible"),
    ],
    "Automotive | Industrial": [
        ("Vehicle | Parts", "part engine brake exhaust"), ("Wheels | Tires", "wheel tire"),
        ("Tools", "tool equipment"), ("Maintenance", "oil fluid filter maintenance"),
        ("Interior", "interior seat floor"), ("Exterior", "exterior body windshield"),
        ("Safety", "safety protective"), ("Hardware", "hardware fastener material"),
    ],
    "Food | Beverage": [
        ("Pantry", "pantry grocery ingredient"), ("Snacks", "snack candy cookie"),
        ("Drinks", "drink beverage juice soda"), ("Coffee | Tea", "coffee tea"),
        ("Fresh | Food", "fresh produce meat dairy"), ("Cooking", "cooking meal sauce spice"),
    ],
    "Health | Wellness": [
        ("Supplements", "supplement vitamin mineral"), ("Medical", "medical healthcare diagnostic"),
        ("Mobility", "mobility wheelchair walker"), ("Dental", "dental oral"),
        ("Therapy", "therapy massage rehabilitation"), ("Pharmacy", "medicine pharmacy"),
    ],
    "Baby | Kids": [
        ("Nursery", "nursery crib bedding"), ("Feeding", "feeding bottle formula"),
        ("Diapering", "diaper wipe"), ("Strollers", "stroller carrier carseat"),
        ("Clothing", "clothing apparel shoe"), ("Safety", "safety monitor gate"), ("Play", "play toy game"),
    ],
    "Pet | Supplies": [
        ("Dogs", "dog canine puppy"), ("Cats", "cat feline kitten"), ("Fish | Aquatic", "fish aquarium aquatic"),
        ("Birds", "bird avian"), ("Small | Animals", "small animal hamster rabbit"),
        ("Food", "food treat feeding"), ("Care", "care grooming health"),
    ],
    "Books | Media": [
        ("Books", "book publication"), ("Music", "music cd vinyl audio"),
        ("Movies", "movie film dvd"), ("Instruments", "instrument musical"),
        ("Magazines", "magazine"), ("Digital | Media", "digital software media"),
    ],
    "Office | School": [
        ("Writing", "writing pen pencil marker"), ("Paper", "paper notebook label"),
        ("Filing", "filing folder binder"), ("Desk | Supplies", "desk stapler tape"),
        ("Classroom", "classroom school education"), ("Business | Machines", "business calculator machine"),
    ],
    "Jewelry | Watches": [
        ("Rings", "ring"), ("Necklaces", "necklace pendant"), ("Earrings", "earring"),
        ("Bracelets", "bracelet"), ("Watches", "watch"), ("Gemstones", "gemstone bead"),
        ("Storage", "storage box display"),
    ],
    "Arts | Crafts": [
        ("Painting", "paint brush canvas"), ("Drawing", "drawing pencil sketch"),
        ("Sewing", "sewing needle thread"), ("Yarn | Fiber", "yarn knitting crochet"),
        ("Fabric", "fabric textile"), ("Paper | Crafts", "paper scrapbook"),
        ("Beads", "bead jewelry"),
    ],
    "Travel | Luggage": [
        ("Suitcases", "suitcase luggage"), ("Backpacks", "backpack"), ("Travel | Bags", "travel bag duffel"),
        ("Organizers", "organizer packing"), ("Travel | Accessories", "passport adapter travel accessory"),
    ],
}

STOP = set("and or for the a an with without of to in on by from accessories accessory supplies supply products product items item general specialty selection department".split())


def tokens(text: str) -> list[str]:
    return [x for x in re.findall(r"[a-z0-9]+", text.lower()) if x not in STOP]


def singular(word: str) -> str:
    # Conservative normalization avoids damaging common singular words.
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("ses"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("&", " and ").replace("/", " ").replace("|", " ")
    value = re.sub(r"[>'`\"(),;:_+*=\\[\]{}-]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return " ".join(singular(x) for x in value.split())


def display(words: list[str] | str) -> str:
    if isinstance(words, str):
        words = words.split()
    words = [w for w in words if w]
    return " | ".join(w.capitalize() for w in words[:5])


def split_path(raw: str) -> list[str]:
    parts = re.split(r"\s*>\s*|\s*::\s*", raw.strip())
    return [clean_text(p) for p in parts if clean_text(p)]


def best_domain(words: set[str]) -> str:
    scored = []
    for name, vocab in DOMAINS.items():
        score = sum(1 for w in vocab if singular(w) in words)
        scored.append((score, name))
    score, name = max(scored)
    # Unknown retail paths need a stable valid home, but normal e-commerce
    # paths generally match one of the semantic vocabularies above.
    return name if score else "Home | Garden"


def best_family(domain: str, words: set[str]) -> str:
    options = FAMILIES[domain]
    scores = [(sum(1 for w in vocab.split() if singular(w) in words), label) for label, vocab in options]
    score, label = max(scores)
    if score:
        return label
    # A real descriptive fallback is preferred to forbidden Other/Misc. It is
    # used only for paths that have no reusable family keyword.
    candidate = next((w for w in sorted(words) if len(w) > 2), "Selection")
    return display([candidate, "selection"])


def label_tokens(label: str) -> set[str]:
    return set(tokens(clean_text(label)))


def terminal_candidate(parts: list[str], parent_words: set[str]) -> str | None:
    for part in reversed(parts):
        ws = [w for w in tokens(part) if w not in parent_words]
        if ws:
            return display(ws)
    return None


def overlap(a: str, b: str) -> float:
    aa, bb = label_tokens(a), label_tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / min(len(aa), len(bb))


def load_rows(input_dir: Path, files: dict[str, str]) -> list[dict]:
    rows = []
    for source, filename in files.items():
        path = input_dir / filename
        if not path.is_file():
            raise ValueError(f"missing input file for {source}: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise ValueError(f"{path} has no CSV header")
            match = next((h for h in reader.fieldnames if h and h.strip().lower() == "category_path"), None)
            if not match:
                raise ValueError(f"{path} has no category_path column; columns={reader.fieldnames}")
            for lineno, row in enumerate(reader, 2):
                raw = (row.get(match) or "").strip()
                if not raw:
                    raise ValueError(f"empty category_path in {path} at CSV row {lineno}")
                parts = split_path(raw)
                if not parts:
                    raise ValueError(f"unusable category_path in {path} at CSV row {lineno}")
                ws = set(tokens(" ".join(parts)))
                domain = best_domain(ws)
                family = best_family(domain, ws)
                rows.append({"source": source, "category_path": raw, "parts": parts,
                             "domain": domain, "family": family})
    if not rows:
        raise ValueError("no input category rows")
    return rows


def assign_third_levels(rows: list[dict]) -> None:
    """Keep source-derived terminal labels only in naturally manageable groups."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row["domain"], row["family"])].append(row)
    for (domain, family), members in groups.items():
        parent = label_tokens(domain) | label_tokens(family)
        candidates = [terminal_candidate(r["parts"], parent) for r in members]
        unique = sorted({x for x in candidates if x})
        # Exact labels provide 100% lexical representation for their assigned
        # records. Suppress an over-wide branch instead of creating vague bins.
        acceptable = 3 <= len(unique) <= 20
        if acceptable:
            for a, b in combinations(unique, 2):
                if overlap(a, b) >= 0.30:
                    acceptable = False
                    break
        if acceptable:
            for row, candidate in zip(members, candidates):
                row["third"] = candidate
        else:
            for row in members:
                row["third"] = None


def mapped_rows(rows: list[dict]) -> list[dict]:
    assign_third_levels(rows)
    output = []
    for row in rows:
        levels = [row["domain"], row["family"], row.get("third"), None, None]
        depth = max(i + 1 for i, value in enumerate(levels) if value)
        out = {"source": row["source"], "category_path": row["category_path"], "depth": depth}
        out.update({f"unified_level_{i + 1}": levels[i] or "" for i in range(5)})
        output.append(out)
    return output


def validate(full: list[dict], original_count: int) -> list[str]:
    if len(full) != original_count:
        raise ValueError(f"mapping coverage failure: {len(full)} rows for {original_count} input rows")
    roots = sorted({r["unified_level_1"] for r in full})
    if not 10 <= len(roots) <= 20:
        raise ValueError(f"top-level root count {len(roots)} is outside required 10-20")
    hierarchy = {tuple(r[c] for c in HIER_COLUMNS) for r in full}
    warnings = []
    children = defaultdict(set)
    for r in full:
        levels = [r[c] for c in HIER_COLUMNS]
        if not levels[0]:
            raise ValueError("unrooted mapping row")
        seen_blank = False
        for value in levels:
            if not value:
                seen_blank = True
            elif seen_blank:
                raise ValueError("mapping has a nonblank level below a blank level")
            elif len(tokens(value)) > 5:
                raise ValueError(f"category label exceeds five words: {value}")
        if int(r["depth"]) != sum(1 for v in levels if v):
            raise ValueError("depth does not equal populated unified levels")
        for level in range(1, 5):
            parent = tuple(levels[:level])
            child = levels[level]
            if child:
                if label_tokens(levels[level - 1]) & label_tokens(child):
                    raise ValueError(f"parent/child name overlap: {levels[level - 1]} > {child}")
                children[parent].add(child)
    for parent, names in children.items():
        if len(names) > 20:
            raise ValueError(f"too many children ({len(names)}) under {' > '.join(parent)}")
        if len(names) < 3:
            warnings.append(f"sparse observed branch ({len(names)} children): {' > '.join(parent)}")
        for a, b in combinations(sorted(names), 2):
            if overlap(a, b) >= 0.30:
                raise ValueError(f"sibling word overlap >=30%: {a} / {b}")
    # Projection is constructed from mapping rows; retain this explicit check
    # to protect future changes to hierarchy writing logic.
    if not hierarchy:
        raise ValueError("empty hierarchy projection")
    return sorted(set(warnings))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main(request: dict) -> dict:
    input_dir = Path(request.get("input_dir", "/root/data"))
    output_dir = Path(request.get("output_dir", "/root/output"))
    files = request.get("source_files", DEFAULT_FILES)
    if not isinstance(files, dict) or not files:
        raise ValueError("source_files must be a nonempty object of source: filename")
    raw = load_rows(input_dir, {str(k): str(v) for k, v in files.items()})
    full = mapped_rows(raw)
    warnings = validate(full, len(raw))
    output_dir.mkdir(parents=True, exist_ok=True)
    full_path = output_dir / "unified_taxonomy_full.csv"
    hierarchy_path = output_dir / "unified_taxonomy_hierarchy.csv"
    write_csv(full_path, FULL_COLUMNS, full)
    tuples = sorted({tuple(r[c] for c in HIER_COLUMNS) for r in full})
    hierarchy_rows = [dict(zip(HIER_COLUMNS, values)) for values in tuples]
    write_csv(hierarchy_path, HIER_COLUMNS, hierarchy_rows)
    distribution = defaultdict(Counter)
    for row in full:
        distribution[row["unified_level_1"]][row["source"]] += 1
    result = {
        "ok": not (request.get("strict_quality", False) and warnings),
        "full_path": str(full_path), "hierarchy_path": str(hierarchy_path),
        "input_rows": len(raw), "mapping_rows": len(full), "hierarchy_rows": len(hierarchy_rows),
        "roots": sorted({r["unified_level_1"] for r in full}),
        "source_distribution_by_root": {k: dict(sorted(v.items())) for k, v in sorted(distribution.items())},
        "warnings": warnings,
    }
    if request.get("strict_quality", False) and warnings:
        raise ValueError("quality warnings in strict mode: " + "; ".join(warnings))
    return result


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(request), ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stdout)
        sys.exit(1)
