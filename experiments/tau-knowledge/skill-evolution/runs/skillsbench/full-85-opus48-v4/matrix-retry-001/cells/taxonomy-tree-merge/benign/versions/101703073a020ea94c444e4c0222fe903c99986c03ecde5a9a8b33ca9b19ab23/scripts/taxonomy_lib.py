"""Reusable helpers for merging hierarchical product taxonomies.

All functions are task-independent: they read whatever source CSVs and
constraints are supplied at runtime. No instance-specific category names,
counts, or answers are embedded here.
"""
import os
import re
import math
from collections import Counter

import numpy as np

STOP = {
    "and", "or", "the", "a", "an", "of", "for", "with", "in", "to", "on",
    "other", "others", "misc", "miscellaneous", "general", "etc", "more",
    "all", "by", "as", "at", "from", "item", "items", "category", "categories",
    "product", "products", "type", "types", "accessory", "accessories",
}

LARGE = 6000  # above this cluster count fall back to KMeans

_WORD_RE = re.compile(r"[^a-z0-9]+")


class Lemmatizer:
    def __init__(self):
        self._cache = {}
        self._wn = None
        try:
            import nltk
            from nltk.stem import WordNetLemmatizer
            for pkg in ("wordnet", "omw-1.4"):
                try:
                    nltk.download(pkg, quiet=True)
                except Exception:
                    pass
            self._wn = WordNetLemmatizer()
            # smoke test
            self._wn.lemmatize("tests")
        except Exception:
            self._wn = None

    @staticmethod
    def _simple(w):
        if len(w) > 4 and w.endswith("ies"):
            return w[:-3] + "y"
        if len(w) > 4 and w.endswith("ses"):
            return w[:-2]
        if len(w) > 4 and w.endswith("es") and w[-3] in "sxz":
            return w[:-2]
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
        return w

    def __call__(self, w):
        if w in self._cache:
            return self._cache[w]
        out = w
        if self._wn is not None:
            try:
                out = self._wn.lemmatize(w, "n")
            except Exception:
                out = self._simple(w)
        else:
            out = self._simple(w)
        self._cache[w] = out
        return out


def normalize_segment(seg, lemmatizer):
    s = _WORD_RE.sub(" ", seg.lower()).strip()
    words = [lemmatizer(w) for w in s.split() if w]
    return " ".join(words)


def split_path(path):
    return [p.strip() for p in str(path).split(">") if p and p.strip()]


def _detect_path_column(df):
    for c in df.columns:
        if str(c).strip().lower() == "category_path":
            return c
    best, best_score = None, -1
    for c in df.columns:
        try:
            score = df[c].astype(str).str.contains(">").mean()
        except Exception:
            score = 0
        if score > best_score:
            best, best_score = c, score
    return best


def _source_label(label):
    l = label.lower()
    if "amazon" in l:
        return "amazon"
    if "fb" in l or "facebook" in l or "meta" in l:
        return "facebook"
    if "google" in l:
        return "google"
    return label


def load_sources(data_dir, files, lemmatizer):
    """files: {label: filename}. Returns (items, warnings).

    Each item: dict(source, category_path, segments(normalized list),
    norm_string, depth).
    """
    import pandas as pd
    items = []
    warnings = []
    for label, fname in files.items():
        path = os.path.join(data_dir, fname)
        if not os.path.exists(path):
            warnings.append(f"missing file: {path}")
            continue
        try:
            df = pd.read_csv(path)
        except Exception as e:
            warnings.append(f"read failed {path}: {e}")
            continue
        col = _detect_path_column(df)
        if col is None:
            warnings.append(f"no path column in {path}")
            continue
        src = _source_label(label)
        raw_items = []
        for raw in df[col].dropna().astype(str):
            segs = split_path(raw)
            if not segs:
                continue
            norm = [normalize_segment(s, lemmatizer) for s in segs]
            norm = [n for n in norm if n]
            if not norm:
                continue
            raw_items.append((raw, norm))
        kept = remove_prefix_paths(raw_items)
        for raw, norm in kept:
            items.append({
                "source": src,
                "category_path": raw,
                "segments": norm,
                "norm_string": " ".join(norm),
                "depth": len(split_path(raw)),
            })
    return items, warnings


def remove_prefix_paths(raw_items):
    """Drop paths whose normalized segment tuple is a proper prefix of another."""
    tuples = [tuple(n) for _, n in raw_items]
    tupset = set(tuples)
    # index by prefix for speed
    by_prefix = {}
    for t in tupset:
        for k in range(1, len(t)):
            by_prefix.setdefault(t[:k], True)
    kept = []
    for (raw, norm), t in zip(raw_items, tuples):
        if t in by_prefix:  # some longer path starts with t
            continue
        kept.append((raw, norm))
    return kept


def get_embeddings(texts, method="auto"):
    if method in ("auto", "st"):
        try:
            from sentence_transformers import SentenceTransformer
            m = SentenceTransformer("all-MiniLM-L6-v2")
            emb = m.encode(list(texts), normalize_embeddings=True,
                           batch_size=256, show_progress_bar=False)
            return np.asarray(emb, dtype=np.float32)
        except Exception:
            if method == "st":
                raise
    return _tfidf_embeddings(texts)


def _tfidf_embeddings(texts):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize
    texts = list(texts)
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    X = vec.fit_transform(texts)
    n_feat = X.shape[1]
    dims = min(128, max(2, min(n_feat - 1, X.shape[0] - 1)))
    if dims < 2:
        arr = X.toarray().astype(np.float32)
        return normalize(arr).astype(np.float32)
    svd = TruncatedSVD(n_components=dims, random_state=0)
    emb = svd.fit_transform(X)
    return normalize(emb).astype(np.float32)


def _agg(k):
    from sklearn.cluster import AgglomerativeClustering
    try:
        return AgglomerativeClustering(n_clusters=k, metric="cosine",
                                       linkage="average")
    except TypeError:
        return AgglomerativeClustering(n_clusters=k, affinity="cosine",
                                       linkage="average")


def cluster(sub_emb, k):
    n = len(sub_emb)
    if k <= 1:
        return [0] * n
    if k >= n:
        return list(range(n))
    if n > LARGE:
        from sklearn.cluster import MiniBatchKMeans
        km = MiniBatchKMeans(n_clusters=k, random_state=0, n_init=3)
        return km.fit_predict(sub_emb)
    try:
        return _agg(k).fit_predict(sub_emb)
    except Exception:
        from sklearn.cluster import KMeans
        return KMeans(n_clusters=k, random_state=0, n_init=4).fit_predict(sub_emb)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def choose_k(n, depth):
    if depth == 1:
        k = _clamp(int(round(math.sqrt(n / 3.0))), 10, 20)
    else:
        k = _clamp(int(round(math.sqrt(n))), 3, 20)
    return min(k, n)


def generate_sibling_names(groups_tokens, ancestor_tokens, target_cov=0.70,
                           max_words=5):
    """groups_tokens: list of (list of member token-sets). Returns list of
    (name_string, picked_tokens, coverage)."""
    dfs = []
    sizes = []
    freq_tokens = []  # tokens frequent (>=0.3) in each group
    for members in groups_tokens:
        size = max(1, len(members))
        df = Counter()
        for m in members:
            for t in set(m):
                df[t] += 1
        dfs.append(df)
        sizes.append(size)
        freq_tokens.append({t for t, c in df.items() if c / size >= 0.3})
    sibling_count = Counter()
    for fs in freq_tokens:
        for t in fs:
            sibling_count[t] += 1

    results = []
    used = set()
    for gi, members in enumerate(groups_tokens):
        df = dfs[gi]
        size = sizes[gi]
        cand = [t for t in df
                if t and t not in STOP and t not in ancestor_tokens]

        def score(t):
            return (df[t] / size) / (sibling_count.get(t, 1))

        cand.sort(key=lambda t: (-score(t), -df[t], t))
        picked = []
        covered = set()
        for t in cand:
            if len(picked) >= max_words:
                break
            members_with = {idx for idx, m in enumerate(members) if t in m}
            new = covered | members_with
            if len(new) > len(covered) or not picked:
                picked.append(t)
                covered = new
            if len(covered) / size >= target_cov and picked:
                break
        if not picked:
            # fallback: most common non-stop token even if ancestor-shared
            fallback = [t for t in df if t and t not in STOP]
            fallback.sort(key=lambda t: (-df[t], t))
            if fallback:
                picked = [fallback[0]]
            else:
                picked = [f"group{gi}"]
            covered = {idx for idx, m in enumerate(members) if picked[0] in m}
        name = " | ".join(picked)
        while name in used:
            extra = [t for t in cand if t not in picked]
            if extra and len(picked) < max_words:
                picked.append(extra[0])
                name = " | ".join(picked)
            else:
                picked = picked + [f"g{gi}"]
                name = " | ".join(picked)
                break
        used.add(name)
        cov = len(covered) / size
        results.append((name, picked, cov))
    return results


def recurse(indices, depth, ancestor_tokens, emb, item_tokens, coverage_log,
            min_split=6):
    """Assign a list of level-names to each index. Returns {index: [names...]}"""
    result = {}
    n = len(indices)
    if n == 0:
        return result
    if depth != 1 and (n < min_split):
        for i in indices:
            result[i] = []
        return result
    k = choose_k(n, depth)
    if depth != 1 and k < 3:
        for i in indices:
            result[i] = []
        return result
    if depth == 1 and k < 1:
        k = min(1, n)
    sub = emb[np.asarray(indices)]
    labels = cluster(sub, k)
    groups = {}
    for idx, lab in zip(indices, labels):
        groups.setdefault(lab, []).append(idx)
    group_list = list(groups.values())
    groups_tokens = [[item_tokens[i] for i in g] for g in group_list]
    names = generate_sibling_names(groups_tokens, ancestor_tokens)
    for g, (name, picked, cov) in zip(group_list, names):
        coverage_log.append((depth, name, len(g), cov))
        if depth < 5 and len(g) >= min_split:
            child = recurse(g, depth + 1,
                            ancestor_tokens | set(picked),
                            emb, item_tokens, coverage_log, min_split)
        else:
            child = {i: [] for i in g}
        for i in g:
            result[i] = [name] + child.get(i, [])
    return result


def pad5(names):
    out = list(names[:5])
    while len(out) < 5:
        out.append("")
    return out


def word_set(name):
    return set(w for w in name.split(" | ") if w)


def validate(full_rows, hier_rows):
    """full_rows: list of dict with unified_level_1..5. hier_rows: list of 5-tuples.
    Returns a warnings dict (diagnostic only)."""
    rep = {}
    level1 = {r["unified_level_1"] for r in full_rows if r["unified_level_1"]}
    rep["n_level1"] = len(level1)
    rep["level1_in_range"] = 10 <= len(level1) <= 20

    # child counts per parent per level
    children = {}
    for t in hier_rows:
        for lvl in range(1, 5):
            parent = tuple(t[:lvl])
            child = t[lvl]
            if all(parent) and child:
                children.setdefault((lvl, parent), set()).add(child)
    violations = 0
    for _, cs in children.items():
        if not (3 <= len(cs) <= 20):
            violations += 1
    rep["child_count_violations"] = violations
    rep["n_parents"] = len(children)

    # name word counts and parent-child overlap
    over5 = 0
    pc_overlap = 0
    for t in hier_rows:
        prev_words = set()
        for lvl in range(5):
            name = t[lvl]
            if not name:
                continue
            ws = word_set(name)
            if len(ws) > 5:
                over5 += 1
            if prev_words & ws:
                pc_overlap += 1
            prev_words = prev_words | ws
    rep["names_over_5_words"] = over5
    rep["parent_child_overlap"] = pc_overlap

    # sibling overlap pairs >=0.3 jaccard
    sib_pairs = 0
    sib_total = 0
    for (lvl, parent), cs in children.items():
        cl = sorted(cs)
        for i in range(len(cl)):
            for j in range(i + 1, len(cl)):
                a, b = word_set(cl[i]), word_set(cl[j])
                if not a or not b:
                    continue
                jac = len(a & b) / len(a | b)
                sib_total += 1
                if jac >= 0.30:
                    sib_pairs += 1
    rep["sibling_overlap_pairs"] = sib_pairs
    rep["sibling_pairs_total"] = sib_total

    # structural integrity: every node's ancestors present
    hset = set(hier_rows)
    broken = 0
    for t in hier_rows:
        for lvl in range(1, 5):
            if t[lvl] and not t[lvl - 1]:
                broken += 1
    rep["structural_breaks"] = broken
    return rep
