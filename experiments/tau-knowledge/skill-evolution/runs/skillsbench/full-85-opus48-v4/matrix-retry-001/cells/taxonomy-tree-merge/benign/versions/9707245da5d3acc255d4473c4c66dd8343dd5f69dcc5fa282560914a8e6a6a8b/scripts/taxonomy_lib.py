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
    # drop single-character tokens (e.g. the stray "s" from "women's")
    words = [w for w in words if len(w) > 1]
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
                           max_words=5, drop_common=True):
    """groups_tokens: list of member token-sets per sibling group. Returns a
    list of (name_string_or_None, picked_tokens, coverage). A None name marks a
    group that cannot be given a representative, parent-distinct, unique label;
    the caller merges such members back up instead of creating a bogus level.

    Guarantees for every non-None name:
      * tokens come from the group's own member words (coverage > 0),
      * never reuse an ancestor token (parent/child independence),
      * no single-character / stopword tokens, at most ``max_words`` words,
      * greedy set-cover maximizes member coverage toward ``target_cov``,
      * a differentiation pass keeps sibling word overlap (Jaccard) < 0.30.
    """
    G = len(groups_tokens)
    invs = []    # token -> set(member index) per group
    sizes = []
    dfs = []
    freq_tokens = []
    for members in groups_tokens:
        size = max(1, len(members))
        inv = {}
        for idx, m in enumerate(members):
            for t in set(m):
                inv.setdefault(t, set()).add(idx)
        df = Counter({t: len(s) for t, s in inv.items()})
        invs.append(inv)
        sizes.append(size)
        dfs.append(df)
        freq_tokens.append({t for t, c in df.items() if c / size >= 0.3})
    sibling_count = Counter()
    for fs in freq_tokens:
        for t in fs:
            sibling_count[t] += 1

    # Tokens that appear in a large share of sibling groups are not
    # distinctive (they behave like a local/parent theme word, e.g.
    # "sporting"/"good"/"recreation" under an outdoor node). Excluding them
    # from names keeps siblings distinct (rule: <30% word overlap) and names
    # concise. Only applied when there are enough siblings to judge.
    present_count = Counter()
    for df in dfs:
        for t in df:
            present_count[t] += 1
    common_tokens = set()
    if drop_common and G >= 5:
        thr = 0.6 * G
        common_tokens = {t for t, c in present_count.items() if c > thr}

    def valid_tok(t):
        return (bool(t) and len(t) > 1 and t not in STOP
                and t not in ancestor_tokens and t not in common_tokens)

    def coverage_of(gi, toks):
        inv = invs[gi]
        covered = set()
        for t in toks:
            covered |= inv.get(t, set())
        return len(covered) / sizes[gi]

    picks = []  # list[tokens] or None
    for gi in range(G):
        inv = invs[gi]
        size = sizes[gi]
        df = dfs[gi]
        cand = [t for t in df if valid_tok(t)]

        def score(t):
            return (df[t] / size) / (sibling_count.get(t, 1))

        picked = []
        covered = set()
        remaining = set(cand)
        while (len(picked) < max_words and remaining
               and len(covered) / size < target_cov):
            best = None
            best_gain = -1
            best_score = -1.0
            for t in remaining:
                gain = len(inv[t] - covered)
                sc = score(t)
                if gain > best_gain or (gain == best_gain and sc > best_score):
                    best, best_gain, best_score = t, gain, sc
            if best is None or best_gain <= 0:
                break
            picked.append(best)
            covered |= inv[best]
            remaining.discard(best)
        if not picked:
            # fallback: most frequent non-ancestor token (stopwords allowed as a
            # last resort, but never an ancestor token -> keeps parent/child
            # independence and avoids synthetic placeholders)
            fb = [t for t in df if t and len(t) > 1 and t not in ancestor_tokens
                  and t not in common_tokens]
            fb.sort(key=lambda t: (-df[t], t))
            if fb:
                picked = [fb[0]]
            else:
                picks.append(None)
                continue
        picks.append(picked)

    # --- sibling differentiation: drive pairwise Jaccard word overlap < 0.30 ---
    def jac(a, b):
        a, b = set(a), set(b)
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    changed = True
    rounds = 0
    while changed and rounds < 6:
        changed = False
        rounds += 1
        for i in range(G):
            if picks[i] is None:
                continue
            for j in range(G):
                if i == j or picks[j] is None:
                    continue
                if jac(picks[i], picks[j]) < 0.30:
                    continue
                if len(picks[i]) >= max_words:
                    continue
                cur = set(picks[i])
                other = set(picks[j])
                df = dfs[i]
                extra = [t for t in df if valid_tok(t) and t not in cur
                         and t not in other]
                extra.sort(key=lambda t: (-(df[t] / sizes[i]), t))
                if extra:
                    picks[i].append(extra[0])
                    changed = True

    # --- build unique, non-empty names ---
    used = set()
    results = []
    for gi in range(G):
        picked = picks[gi]
        if picked is None:
            results.append((None, [], 0.0))
            continue
        name = " | ".join(picked)
        if name in used:
            df = dfs[gi]
            extra = [t for t in df if valid_tok(t) and t not in picked]
            extra.sort(key=lambda t: (-df[t], t))
            for e in extra:
                if len(picked) >= max_words:
                    break
                picked = picked + [e]
                name = " | ".join(picked)
                if name not in used:
                    break
        if name in used:
            results.append((None, [], 0.0))
            continue
        used.add(name)
        results.append((name, picked, coverage_of(gi, picked)))
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
    names = generate_sibling_names(groups_tokens, ancestor_tokens,
                                   drop_common=(depth != 1))
    # A child "survives" only if it has a representative (>=COV_FLOOR coverage),
    # parent-distinct, unique name. Non-surviving children merge back up so we
    # never emit a non-representative label. Top level (depth 1) always keeps
    # its clusters so every source row receives a level-1 category.
    cov_floor = 0.70
    survive = []
    for g, (name, picked, cov) in zip(group_list, names):
        ok = name is not None and (depth == 1 or cov >= cov_floor)
        survive.append((g, name, picked, cov, ok))
    n_ok = sum(1 for s in survive if s[4])
    if depth != 1 and n_ok < 3:
        # cannot form >=3 representative children -> keep this node as a leaf
        for i in indices:
            result[i] = []
        return result
    for g, name, picked, cov, ok in survive:
        if not ok:
            # merge members back up (no new level for them)
            for i in g:
                result[i] = []
            continue
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
