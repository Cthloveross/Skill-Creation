#!/usr/bin/env python3
"""Deterministic filler matching over word-level ASR tokens.

stdin: {"tokens": [{"text": str, "start": number, "end": number}, ...],
        "fillers": [str, ...] optional}
stdout: {"detections": [{"word": str, "timestamp": number, "end": number,
                         "token_start": int, "token_end": int}, ...]}
"""
import json
import math
import sys
import unicodedata

DEFAULT_FILLERS = [
    "um", "uh", "hum", "hmm", "mhm", "like", "you know", "i mean",
    "yeah", "so", "kind of", "basically", "i guess", "well", "okay",
]


def normalize(text):
    """Case-fold and discard punctuation without changing stored raw token text."""
    if not isinstance(text, str):
        raise ValueError("token text must be a string")
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold()
                   if ch.isalnum())


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(label + " must be finite")
    return value


def validate_tokens(tokens):
    if not isinstance(tokens, list):
        raise ValueError("tokens must be an array")
    clean = []
    prior_start = -1.0
    for index, token in enumerate(tokens):
        if not isinstance(token, dict):
            raise ValueError("token %d must be an object" % index)
        raw = token.get("text")
        start = _finite_number(token.get("start"), "token %d start" % index)
        end = _finite_number(token.get("end"), "token %d end" % index)
        if start < 0 or end <= start:
            raise ValueError("token %d needs nonnegative start and positive duration" % index)
        if start < prior_start:
            raise ValueError("tokens must be ordered by start time")
        prior_start = start
        clean.append({"raw": raw, "norm": normalize(raw), "start": start, "end": end})
    return clean


def phrase_patterns(fillers):
    if not isinstance(fillers, list) or not fillers or not all(isinstance(x, str) for x in fillers):
        raise ValueError("fillers must be a nonempty array of strings")
    patterns = []
    seen = set()
    for filler in fillers:
        parts = [normalize(part) for part in filler.split()]
        if not parts or any(not part for part in parts):
            raise ValueError("filler %r has no matchable words" % filler)
        key = tuple(parts)
        if key not in seen:
            # Canonical output uses the explicitly declared phrase, not ASR spelling/case.
            patterns.append((key, filler))
            seen.add(key)
    return patterns


def detect(tokens, fillers=None):
    clean = validate_tokens(tokens)
    patterns = phrase_patterns(DEFAULT_FILLERS if fillers is None else fillers)
    # At a common first word, longest phrase wins; original list order breaks exact ties.
    patterns.sort(key=lambda item: len(item[0]), reverse=True)
    detections = []
    i = 0
    while i < len(clean):
        selected = None
        for words, canonical in patterns:
            n = len(words)
            if i + n <= len(clean) and tuple(t["norm"] for t in clean[i:i + n]) == words:
                selected = (n, canonical)
                break
        if selected is None:
            i += 1
            continue
        n, canonical = selected
        detections.append({
            "word": canonical,
            "timestamp": clean[i]["start"],
            "end": clean[i + n - 1]["end"],
            "token_start": i,
            "token_end": i + n - 1,
        })
        # Explicit non-overlap policy: consumed phrase words cannot form another result.
        i += n
    return detections


def main():
    request = json.load(sys.stdin)
    if not isinstance(request, dict):
        raise ValueError("input must be a JSON object")
    result = detect(request.get("tokens"), request.get("fillers"))
    json.dump({"detections": result}, sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        raise SystemExit(2)
