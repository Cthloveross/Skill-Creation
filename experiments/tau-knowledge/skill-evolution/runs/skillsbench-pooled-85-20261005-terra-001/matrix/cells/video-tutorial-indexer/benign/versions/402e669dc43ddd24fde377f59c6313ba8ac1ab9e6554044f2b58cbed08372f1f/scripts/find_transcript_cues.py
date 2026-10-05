#!/usr/bin/env python3
"""Rank transcript locations that may merit manual chapter-boundary review.

JSON stdin:
{
 "transcript_path":"/path/whisper.json",
 "chapters":[{"title":"exact title","aliases":["optional phrase"]}],
 "per_chapter":8,
 "context":1
}
Outputs JSON candidates with segment start/end/text and surrounding context. This is a
lexical lead generator, not a semantic chapter decision engine.
"""
import json
import math
import re
import sys
from pathlib import Path

WORD = re.compile(r"[a-z0-9]+")
STOP = {"a", "an", "and", "as", "at", "by", "for", "from", "how", "if", "in", "into", "it", "of", "on", "or", "the", "to", "up", "we", "with", "will", "your"}


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    raise SystemExit(2)


def tokens(text):
    return [w for w in WORD.findall(text.lower()) if w not in STOP]


def clean_segment(raw, index):
    if not isinstance(raw, dict):
        raise ValueError(f"segment {index} is not an object")
    start, end, text = raw.get("start"), raw.get("end"), raw.get("text")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not isinstance(text, str):
        raise ValueError(f"segment {index} lacks numeric start/end or text")
    if not (math.isfinite(start) and math.isfinite(end)):
        raise ValueError(f"segment {index} has non-finite timestamps")
    return {"start": float(start), "end": float(end), "text": text}


def score(segment_text, phrases):
    lowered = segment_text.lower()
    segment_words = set(tokens(segment_text))
    best = 0.0
    for phrase in phrases:
        phrase_words = tokens(phrase)
        if not phrase_words:
            continue
        overlap = sum(w in segment_words for w in set(phrase_words)) / len(set(phrase_words))
        contiguous = 1.0 if phrase.lower() in lowered else 0.0
        # Phrase match is strong; token overlap remains useful for ASR punctuation/case variation.
        best = max(best, 4.0 * contiguous + overlap)
    return best


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid input JSON: {exc}")
    if not isinstance(request, dict):
        fail("input must be an object")
    path = request.get("transcript_path")
    chapters = request.get("chapters")
    if not isinstance(path, str) or not Path(path).is_file():
        fail("transcript_path must name an existing file")
    if not isinstance(chapters, list) or not chapters:
        fail("chapters must be a nonempty array")
    try:
        source = json.loads(Path(path).read_text(encoding="utf-8"))
        segments = [clean_segment(x, i) for i, x in enumerate(source["segments"])]
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        fail(f"invalid Whisper transcript: {exc}")
    per_chapter = request.get("per_chapter", 8)
    context = request.get("context", 1)
    if not isinstance(per_chapter, int) or per_chapter < 1 or not isinstance(context, int) or context < 0:
        fail("per_chapter must be positive and context must be nonnegative integers")

    output = []
    for chapter_number, item in enumerate(chapters):
        if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not item["title"]:
            fail(f"chapters[{chapter_number}] must contain a nonempty title")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            fail(f"chapters[{chapter_number}].aliases must be an array of strings")
        phrases = [item["title"]] + [x for x in aliases if x]
        ranked = []
        for i, segment in enumerate(segments):
            value = score(segment["text"], phrases)
            if value > 0:
                lo, hi = max(0, i - context), min(len(segments), i + context + 1)
                ranked.append((value, i, {"start": segment["start"], "end": segment["end"],
                                           "text": segment["text"], "context": segments[lo:hi]}))
        ranked.sort(key=lambda entry: (-entry[0], entry[1]))
        output.append({"title": item["title"], "aliases_used": phrases,
                       "candidates": [dict(candidate, score=round(value, 4))
                                      for value, _, candidate in ranked[:per_chapter]]})
    print(json.dumps({"ok": True, "segment_count": len(segments), "chapter_cues": output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
