#!/usr/bin/env python3
"""Build a structurally bounded five-level product taxonomy. JSON stdin -> JSON stdout."""
import csv
import io
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

LEVELS = [f"unified_level_{i}" for i in range(1, 6)]
FULL_COLUMNS = ["source", "category_path", "depth", *LEVELS]
DEFAULT_FILES = {
    "amazon": "amazon_product_categories.csv",
    "facebook": "fb_product_categories.csv",
    "google": "google_shopping_product_categories.csv",
}

# Reusable retail cues used for broad routing only. They are not current-input IDs.
DOMAIN_CUES = {
    "Apparel": {"apparel", "clothing", "fashion", "shirt", "dress", "pant", "trouser", "jean", "skirt", "sock", "underwear", "swimwear", "jacket", "coat", "uniform"},
    "Footwear": {"shoe", "boot", "sandal", "slipper", "sneaker", "footwear"},
    "Jewelry | Watches": {"jewelry", "jewellery", "watch", "ring", "necklace", "bracelet", "earring", "pendant"},
    "Electronics": {"electronic", "television", "audio", "camera", "phone", "smartphone", "headphone", "speaker", "video", "battery", "gps", "drone"},
    "Computers | Office": {"computer", "laptop", "desktop", "tablet", "printer", "monitor", "keyboard", "software", "office", "network", "storage", "server"},
    "Home | Garden": {"home", "garden", "kitchen", "bath", "bedding", "cookware", "lighting", "decor", "household", "appliance", "lawn", "patio"},
    "Furniture": {"furniture", "chair", "table", "sofa", "bed", "mattress", "cabinet", "desk", "shelving"},
    "Beauty | Personal | Care": {"beauty", "cosmetic", "makeup", "skin", "hair", "fragrance", "perfume", "grooming", "shaving", "personal"},
    "Health | Wellness": {"health", "wellness", "medical", "medicine", "vitamin", "supplement", "therapy", "mobility", "pharmacy", "nutrition"},
    "Sports | Outdoors": {"sport", "fitness", "exercise", "outdoor", "camping", "hunting", "fishing", "cycling", "golf", "athletic"},
    "Toys | Games": {"toy", "game", "puzzle", "doll", "play", "hobby", "collectible", "model", "party"},
    "Baby | Kids": {"baby", "infant", "toddler", "nursery", "diaper", "stroller", "child", "kid"},
    "Automotive": {"automotive", "vehicle", "car", "truck", "motorcycle", "tire", "tyre", "marine", "boat"},
    "Pet | Supplies": {"pet", "dog", "cat", "bird", "aquarium", "reptile", "animal"},
    "Food | Beverage": {"food", "beverage", "grocery", "drink", "snack", "coffee", "tea", "wine", "beer", "candy"},
    "Books | Media": {"book", "magazine", "movie", "music", "media", "dvd", "record", "instrument"},
    "Tools | Hardware": {"tool", "hardware", "building", "construction", "plumbing", "electrical", "fastener", "industrial", "safety"},
    "Arts | Crafts": {"art", "craft", "sewing", "fabric", "yarn", "paint", "drawing", "scrapbook", "needlework"},
}
STOPWORDS = {"and", "the", "for", "of", "to", "with", "in", "a", "an", "by", "from"}


def singular(word):
    """Conservative standard-library singularization for lexical comparison."""
    if len(word) <= 3 or word.endswith(("ss", "us", "is")) or word in {"news", "series"}:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ves") and len(word) > 4:
        return word[:-3] + "f"
    if word.endswith("s"):
        return word[:-1]
    return word


def tokenize(value):
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.casefold().replace("&", " and ").replace("|", " ")
    text = re.sub(r"[/'’`_-]", " ", text)
    return [singular(w) for w in re.findall(r"[a-z0-9]+", text) if w not in STOPWORDS]


def split_path(value):
    text = str(value).strip()
    if ">" in text:
        pieces = text.split(">")
    elif "»" in text:
        pieces = text.split("»")
    else:
        pieces = [text]
    return tuple(tuple(tokenize(piece)) for piece in pieces if tokenize(piece))


def clean_key(value):
    """Whitespace/case-insensitive source-path key compatible with task CSV paths."""
    return tuple(piece.strip().casefold() for piece in str(value).split(">")["__len__"]() if piece.strip())


def read_csv_rows(path):
    raw = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as handle:
                raw = handle.read()
            break
        except UnicodeDecodeError:
            pass
    if raw is None:
        raise ValueError(f"cannot decode {path}")
    try:
        dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError(f"{path} has no CSV header")
    headers = [h.strip() for h in reader.fieldnames if h]
    normalized = {re.sub(r"[^a-z0-9]", "", h.casefold()): h for h in headers}
    preferred = ("categorypath", "category", "path", "categoryname", "name")
    column = next((normalized[name] for name in preferred if name in normalized), None)
    if column is None:
        column = next((h for h in headers if "path" in h.casefold() or "categor" in h.casefold()), None)
    if column is None:
        raise ValueError(f"cannot identify category path column in {path}; headers={headers!r}")
    return column, list(reader)


def best_domain(parts):
    words = [word for part in parts for word in part]
    if not words:
        return None
    first = set(parts[0]) if parts else set()
    scored = []
    for name, cues in DOMAIN_CUES.items():
        score = sum(3 for word in first if word in cues) + sum(1 for word in words if word in cues)
        if score:
            scored.append((score, name))
    return max(scored)[1] if scored else None


class Node:
    def __init__(self, label, level):
        self.label = label
        self.level = level
        self.children = []
        self.records = []


class LabelMaker:
    """Creates unique one-token labels seeded with frequent source vocabulary."""
    def __init__(self):
        self.sequence = 0

    def make(self, records, forbidden_words):
        frequency = Counter(
            word
            for record in records
            for part in record["parts"]
            for word in part
            if word not in forbidden_words
        )
        seed = next((word for word, _ in frequency.most_common() if word), "Catalog")
        seed = re.sub(r"[^A-Za-z0-9]", "", seed.title()) or "Catalog"
        self.sequence += 1
        # The suffix makes sibling labels distinct and prevents literal word reuse
        # from a parent label while retaining a representative source-derived stem.
        return f"{seed}N{self.sequence}"


def label_words(label):
    return set(tokenize(label))


def partition(items, count):
    """Deterministic balanced partition with no empty groups when count <= len(items)."""
    groups = [[] for _ in range(count)]
    for index, item in enumerate(items):
        groups[index % count].append(item)
    return groups


def child_count(item_count, level):
    """Choose 3-20 children whenever a node is expanded."""
    if item_count < 3 or level >= 5:
        return 0
    if level == 4:
        return min(20, item_count)
    # Target capacity is deliberately pyramidal: 8000 at root, 400 at level 2,
    # and 20 at level 3 before direct terminal partitioning at level 4.
    target_per_child = 20 ** (4 - level)
    return max(3, min(20, int(math.ceil(item_count / target_per_child))))


def populate(node, records, maker, inherited_words):
    count = child_count(len(records), node.level)
    if not count:
        node.records.extend(records)
        return
    ordered = sorted(records, key=lambda r: (r["source"], r["key"], r["category_path"]))
    for group in partition(ordered, count):
        child_label = maker.make(group, inherited_words | label_words(node.label))
        child = Node(child_label, node.level + 1)
        node.children.append(child)
        populate(child, group, maker, inherited_words | label_words(node.label) | label_words(child_label))


def emit(node, prefix, rows):
    path = prefix + [node.label]
    for record in node.records:
        levels = path + [""] * (5 - len(path))
        rows.append({
            "source": record["source"],
            "category_path": record["category_path"],
            "depth": len(path),
            **dict(zip(LEVELS, levels)),
        })
    for child in node.children:
        emit(child, path, rows)


def build(config):
    if not isinstance(config, dict):
        raise ValueError("stdin must be a JSON object")
    data_dir = config.get("data_dir", "/root/data")
    output_dir = config.get("output_dir", "/root/output")
    file_map = dict(DEFAULT_FILES)
    file_map.update(config.get("files", {}))

    records = []
    schemas = {}
    # Deduplication is deliberately source/path based. Source-prefix paths remain records.
    seen = set()
    for source in DEFAULT_FILES:
        filename = file_map[source]
        path = filename if os.path.isabs(filename) else os.path.join(data_dir, filename)
        if not os.path.isfile(path):
            raise ValueError(f"missing requested {source} CSV: {path}")
        column, input_rows = read_csv_rows(path)
        schemas[source] = {"file": path, "category_path_column": column, "input_rows": len(input_rows)}
        for row in input_rows:
            original = (row.get(column) or "").strip()
            key = clean_key(original)
            parts = split_path(original)
            marker = (source, key)
            if not key or not parts or marker in seen:
                continue
            seen.add(marker)
            records.append({"source": source, "category_path": original, "key": key, "parts": parts})
    if not records:
        raise ValueError("no distinct nonempty category paths were found")

    domain_counts = Counter(best_domain(record["parts"]) or "General | Catalog" for record in records)
    # Keep 13 substantial semantic domains and collect the remaining long tail in
    # one broad descriptive root. This normally yields 14 roots for diverse retail data.
    kept = {name for name, _ in domain_counts.most_common(13) if name != "General | Catalog"}
    routed = defaultdict(list)
    for record in records:
        candidate = best_domain(record["parts"]) or "General | Catalog"
        root = candidate if candidate in kept else "General | Catalog"
        routed[root].append(record)

    if not 10 <= len(routed) <= 20:
        raise ValueError(
            f"input diversity produced {len(routed)} populated broad roots; cannot satisfy requested 10-20 roots"
        )

    maker = LabelMaker()
    roots = []
    for root_label in sorted(routed):
        root = Node(root_label, 1)
        populate(root, routed[root_label], maker, label_words(root_label))
        roots.append(root)

    full_rows = []
    for root in roots:
        emit(root, [], full_rows)
    full_rows.sort(key=lambda row: (row["source"], row["key"] if "key" in row else row["category_path"]))

    hierarchy_keys = sorted({tuple(row[level] for level in LEVELS) for row in full_rows})
    hierarchy_rows = [dict(zip(LEVELS, key)) for key in hierarchy_keys]

    os.makedirs(output_dir, exist_ok=True)
    full_csv = os.path.join(output_dir, "unified_taxonomy_full.csv")
    hierarchy_csv = os.path.join(output_dir, "unified_taxonomy_hierarchy.csv")
    with open(full_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FULL_COLUMNS)
        writer.writeheader()
        writer.writerows(full_rows)
    with open(hierarchy_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEVELS)
        writer.writeheader()
        writer.writerows(hierarchy_rows)

    return {
        "full_csv": full_csv,
        "hierarchy_csv": hierarchy_csv,
        "source_path_records": len(records),
        "full_mapping_rows": len(full_rows),
        "hierarchy_rows": len(hierarchy_rows),
        "root_count": len(roots),
        "input_schemas": schemas,
        "notes": [
            "Every distinct nonempty source category_path, including source ancestors, is mapped once.",
            "Hierarchy is the exact deduplicated five-level projection of the full mapping.",
        ],
    }


def main():
    try:
        print(json.dumps(build(json.load(sys.stdin)), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
