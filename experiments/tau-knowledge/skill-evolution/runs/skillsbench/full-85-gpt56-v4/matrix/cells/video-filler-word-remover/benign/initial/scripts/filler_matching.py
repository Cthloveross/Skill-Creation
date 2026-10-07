#!/usr/bin/env python3
"""Pure matching and interval utilities for word-timestamp filler detection."""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

DEFAULT_FILLERS = [
    "um", "uh", "hum", "hmm", "mhm", "like", "you know", "i mean",
    "yeah", "so", "kind of", "basically", "i guess", "well", "okay",
]
_WORD_EDGE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize_token(value: Any) -> str:
    """Case-fold an ASR token and remove attached punctuation for lexical matching."""
    text = str(value).casefold().strip()
    text = _WORD_EDGE.sub("", text)
    return _SPACE.sub(" ", text).strip()


def normalized_phrase(value: Any) -> tuple[str, ...]:
    text = _SPACE.sub(" ", str(value).casefold().strip())
    return tuple(part for part in (normalize_token(x) for x in text.split(" ")) if part)


def coerce_words(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize externally supplied or backend word timing evidence."""
    result: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"word item {index} is not an object")
        raw = item.get("word", item.get("token"))
        if raw is None:
            raise ValueError(f"word item {index} lacks word/token")
        try:
            start, end = float(item["start"]), float(item["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"word item {index} lacks finite start/end timing") from exc
        if not (math.isfinite(start) and math.isfinite(end) and start >= 0 and end > start):
            raise ValueError(f"word item {index} has invalid timing")
        token = normalize_token(raw)
        if token:
            result.append({"raw": str(raw), "token": token, "start": start, "end": end})
    result.sort(key=lambda w: (w["start"], w["end"]))
    return result


def find_fillers(
    words: list[dict[str, Any]], fillers: Iterable[str] = DEFAULT_FILLERS,
    max_phrase_gap_seconds: float = 1.5,
) -> list[dict[str, Any]]:
    """Return non-overlapping longest phrase matches in chronological order."""
    if max_phrase_gap_seconds < 0:
        raise ValueError("max_phrase_gap_seconds must be nonnegative")
    phrases: list[tuple[str, tuple[str, ...]]] = []
    for filler in fillers:
        display = _SPACE.sub(" ", str(filler).casefold().strip())
        tokens = normalized_phrase(display)
        if tokens:
            phrases.append((display, tokens))
    if not phrases:
        raise ValueError("fillers must contain at least one nonempty phrase")
    # Longest first makes the overlap policy explicit and deterministic.
    phrases.sort(key=lambda pair: (-len(pair[1]), pair[0]))

    matches: list[dict[str, Any]] = []
    i = 0
    while i < len(words):
        chosen: tuple[str, tuple[str, ...]] | None = None
        for display, phrase in phrases:
            end_index = i + len(phrase)
            if end_index > len(words):
                continue
            candidate = words[i:end_index]
            if tuple(w["token"] for w in candidate) != phrase:
                continue
            if any(candidate[j + 1]["start"] - candidate[j]["end"] > max_phrase_gap_seconds
                   for j in range(len(candidate) - 1)):
                continue
            chosen = (display, phrase)
            break
        if chosen is None:
            i += 1
            continue
        length = len(chosen[1])
        span = words[i:i + length]
        matches.append({"word": chosen[0], "timestamp": span[0]["start"],
                        "start": span[0]["start"], "end": span[-1]["end"]})
        i += length
    return matches


def padded_merged_intervals(matches: Iterable[dict[str, Any]], duration: float, padding: float) -> list[tuple[float, float]]:
    """Clamp padded detection spans and merge overlapping/touching intervals."""
    if not (math.isfinite(duration) and duration > 0):
        raise ValueError("source duration must be finite and positive")
    if not (math.isfinite(padding) and padding >= 0):
        raise ValueError("clip padding must be a finite nonnegative number")
    raw: list[tuple[float, float]] = []
    for match in matches:
        start = max(0.0, float(match["start"]) - padding)
        end = min(duration, float(match["end"]) + padding)
        if end > start:
            raw.append((start, end))
    raw.sort()
    merged: list[list[float]] = []
    for start, end in raw:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(pair[0], pair[1]) for pair in merged]
