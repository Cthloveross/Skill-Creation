#!/usr/bin/env python3
"""Create a normalized, bounded unified product taxonomy.

JSON stdin schema is documented in SKILL.md.  The program writes CSV artifacts and
prints a JSON validation summary to stdout.  It requires only Python's stdlib.
"""
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

LEVEL_COLUMNS = ["unified_level_%d" % i for i in range(1, 6)]
FULL_COLUMNS = ["source", "category_path", "depth"] + LEVEL_COLUMNS
PATH_CANDIDATES = (
    "category_path", "product_category", "google_product_category",
    "google_product_taxonomy", "path", "category", "taxonomy_path",
)
STOP_FOR_SHARED = {"and", "for", "with", "the", "a", "an", "of", "in"}

# Generic domain policy. Labels are broad, conventional commerce domains; lower
# hierarchy names are always generated from the supplied paths.
ANCHORS = OrderedDict([
    ("Apparel", {"apparel", "clothing", "fashion", "shoe", "footwear", "jewelry", "watch"}),
    ("Automotive", {"automotive", "vehicle", "car", "truck", "motorcycle", "motorcycle", "auto"}),
    ("Baby", {"baby", "infant", "toddler", "nursery"}),
    ("Beauty | Personal | Care", {"beauty", "cosmetic", "makeup", "skin", "hair", "personal", "fragrance"}),
    ("Books | Media", {"book", "media", "movie", "music", "video", "magazine", "record"}),
    ("Business | Industrial", {"business", "industrial", "commercial", "lab", "scientific", "material"}),
    ("Electronics", {"electronic", "computer", "camera", "audio", "phone", "tablet", "television", "network"}),
    ("Food | Beverage", {"food", "beverage", "grocery", "drink", "snack", "wine", "beer"}),
    ("Furniture | Home", {"furniture", "home", "kitchen", "bed", "bath", "garden", "decor", "appliance"}),
    ("Health", {"health", "medical", "wellness", "vitamin", "pharmacy", "drug"}),
    ("Hobby | Crafts", {"craft", "art", "sewing", "party", "collectible", "musical"}),
    ("Office | School", {"office", "school", "stationery", "paper", "printer", "supplies"}),
    ("Pet", {"pet", "dog", "cat", "animal", "aquarium", "bird"}),
    ("Sports | Outdoors", {"sport", "outdoor", "fitness", "exercise", "camping", "hunting", "cycling"}),
    ("Toys | Games", {"toy", "game", "puzzle", "play", "doll"}),
    ("Travel | Luggage", {"luggage", "travel", "bag", "suitcase", "backpack"}),
])


def singular(token):
    """Conservative token lemmatization without third-party NLP dependencies."""
    if len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith(("sses", "shes", "ches", "xes", "zes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokens(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[|/_\\-]+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return [singular(x) for x in value.split() if x]


def canonical(value):
    return " ".join(tokens(value))


def display(tok_list):
    """Produce a concise human-readable pipe-separated name from normalized terms."""
    seen, chosen = set(), []
    for token in tok_list:
        if token and token not in seen:
            chosen.append(token)
            seen.add(token)
        if len(chosen) == 5:
            break
    if not chosen:
        return "Product"
    special = {"tv": "TV", "dvd": "DVD", "pc": "PC", "usb": "USB"}
    return " | ".join(special.get(x, x.capitalize()) for x in chosen)


def split_path(raw):
    # The requested format uses >. A repeated > with arbitrary spacing is accepted.
    pieces = re.split(r"\s*>\s*", str(raw).strip())
    result = []
    for part in pieces:
        norm = canonical(part)
        if norm:
            result.append(norm)
    return result


def detect_path_column(fieldnames, rows):
    lowered = {str(x).strip().lower(): x for x in (fieldnames or []) if x is not None}
    for candidate in PATH_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    best, best_score = None, -1
    for field in fieldnames or []:
        score = sum(1 for row in rows[:100] if ">" in str(row.get(field, "")))
        if score > best_score:
            best, best_score = field, score
    return best if best_score > 0 else None


def read_source(source, path):
    """Read a CSV while tolerating heterogeneous headings and dialects."""
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(16384)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        rows = list(reader)
        column = detect_path_column(reader.fieldnames, rows)
        if not column:
            raise ValueError("No hierarchy path column found in %s; headers were %r" % (path, reader.fieldnames))
    records = []
    for row in rows:
        raw = str(row.get(column, "")).strip()
        parts = split_path(raw)
        if parts:
            records.append({"source": source, "category_path": raw, "parts": parts})
    return records, column


def retain_leaves(records):
    """Deduplicate and remove paths that are prefixes of a longer path per source."""
    unique = OrderedDict()
    for rec in records:
        key = (rec["source"], tuple(rec["parts"]))
        unique.setdefault(key, rec)
    extension_prefixes = set()
    for source, parts in unique:
        for end in range(1, len(parts)):
            extension_prefixes.add((source, parts[:end]))
    return [rec for key, rec in unique.items() if key not in extension_prefixes]


def root_for(parts):
    all_tokens = [word for part in parts for word in part.split()]
    first_tokens = set(parts[0].split()) if parts else set()
    best_name, best_score = None, 0
    for name, words in ANCHORS.items():
        score = sum(1 for word in all_tokens if word in words)
        score += 2 * sum(1 for word in first_tokens if word in words)
        if score > best_score:
            best_name, best_score = name, score
    if best_name:
        return best_name
    return display(parts[0].split()) if parts else "Product"


class Node:
    def __init__(self, raw, parent=None):
        self.raw = raw
        self.name = display(raw.split())
        self.parent = parent
        self.children = OrderedDict()
        self.records = []  # records terminal at this exact node

    def size(self):
        return len(self.records) + sum(child.size() for child in self.children.values())


def merge_nodes(destination, source):
    """Combine same-depth nodes without adding a hierarchy level."""
    destination.records.extend(source.records)
    for record in source.records:
        record["leaf"] = destination
    for key, child in source.children.items():
        if key in destination.children:
            merge_nodes(destination.children[key], child)
        else:
            destination.children[key] = child
            child.parent = destination


def representative_raw(nodes, parent):
    freq = Counter()
    parent_words = set(tokens(parent.name)) if parent else set()
    for node in nodes:
        weight = max(1, node.size())
        for word in tokens(node.raw):
            if word not in parent_words and word not in STOP_FOR_SHARED:
                freq[word] += weight
    words = [word for word, _ in freq.most_common(4)]
    if not words:
        # This fallback still uses an observed label rather than an opaque bucket id.
        words = tokens(nodes[0].raw)[:3] or ["product"]
    return " ".join(words)


def cap_children(node):
    """Keep at most 20 child nodes, merging rare nodes at the same depth."""
    for child in list(node.children.values()):
        cap_children(child)
    if len(node.children) <= 20:
        return
    ranked = sorted(node.children.items(), key=lambda item: (-item[1].size(), item[0]))
    keep, excess = ranked[:19], ranked[19:]
    replacement_raw = representative_raw([child for _, child in excess], node)
    # Avoid a direct raw-key collision deterministically.
    key = replacement_raw
    suffix = 2
    while key in dict(keep):
        key = replacement_raw + " group " + str(suffix)
        suffix += 1
    merged = Node(key, node)
    for _, child in excess:
        merge_nodes(merged, child)
    node.children = OrderedDict(keep + [(key, merged)])


def assign_names(node):
    """Name children while removing redundant parent and sibling terms where possible."""
    children = list(node.children.values())
    if children:
        parent_words = set(tokens(node.name))
        raw_word_counts = Counter()
        for child in children:
            raw_word_counts.update(set(tokens(child.raw)) - STOP_FOR_SHARED)
        proposed = []
        for child in children:
            words = tokens(child.raw)
            without_parent = [w for w in words if w not in parent_words]
            if without_parent:
                words = without_parent
            # Shared terms add little discriminative value among siblings. Keep them
            # only if dropping them would make the observed label empty.
            distinct = [w for w in words if raw_word_counts[w] < 2 or w in STOP_FOR_SHARED]
            if distinct:
                words = distinct
            proposed.append(words or tokens(child.raw) or ["product"])
        used = set()
        for child, words in zip(children, proposed):
            name = display(words)
            if name in used:
                # Restore observed terms progressively to avoid duplicate sibling labels.
                for word in tokens(child.raw):
                    candidate = display(words + [word])
                    if candidate not in used:
                        name = candidate
                        break
            used.add(name)
            child.name = name
        for child in children:
            assign_names(child)


def node_levels(leaf):
    result = []
    node = leaf
    while node is not None:
        result.append(node.name)
        node = node.parent
    result.reverse()
    return (result + [""] * 5)[:5]


def build(records):
    root_nodes = OrderedDict()
    root_counts = Counter(root_for(rec["parts"]) for rec in records)
    # Bound the root breadth without manufacturing individual source mappings.
    allowed = None
    overflow_root = None
    if len(root_counts) > 20:
        allowed = {name for name, _ in root_counts.most_common(19)}
        overflow_names = [name for name in root_counts if name not in allowed]
        overflow_root = display(tokens(" ".join(overflow_names))[:4])
        if overflow_root in allowed or not overflow_root:
            overflow_root = "General | Merchandise"
    for record in records:
        root_name = root_for(record["parts"])
        if allowed is not None and root_name not in allowed:
            root_name = overflow_root
        root = root_nodes.get(root_name)
        if root is None:
            root = Node(canonical(root_name))
            root.name = root_name
            root_nodes[root_name] = root
        # Remove an immediately redundant source component under the assigned root.
        root_words = set(tokens(root_name))
        residual = []
        for part in record["parts"]:
            part_words = set(part.split())
            if not residual and part_words and part_words.issubset(root_words):
                continue
            if residual and part == residual[-1]:
                continue
            residual.append(part)
        # Root plus at most four deeper nodes. If input is deeper, retain the most
        # specific terminal component in the final available level.
        if len(residual) > 4:
            residual = residual[:3] + [residual[-1]]
        node = root
        for part in residual:
            if part not in node.children:
                node.children[part] = Node(part, node)
            node = node.children[part]
        node.records.append(record)
        record["leaf"] = node
    virtual = Node("catalog")
    virtual.name = "Catalog"
    virtual.children = root_nodes
    for root in root_nodes.values():
        root.parent = None
        cap_children(root)
    # Root cap is handled before construction; name lower levels only.
    for root in root_nodes.values():
        assign_names(root)
    return root_nodes


def prefix_key(levels, depth):
    return tuple(levels[:depth])


def validate(full_rows, hierarchy_rows, roots):
    errors, warnings = [], []
    if not full_rows:
        errors.append("No usable category paths were read.")
        return errors, warnings, {}
    expected = {tuple(row[c] for c in LEVEL_COLUMNS) for row in full_rows}
    actual = {tuple(row[c] for c in LEVEL_COLUMNS) for row in hierarchy_rows}
    if expected != actual:
        errors.append("Hierarchy rows are not exactly the deduplicated unified-level projection of full rows.")
    for row in full_rows:
        levels = [row[c] for c in LEVEL_COLUMNS]
        depth = sum(bool(x) for x in levels)
        if depth != row["depth"] or depth < 1 or depth > 5:
            errors.append("Invalid depth or non-contiguous level values for path %r." % row["category_path"])
            break
        if any(not levels[i] and any(levels[i + 1:]) for i in range(5)):
            errors.append("A hierarchy row has a missing ancestor.")
            break
        for name in levels[:depth]:
            word_count = len(tokens(name))
            if not name or word_count > 5 or ">" in name or "Other" == name or "Misc" == name:
                errors.append("Invalid generated category name %r." % name)
                break
    root_names = sorted({row["unified_level_1"] for row in full_rows})
    if not 10 <= len(root_names) <= 20:
        warnings.append("Observed root count is %d, outside requested 10-20; sparse/source-specific inputs were not padded with fabricated roots." % len(root_names))
    children = defaultdict(set)
    source_counts = defaultdict(Counter)
    for row in full_rows:
        source_counts[row["unified_level_1"]][row["source"]] += 1
        levels = [row[c] for c in LEVEL_COLUMNS]
        for depth in range(1, 5):
            if levels[depth]:
                children[tuple(levels[:depth])].add(levels[depth])
    for parent, names in sorted(children.items()):
        count = len(names)
        if count > 20:
            errors.append("Parent %r has %d children (maximum is 20)." % (parent, count))
        elif count < 3:
            warnings.append("Parent %r has only %d observed children; it was not padded with artificial categories." % (parent, count))
        name_list = sorted(names)
        parent_words = set(tokens(parent[-1]))
        for name in name_list:
            overlap = parent_words & set(tokens(name))
            if overlap:
                warnings.append("Parent-child name overlap at %r -> %r: %s." % (parent, name, ", ".join(sorted(overlap))))
        for index, left in enumerate(name_list):
            left_words = set(tokens(left))
            for right in name_list[index + 1:]:
                right_words = set(tokens(right))
                union = left_words | right_words
                ratio = (len(left_words & right_words) / len(union)) if union else 0.0
                if ratio >= 0.30:
                    warnings.append("Sibling word overlap %.0f%% under %r: %r / %r." % (ratio * 100, parent, left, right))
    distributions = {}
    for root, counts in sorted(source_counts.items()):
        total = sum(counts.values())
        distributions[root] = {source: round(count / total, 6) for source, count in sorted(counts.items())}
        if len(counts) == 1:
            warnings.append("Top-level category %r is source-exclusive (%s); retained for semantic coherence." % (root, next(iter(counts))))
    return errors, warnings, distributions


def write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    try:
        config = json.load(sys.stdin)
        defaults = {
            "amazon": "/root/data/amazon_product_categories.csv",
            "facebook": "/root/data/fb_product_categories.csv",
            "google": "/root/data/google_shopping_product_categories.csv",
        }
        paths = dict(defaults)
        paths.update(config.get("input_files", {}))
        all_records, detected = [], {}
        for source in ("amazon", "facebook", "google"):
            records, column = read_source(source, paths[source])
            all_records.extend(records)
            detected[source] = column
        input_count = len(all_records)
        if config.get("keep_leaf_paths", True):
            all_records = retain_leaves(all_records)
        else:
            dedup = OrderedDict()
            for rec in all_records:
                dedup.setdefault((rec["source"], tuple(rec["parts"])), rec)
            all_records = list(dedup.values())
        roots = build(all_records)
        full_rows = []
        for rec in all_records:
            levels = node_levels(rec["leaf"])
            depth = sum(bool(x) for x in levels)
            row = {"source": rec["source"], "category_path": rec["category_path"], "depth": depth}
            row.update(dict(zip(LEVEL_COLUMNS, levels)))
            full_rows.append(row)
        full_rows.sort(key=lambda row: (row["source"], row["category_path"], tuple(row[c] for c in LEVEL_COLUMNS)))
        unique = OrderedDict()
        for row in full_rows:
            unique.setdefault(tuple(row[c] for c in LEVEL_COLUMNS), {c: row[c] for c in LEVEL_COLUMNS})
        hierarchy_rows = [unique[key] for key in sorted(unique)]
        errors, warnings, distributions = validate(full_rows, hierarchy_rows, roots)
        output_dir = Path(config.get("output_dir", "/root/output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        write_csv(output_dir / "unified_taxonomy_full.csv", FULL_COLUMNS, full_rows)
        write_csv(output_dir / "unified_taxonomy_hierarchy.csv", LEVEL_COLUMNS, hierarchy_rows)
        summary = {
            "ok": not errors,
            "input_rows": input_count,
            "mapped_leaf_rows": len(full_rows),
            "hierarchy_paths": len(hierarchy_rows),
            "top_level_categories": len({row["unified_level_1"] for row in full_rows}),
            "detected_path_columns": detected,
            "outputs": {
                "full": str(output_dir / "unified_taxonomy_full.csv"),
                "hierarchy": str(output_dir / "unified_taxonomy_hierarchy.csv"),
            },
            "source_proportions_by_top_level": distributions,
            "errors": errors,
            "warnings": warnings,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
