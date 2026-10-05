"""Pure helpers for word-timed filler detection."""
from __future__ import annotations

import math
import unicodedata
from typing import Any

# Longest forms are considered first at each token. This prevents an overlapping
# partial detection if a vocabulary is later extended with component words.
FILLER_PHRASES: tuple[tuple[str, ...], ...] = (
    ("you", "know"),
    ("i", "mean"),
    ("kind", "of"),
    ("i", "guess"),
    ("um",),
    ("uh",),
    ("hum",),
    ("hmm",),
    ("mhm",),
    ("like",),
    ("yeah",),
    ("so",),
    ("basically",),
    ("well",),
    ("okay",),
)


def normalize_for_match(value: str) -> str:
    """Case-fold and remove only punctuation/symbols attached to token edges."""
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    left = 0
    right = len(text)
    while left < right and _is_edge_punctuation(text[left]):
        left += 1
    while right > left and _is_edge_punctuation(text[right - 1]):
        right -= 1
    return text[left:right]


def _is_edge_punctuation(char: str) -> bool:
    category = unicodedata.category(char)
    return category.startswith("P") or category.startswith("S") or char.isspace()


def coerce_words(raw_words: Any) -> list[dict[str, Any]]:
    """Validate and normalize a list of independently timed ASR words."""
    if not isinstance(raw_words, list):
        raise ValueError("word transcript must be a JSON array")
    words: list[dict[str, Any]] = []
    previous_start = -math.inf
    for index, raw in enumerate(raw_words):
        if not isinstance(raw, dict):
            raise ValueError(f"word {index} is not an object")
        token = raw.get("word", raw.get("text", raw.get("token")))
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"word {index} lacks a nonempty word/text/token string")
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"word {index} needs numeric start and end") from exc
        if not (math.isfinite(start) and math.isfinite(end) and start >= 0 and end > start):
            raise ValueError(f"word {index} has invalid interval [{start}, {end}]")
        if start < previous_start:
            raise ValueError("word-level transcript is not in nondecreasing time order")
        normalized = normalize_for_match(token)
        words.append({"raw": token, "normalized": normalized, "start": start, "end": end})
        previous_start = start
    return words


def detect_fillers(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return non-overlapping lexical filler matches in transcript order."""
    matches: list[dict[str, Any]] = []
    index = 0
    while index < len(words):
        selected: tuple[str, ...] | None = None
        for phrase in FILLER_PHRASES:
            if index + len(phrase) > len(words):
                continue
            observed = tuple(words[index + offset]["normalized"] for offset in range(len(phrase)))
            if observed == phrase:
                selected = phrase
                break
        if selected is None:
            index += 1
            continue
        last = index + len(selected) - 1
        matches.append(
            {
                "word": " ".join(selected),
                "timestamp": words[index]["start"],
                "start": words[index]["start"],
                "end": words[last]["end"],
                "source_tokens": [words[pos]["raw"] for pos in range(index, last + 1)],
            }
        )
        index = last + 1
    return matches
