#!/usr/bin/env python3
"""Solve conventional 13-category dice matches.

JSON stdin: {"workbook": str, "output": str, "pdf": optional str}.
JSON stdout is an audit report; the output file receives only the signed integer.
"""
import json
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import openpyxl


def normal(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def as_integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*[+-]?\d+\s*", value):
        return int(value)
    return None


def as_die(value):
    value = as_integer(value)
    return value if value is not None and 1 <= value <= 6 else None


def check_pdf(path):
    """Require only extractable public dice/scoring context; rule interpretation is documented."""
    if path is None:
        return None
    pdf = Path(path)
    if not pdf.is_file():
        raise ValueError(f"PDF does not exist: {pdf}")
    try:
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages).lower()
    except Exception as exc:
        raise ValueError(f"Could not extract supplied PDF: {exc}")
    if "dice" not in text or ("score" not in text and "scoring" not in text):
        raise ValueError("PDF does not expose required dice-game scoring context")
    return len(text)


def header_candidates(book):
    """Yield complete parsed candidates, preserving labels that are visually merged/blanks."""
    candidates = []
    for sheet in book.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        for header_index, header in enumerate(rows[:40]):
            names = [normal(value) if value is not None else "" for value in header]
            game_columns = [i for i, name in enumerate(names)
                            if name in {"game", "gamenumber", "gameid", "gamenum", "number"}
                            or ("game" in name and ("id" in name or "number" in name))]
            die_columns = [i for i, name in enumerate(names)
                           if ("die" in name or "dice" in name) and re.search(r"\d", name)]
            if len(die_columns) < 5:
                die_columns = [i for i, name in enumerate(names)
                               if "roll" in name and re.search(r"\d", name)]
            if not game_columns or len(die_columns) < 5:
                continue
            game_col, die_columns = game_columns[0], die_columns[:5]
            current_game = None
            parsed = []
            for row_number, row in enumerate(rows[header_index + 1:], header_index + 2):
                if game_col < len(row):
                    proposed = as_integer(row[game_col])
                    if proposed is not None:
                        current_game = proposed
                if current_game is None or max(die_columns) >= len(row):
                    continue
                dice = tuple(as_die(row[col]) for col in die_columns)
                if all(die is not None for die in dice):
                    parsed.append((current_game, dice, row_number))
            if not parsed:
                continue
            groups = defaultdict(list)
            for game, dice, source_row in parsed:
                groups[game].append((dice, source_row))
            complete = all(len(turns) == 13 for turns in groups.values())
            candidates.append({"sheet": sheet.title, "header_row": header_index + 1,
                               "game_column": header[game_col],
                               "dice_columns": [header[i] for i in die_columns],
                               "groups": groups, "records": len(parsed), "complete": complete})
    return candidates


def select_games(workbook):
    path = Path(workbook)
    if not path.is_file():
        raise ValueError(f"Workbook does not exist: {path}")
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        choices = [c for c in header_candidates(book) if c["complete"]]
    finally:
        book.close()
    if not choices:
        raise ValueError("No labeled game/dice table has exactly 13 valid turns per game")
    largest = max(c["records"] for c in choices)
    choices = [c for c in choices if c["records"] == largest]
    signatures = {(c["sheet"], c["header_row"], str(c["game_column"]),
                   tuple(map(str, c["dice_columns"]))) for c in choices}
    if len(signatures) != 1:
        raise ValueError("More than one equally large complete dice table was discovered")
    choice = choices[0]
    games = {game: [dice for dice, _ in turns] for game, turns in choice["groups"].items()}
    source_rows = {game: [row for _, row in turns] for game, turns in choice["groups"].items()}
    return choice, games, source_rows


def category_scores(dice):
    counts = [dice.count(face) for face in range(1, 7)]
    total = sum(dice)
    distinct = set(dice)
    small = any(set(run).issubset(distinct)
                for run in ((1, 2, 3, 4), (2, 3, 4, 5), (3, 4, 5, 6)))
    large = distinct in ({1, 2, 3, 4, 5}, {2, 3, 4, 5, 6})
    return tuple((face + 1) * counts[face] for face in range(6)) + (
        total if max(counts) >= 3 else 0,
        total if max(counts) >= 4 else 0,
        25 if sorted(counts, reverse=True)[:2] == [3, 2] else 0,
        30 if small else 0,
        40 if large else 0,
        50 if max(counts) == 5 else 0,
        total,
    )


def optimal_score(rolls):
    if len(rolls) != 13:
        raise ValueError(f"Expected 13 turns, got {len(rolls)}")
    values = [category_scores(dice) for dice in rolls]

    @lru_cache(maxsize=None)
    def best(turn, used, upper_total):
        if turn == 13:
            return 0
        answer = -10**9
        for category, score in enumerate(values[turn]):
            if used & (1 << category):
                continue
            next_upper = upper_total + (score if category < 6 else 0)
            bonus = 35 if category < 6 and upper_total < 63 <= next_upper else 0
            answer = max(answer, score + bonus + best(turn + 1, used | (1 << category), next_upper))
        return answer
    return best(0, 0, 0)


def solve(obj):
    workbook, output = obj.get("workbook"), obj.get("output")
    if not isinstance(workbook, str) or not isinstance(output, str):
        raise ValueError("workbook and output must be string paths")
    pdf_text_chars = check_pdf(obj.get("pdf"))
    table, games, source_rows = select_games(workbook)
    ids = sorted(games)
    if not ids or ids != list(range(1, max(ids) + 1)):
        raise ValueError("Game IDs must be consecutive integers beginning at 1")
    if len(ids) % 2:
        raise ValueError("An even number of consecutive games is required for pairing")
    scores = {game: optimal_score(rolls) for game, rolls in games.items()}
    p1 = p2 = ties = 0
    matches = []
    for odd in range(1, max(ids) + 1, 2):
        first, second = scores[odd], scores[odd + 1]
        if first > second:
            winner = "player1"; p1 += 1
        elif second > first:
            winner = "player2"; p2 += 1
        else:
            winner = "tie"; ties += 1
        matches.append({"player1_game": odd, "player2_game": odd + 1,
                        "player1_score": first, "player2_score": second, "winner": winner})
    answer = p1 - p2
    Path(output).write_text(f"{answer}\n", encoding="utf-8")
    return {"answer": answer, "player1_wins": p1, "player2_wins": p2, "ties": ties,
            "matches": len(matches), "match_details": matches,
            "table": {key: table[key] for key in ("sheet", "header_row", "game_column", "dice_columns", "records")},
            "game_source_rows": source_rows, "pdf_text_characters_checked": pdf_text_chars}


def main():
    try:
        print(json.dumps(solve(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
