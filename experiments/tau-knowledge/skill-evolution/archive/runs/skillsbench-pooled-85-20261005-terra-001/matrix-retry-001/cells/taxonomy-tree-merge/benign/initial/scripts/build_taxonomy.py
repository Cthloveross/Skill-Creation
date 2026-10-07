#!/usr/bin/env python3
"""Build a five-level unified product taxonomy. JSON stdin -> JSON stdout."""
import csv
import io
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

LEVEL_COLUMNS = [f"unified_level_{i}" for i in range(1, 6)]
FULL_COLUMNS = ["source", "category_path", "depth"] + LEVEL_COLUMNS
DEFAULT_FILES = {
    "amazon": "amazon_product_categories.csv",
    "facebook": "fb_product_categories.csv",
    "google": "google_shopping_product_categories.csv",
}

# These are reusable broad retail-domain cues, not identifiers or labels copied
# from a current input.  They only select a root when input tokens support it.
DOMAIN_CUES = {
    "Apparel": {"apparel", "clothing", "fashion", "shirt", "dress", "pants", "trouser", "jean", "skirt", "sock", "underwear", "swimwear", "jacket", "coat", "uniform"},
    "Footwear": {"shoe", "boot", "sandal", "slipper", "sneaker", "footwear"},
    "Jewelry | Watches": {"jewelry", "jewellery", "watch", "ring", "necklace", "bracelet", "earring", "pendant"},
    "Electronics": {"electronic", "television", "audio", "camera", "phone", "smartphone", "headphone", "speaker", "video", "battery", "gps", "drone"},
    "Computers | Office": {"computer", "laptop", "desktop", "tablet", "printer", "monitor", "keyboard", "software", "office", "network", "storage", "server"},
    "Home | Garden": {"home", "garden", "kitchen", "bath", "bedding", "cookware", "lighting", "decor", "household", "appliance", "lawn", "patio"},
    "Furniture": {"furniture", "chair", "table", "sofa", "bed", "mattress", "cabinet", "desk", "shelving"},
    "Beauty | Personal | Care": {"beauty", "cosmetic", "makeup", "skin", "hair", "fragrance", "perfume", "grooming", "shaving", "personal"},
    "Health | Wellness": {"health", "wellness", "medical", "medicine", "vitamin", "supplement", "therapy", "mobility", "pharmacy", "nutrition"},
    "Sports | Outdoors": {"sport", "fitness", "exercise", "outdoor", "camping", "hunting", "fishing", "cycling", "golf", "team", "athletic"},
    "Toys | Games": {"toy", "game", "puzzle", "doll", "play", "hobby", "collectible", "model", "party"},
    "Baby | Kids": {"baby", "infant", "toddler", "nursery", "diaper", "stroller", "child", "kid"},
    "Automotive": {"automotive", "vehicle", "car", "truck", "motorcycle", "tire", "tyre", "rv", "marine", "boat"},
    "Pet | Supplies": {"pet", "dog", "cat", "bird", "aquarium", "reptile", "animal"},
    "Food | Beverage": {"food", "beverage", "grocery", "drink", "snack", "coffee", "tea", "wine", "beer", "candy"},
    "Books | Media": {"book", "magazine", "movie", "music", "media", "dvd", "blu", "record", "instrument"},
    "Tools | Hardware": {"tool", "hardware", "building", "construction", "plumbing", "electrical", "fastener", "industrial", "safety"},
    "Arts | Crafts": {"art", "craft", "sewing", "fabric", "yarn", "paint", "drawing", "scrapbook", "needlework"},
}
STOPWORDS = {"and", "the", "for", "of", "to", "with", "in", "a", "an", "by", "from", "other"}


def singular(word):
    """Small conservative normalizer; avoids external NLP model requirements."""
    if len(word) <= 3 or word in {"glass", "class", "dress", "press", "news", "series", "access"}:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ves") and len(word) > 4:
        return word[:-3] + "f"
    if word.endswith("ses") and not word.endswith("sses"):
        return word[:-2]  # cases -> case
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("&", " and ").replace("|", " ")
    value = re.sub(r"[/'’`_-]", " ", value)
    words = re.findall(r"[a-z0-9]+", value)
    return [singular(w) for w in words if w not in STOPWORDS]


def label(words):
    """Produce a concise normalized display label of no more than five words."""
    out = []
    for word in words:
        if word and word not in out:
            out.append(word)
        if len(out) == 5:
            break
    if not out:
        out = ["Catalog"]
    return " | ".join(w.upper() if w in {"gps", "rv", "dvd"} else w.title() for w in out)


def split_path(value):
    text = str(value).strip()
    # Source task specifies >. Alternate forms are accepted only when > is absent.
    if ">" in text:
        bits = text.split(">")
    elif "»" in text:
        bits = text.split("»")
    elif " / " in text:
        bits = text.split(" / ")
    else:
        bits = [text]
    return tuple(tuple(tokens(bit)) for bit in bits if tokens(bit))


def read_csv_rows(path):
    raw = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as fh:
                raw = fh.read()
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise ValueError(f"cannot decode {path}")
    try:
        dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError(f"{path} has no header")
    headers = [h.strip() for h in reader.fieldnames if h]
    normalized = {re.sub(r"[^a-z0-9]", "", h.lower()): h for h in headers}
    wanted = ("categorypath", "category", "path", "categoryname", "name")
    chosen = next((normalized[x] for x in wanted if x in normalized), None)
    if chosen is None:
        chosen = next((h for h in headers if "path" in h.lower() or "categor" in h.lower()), None)
    if chosen is None:
        raise ValueError(f"cannot find category path column in {path}; headers={headers}")
    return chosen, list(reader)


def remove_prefixes(records):
    """Return all original records whose normalized path is source-local leaf."""
    by_source = defaultdict(lambda: defaultdict(list))
    for rec in records:
        by_source[rec["source"]][rec["parts"]].append(rec)
    kept = []
    for source, path_rows in by_source.items():
        strict_prefixes = set()
        for path in path_rows:
            for n in range(1, len(path)):
                strict_prefixes.add(path[:n])
        for path, originals in path_rows.items():
            if path not in strict_prefixes:
                kept.extend(originals)
    return kept


def best_domain(parts):
    all_words = [w for part in parts for w in part]
    first = list(parts[0]) if parts else []
    scores = {}
    for domain, cue in DOMAIN_CUES.items():
        score = sum(3 for w in first if w in cue) + sum(1 for w in all_words if w in cue)
        if score:
            scores[domain] = score
    return max(scores, key=scores.get) if scores else None


class Node:
    def __init__(self, raw=(), root_label=None):
        self.raw = tuple(raw)[:5]
        self.root_label = root_label
        self.children = {}
        self.records = []
        self.display = root_label or label(self.raw)

    def add_child(self, raw):
        raw = tuple(raw)[:5] or ("catalog",)
        if raw not in self.children:
            self.children[raw] = Node(raw)
        return self.children[raw]


def node_weight(node):
    return len(node.records) + sum(node_weight(c) for c in node.children.values())


def collect_records(node):
    out = list(node.records)
    for child in node.children.values():
        out.extend(collect_records(child))
    return out


def group_tokens(nodes, parent_words):
    freq = Counter(w for n in nodes for w in n.raw if w not in parent_words)
    candidates = [w for w, _ in freq.most_common()]
    return tuple(candidates[:3] or ["catalog"])


def merge_to_limit(node, limit=20):
    """At the final permitted depth, merge rare branches without losing records."""
    ordered = sorted(node.children.values(), key=lambda n: (-node_weight(n), n.raw))
    if len(ordered) <= limit:
        return
    retained = ordered[:limit - 1]
    merged = ordered[limit - 1:]
    result = {n.raw: n for n in retained}
    summary = Node(group_tokens(merged, set(node.raw)))
    summary.records = [r for item in merged for r in collect_records(item)]
    key = summary.raw
    suffix = 2
    while key in result:
        key = summary.raw + ("selection", str(suffix))
        suffix += 1
    summary.raw = key[:5]
    result[summary.raw] = summary
    node.children = result


def cap_and_compact(node, depth):
    """Keep non-leaf breadth manageable and eliminate redundant short branches."""
    for child in list(node.children.values()):
        cap_and_compact(child, depth + 1)

    # Prefix rows were removed, so an internal node normally contains no records.
    # Collapsing one/two-child nodes makes sparse source encodings less needlessly deep.
    changed = True
    while changed:
        changed = False
        replacement = {}
        for key, child in node.children.items():
            if not child.records and 0 < len(child.children) < 3:
                for grand_key, grand in child.children.items():
                    candidate = grand_key
                    index = 2
                    while candidate in replacement:
                        candidate = grand_key + ("line", str(index))
                        index += 1
                    replacement[candidate] = grand
                changed = True
            else:
                replacement[key] = child
        node.children = replacement

    if len(node.children) <= 20:
        return
    # A wrapper would produce a sixth level when its children already occupy level 5.
    if depth >= 4:
        merge_to_limit(node)
        return

    buckets = defaultdict(list)
    for child in node.children.values():
        head = next((w for w in child.raw if w not in set(node.raw)), "catalog")
        buckets[head].append(child)
    ordered = sorted(buckets.items(), key=lambda kv: (-sum(node_weight(x) for x in kv[1]), kv[0]))
    result = {}
    if len(ordered) <= 20:
        selected = ordered
        overflow = []
    else:
        selected = ordered[:19]
        overflow = [child for _, children in ordered[19:] for child in children]
    for head, children in selected:
        if len(children) == 1:
            child = children[0]
            result[child.raw] = child
        else:
            wrapper = Node((head,))
            wrapper.children = {c.raw: c for c in children}
            result[wrapper.raw] = wrapper
    if overflow:
        wrapper = Node(group_tokens(overflow, set(node.raw)))
        wrapper.children = {c.raw: c for c in overflow}
        key = wrapper.raw
        count = 2
        while key in result:
            key = wrapper.raw + ("selection", str(count))
            count += 1
        wrapper.raw = key[:5]
        result[wrapper.raw] = wrapper
    node.children = result
    for child in list(node.children.values()):
        cap_and_compact(child, depth + 1)


def assign_display(node, ancestor_words=()):
    """Make names independent from parent words and reduce sibling token overlap."""
    parent_words = set(ancestor_words) | set(tokens(node.display))
    children = list(node.children.values())
    proposed = {}
    for child in children:
        base = [w for w in child.raw if w not in parent_words]
        proposed[child] = base or list(child.raw) or ["catalog"]
    occurrences = Counter(w for value in proposed.values() for w in set(value))
    for child, value in list(proposed.items()):
        trimmed = [w for w in value if occurrences[w] == 1]
        if trimmed:
            proposed[child] = trimmed
    used = set()
    for child in sorted(children, key=lambda c: c.raw):
        value = proposed[child][:5]
        rendered = label(value)
        # Labels must be distinguishable even after inherited-word removal.
        if rendered in used:
            for extra in list(child.raw) + ["selection", "range", "line"]:
                if extra not in value and extra not in parent_words:
                    value = (value + [extra])[:5]
                    rendered = label(value)
                    if rendered not in used:
                        break
        used.add(rendered)
        child.display = rendered
        assign_display(child, tuple(parent_words | set(tokens(rendered))))


def emit_rows(node, path, output):
    now = path
    if node.root_label:
        now = [node.display]
    elif node.display:
        now = path + [node.display]
    now = now[:5]
    for record in node.records:
        levels = now + [""] * (5 - len(now))
        output.append({
            "source": record["source"],
            "category_path": record["category_path"],
            "depth": len(now),
            **dict(zip(LEVEL_COLUMNS, levels)),
        })
    for child in node.children.values():
        emit_rows(child, now, output)


def build(config):
    data_dir = config.get("data_dir", "/root/data")
    output_dir = config.get("output_dir", "/root/output")
    file_map = dict(DEFAULT_FILES)
    file_map.update(config.get("files", {}))
    records, schemas = [], {}
    for source, default_name in DEFAULT_FILES.items():
        path = file_map.get(source, default_name)
        if not os.path.isabs(path):
            path = os.path.join(data_dir, path)
        if not os.path.isfile(path):
            raise ValueError(f"missing requested {source} CSV: {path}")
        column, rows = read_csv_rows(path)
        schemas[source] = {"file": path, "category_path_column": column, "input_rows": len(rows)}
        for row in rows:
            original = (row.get(column) or "").strip()
            parts = split_path(original)
            if parts:
                records.append({"source": source, "category_path": original, "parts": parts})
    records = remove_prefixes(records)
    if not records:
        raise ValueError("no nonempty leaf category paths were found")

    domains = [best_domain(r["parts"]) for r in records]
    active_known = {d for d in domains if d}
    unknown_counter = Counter(label(r["parts"][0]) for r, d in zip(records, domains) if not d)
    room = max(0, 20 - len(active_known))
    accepted_unknown = {name for name, _ in unknown_counter.most_common(room)}
    roots = {}
    for record, domain in zip(records, domains):
        if domain:
            root_name = domain
        else:
            candidate = label(record["parts"][0])
            root_name = candidate if candidate in accepted_unknown else "Specialty | Products"
        if root_name not in roots:
            roots[root_name] = Node(tokens(root_name), root_label=root_name)
        root = roots[root_name]
        route = []
        root_words = set(tokens(root_name))
        for part in record["parts"]:
            remaining = [w for w in part if w not in root_words]
            # Skip a source level that merely repeats the selected broad root.
            if not remaining and set(part) & root_words:
                continue
            part = tuple(remaining or part)
            if route and tuple(route[-1]) == part:
                continue
            route.append(part)
        if not route:
            root.records.append(record)
            continue
        if len(route) > 4:
            tail = []
            for part in route[3:]:
                tail.extend(part)
            route = route[:3] + [tuple(dict.fromkeys(tail))[:5]]
        current = root
        for part in route:
            current = current.add_child(part)
        current.records.append(record)

    container = Node(())
    container.children = {tuple(tokens(k)): v for k, v in roots.items()}
    cap_and_compact(container, 0)
    # Root nodes retain their broad domain names; all descendants are generated.
    for root in container.children.values():
        root.display = root.root_label or label(root.raw)
        assign_display(root, tuple(tokens(root.display)))

    full_rows = []
    for root in container.children.values():
        emit_rows(root, [], full_rows)
    full_rows.sort(key=lambda r: (r["source"], r["category_path"], tuple(r[c] for c in LEVEL_COLUMNS)))
    seen, hierarchy = set(), []
    for row in full_rows:
        key = tuple(row[c] for c in LEVEL_COLUMNS)
        if key not in seen:
            seen.add(key)
            hierarchy.append(dict(zip(LEVEL_COLUMNS, key)))
    hierarchy.sort(key=lambda r: tuple(r[c] for c in LEVEL_COLUMNS))

    os.makedirs(output_dir, exist_ok=True)
    full_path = os.path.join(output_dir, "unified_taxonomy_full.csv")
    hierarchy_path = os.path.join(output_dir, "unified_taxonomy_hierarchy.csv")
    for path, columns, rows in ((full_path, FULL_COLUMNS, full_rows), (hierarchy_path, LEVEL_COLUMNS, hierarchy)):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    return {
        "full_csv": full_path,
        "hierarchy_csv": hierarchy_path,
        "input_leaf_records": len(records),
        "full_mapping_rows": len(full_rows),
        "hierarchy_rows": len(hierarchy),
        "root_count": len(container.children),
        "input_schemas": schemas,
        "notes": ["Prefix paths are omitted source-locally; hierarchy is the exact deduplicated projection of full mapping."]
    }


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin must be a JSON object")
        print(json.dumps(build(config), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)

if __name__ == "__main__":
    main()
