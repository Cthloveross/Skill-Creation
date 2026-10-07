#!/usr/bin/env python3
"""OCR a receipt image directory into a strict results Excel workbook.

Reads JSON from stdin:
  {"input_dir": str, "output_path": str, "debug_dir": optional str}
Writes one JSON status object to stdout.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from openpyxl import Workbook, load_workbook

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
# These are normalized in total_label_score so minor OCR spacing and hyphens do not
# turn a subtotal, tax line, or item count into a payable total.
EXCLUSIONS = ("SUBTOTAL", "TAX", "SST", "DISCOUNT", "CHANGE", "CASH TENDERED")
MONTHS = {
    "JAN": 1, "JANUARY": 1, "FEB": 2, "FEBRUARY": 2, "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4, "MAY": 5, "JUN": 6, "JUNE": 6, "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8, "SEP": 9, "SEPT": 9, "SEPTEMBER": 9, "OCT": 10,
    "OCTOBER": 10, "NOV": 11, "NOVEMBER": 11, "DEC": 12, "DECEMBER": 12,
}
NUMBER_RE = re.compile(r"(?<![\d/])(?:\d{1,3}(?:[,.]\d{3})+|\d+)(?:[,.]\d{2})?(?![\d/])")
YEAR_FIRST_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})(?!\d)")
# Requiring one repeated separator prevents an invoice/terminal sequence such as
# "19- 18/01/2018" from consuming the beginning of the actual date.
NUMERIC_DATE_RE = re.compile(r"(?<![\d/-])(\d{1,2})\s*([/.-])\s*(\d{1,2})\s*\2\s*(\d{2,4})(?!\d)")
MONTH_DATE_RE_1 = re.compile(r"(?<!\w)(\d{1,2})\s*[-/. ]\s*([A-Z]{3,9})\s*[-,/. ]\s*(\d{2,4})(?!\w)", re.I)
MONTH_DATE_RE_2 = re.compile(r"(?<!\w)([A-Z]{3,9})\s+(\d{1,2})(?:ST|ND|RD|TH)?[,]?\s+(\d{2,4})(?!\w)", re.I)


def image_files(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda p: (p.name.casefold(), str(p).casefold()),
    )


def ocr_texts(path: Path) -> list[str]:
    """Return distinct OCR transcripts from modest, field-safe image variants."""
    with Image.open(path) as opened:
        base = ImageOps.exif_transpose(opened).convert("L")
    # Upscaling helps thermal-receipt glyphs while avoiding destructive rotation guesses.
    base = base.resize((base.width * 2, base.height * 2), Image.Resampling.LANCZOS)
    enhanced = ImageOps.autocontrast(base)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.8)
    thresholded = enhanced.point(lambda px: 255 if px > 185 else 0)
    variants = (base, enhanced, thresholded)
    texts: list[str] = []
    seen: set[str] = set()
    for image in variants:
        for psm in (6, 11):
            text = pytesseract.image_to_string(image, config=f"--oem 3 --psm {psm}")
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if text not in seen:
                seen.add(text)
                texts.append(text)
    return texts


def normalize_amount(token: str) -> Optional[str]:
    """Parse a displayed money token and return a fixed two-decimal string."""
    token = token.strip().replace(" ", "")
    if not token or not re.search(r"\d", token):
        return None
    # With both punctuation marks, the final mark is the decimal mark. With one,
    # a final two-digit group is treated as cents; otherwise it is grouping.
    last_dot, last_comma = token.rfind("."), token.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal_at = max(last_dot, last_comma)
        integer = re.sub(r"[,.]", "", token[:decimal_at])
        fraction = token[decimal_at + 1:]
        clean = integer + "." + fraction
    elif last_dot >= 0 or last_comma >= 0:
        mark = "." if last_dot >= 0 else ","
        pieces = token.split(mark)
        if len(pieces[-1]) == 2:
            clean = "".join(pieces[:-1]) + "." + pieces[-1]
        else:
            clean = "".join(pieces)
    else:
        clean = token
    try:
        value = Decimal(clean)
    except InvalidOperation:
        return None
    if value < 0 or value > Decimal("1000000000"):
        return None
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def line_amounts(line: str) -> list[str]:
    """Return displayed monetary tokens, repairing only OCR whitespace in decimals.

    Receipt OCR commonly emits ``88. 17`` or ``10 00``.  Joining those patterns
    here, locally at a candidate amount line, avoids unsafe global digit edits.
    """
    cleaned = re.sub(r"(?<=\d)\s*([.,])\s*(?=\d{2}(?!\d))", r"\1", line)
    # A bare final pair of cents is accepted only after an integer and whitespace;
    # dates retain separators and therefore are unaffected.
    cleaned = re.sub(r"(?<![\d.,])(\d{1,7})\s+(\d{2})(?!\d)", r"\1.\2", cleaned)
    values: list[str] = []
    for token in NUMBER_RE.findall(cleaned):
        normalized = normalize_amount(token)
        if normalized is not None:
            values.append(normalized)
    return values


def total_label_score(line: str) -> int:
    """Rank final-payable labels and reject accounting/item-count lookalikes."""
    upper = re.sub(r"\s+", " ", line.upper())
    compact = re.sub(r"[^A-Z0-9]", "", upper)
    # Hyphenated SUB-TOTAL and lines such as GST SUMMARY must not fall through to
    # the generic TOTAL rule.  Item(s) is a count rather than a payable amount.
    if (any(word in compact for word in EXCLUSIONS)
            or "GSSUMMARY" in compact or "GSTSUMMARY" in compact
            or re.search(r"\bGST\s+(?:SUMMARY|PAYABLE)\b", upper)
            or re.search(r"\bTOTAL\s+(?:INCLUD(?:E|ES|ED)|SAVINGS)\b", upper)
            or re.search(r"\bINCLUDED\s+IN\s+TOTAL\b", upper)
            or re.search(r"\bGST.*\bINCLUDED\b.*\bTOTAL\b", upper)
            or re.search(r"\bTOTAL\s*(?:I?TEM|QTY|QUANTITY|TAX)\b", upper)):
        return 0
    if re.search(r"\bGRAND\s*TOTAL\b", upper) or "GRANDTOTAL" in compact:
        return 100
    if re.search(r"\b(?:TOTAL|TOTA[IL])\s*(?:\(\s*)?(?:RM|RN)\b", upper):
        return 90
    if re.search(r"\b(?:ROUNDED\s+TOTAL|TOTAL\s+(?:ROUNDED|AFTER|INCL(?:USIVE)?|SALES|GROSS))\b", upper):
        return 85
    if re.search(r"\b(?:TOTAL|TOTA[IL])\s*(?:AMOUNT|AMT)\b", upper):
        return 80
    if re.search(r"\b(?:TOTAL\s+DUE|AMOUNT\s+DUE|BALANCE\s+DUE|NETT?\s+TOTAL)\b", upper):
        return 70
    if re.search(r"\b(?:TOTAL|AMOUNT)\b", upper):
        return 50
    return 0


def extract_total(texts: Iterable[str]) -> Optional[str]:
    candidates: list[tuple[str, int]] = []
    for text in texts:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            score = total_label_score(line)
            if not score:
                continue
            # A payable total is commonly adjacent to its rounding adjustment or
            # tender/payment line.  This context disambiguates it from a GST
            # summary's "Total" while retaining the documented label priorities.
            previous = lines[index - 1].upper() if index else ""
            following_line = lines[index + 1].upper() if index + 1 < len(lines) else ""
            if (re.search(r"\bROUNDING\b", previous)
                    or re.search(r"\b(?:CASH|CARD|VISA|MASTERCARD|PAYMENT)\b", following_line)):
                score = max(score, 90)
            amounts = line_amounts(line)
            if amounts:
                # Receipt lines can contain a count as well as the final amount.
                candidates.append((amounts[-1], score))
                continue
            # The public fallback: label and value split across successive lines.
            if index + 1 < len(lines) and not any(x in lines[index + 1].upper() for x in EXCLUSIONS):
                following = line_amounts(lines[index + 1])
                if following:
                    candidates.append((following[-1], score - 8))
    if not candidates:
        return None
    support = Counter(value for value, _ in candidates)
    # Preserve label priority; agreement across preparations breaks close calls.
    return max(candidates, key=lambda item: (item[1] + min(support[item[0]], 4) * 5, item[1], item[0]))[0]


def year_from_token(token: str) -> int:
    year = int(token)
    if year < 100:
        return 2000 + year if year <= 69 else 1900 + year
    return year


def safe_iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def date_tokens(text: str) -> list[tuple[str, int, object]]:
    """Return (kind, evidence score, parts) without resolving ambiguous day/month."""
    out: list[tuple[str, int, object]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        score = 60 if re.search(r"\b(?:DATE|DATED|INVOICE\s+DATE|PURCHASE\s+DATE)\b", upper) else 10
        for match in YEAR_FIRST_RE.finditer(line):
            out.append(("iso", score, (int(match.group(1)), int(match.group(2)), int(match.group(3)))))
        for match in MONTH_DATE_RE_1.finditer(upper):
            month = MONTHS.get(match.group(2).upper())
            if month:
                out.append(("iso", score, (year_from_token(match.group(3)), month, int(match.group(1)))))
        for match in MONTH_DATE_RE_2.finditer(upper):
            month = MONTHS.get(match.group(1).upper())
            if month:
                out.append(("iso", score, (year_from_token(match.group(3)), month, int(match.group(2)))))
        for match in NUMERIC_DATE_RE.finditer(line):
            out.append(("numeric", score, (int(match.group(1)), match.group(2), int(match.group(3)), year_from_token(match.group(4)))))
    return out


def infer_date_order(all_texts: Iterable[str]) -> Optional[str]:
    votes: Counter[str] = Counter()
    saw_rm = False
    for text in all_texts:
        saw_rm = saw_rm or bool(re.search(r"\bRM\b", text.upper()))
        for kind, score, parts in date_tokens(text):
            if kind != "numeric":
                continue
            first, _separator, second, _year = parts  # type: ignore[misc]
            if first > 12 and second <= 12:
                votes["dmy"] += score
            elif second > 12 and first <= 12:
                votes["mdy"] += score
    if votes["dmy"] or votes["mdy"]:
        if votes["dmy"] != votes["mdy"]:
            return "dmy" if votes["dmy"] > votes["mdy"] else "mdy"
        return None
    # RM is an observed current-input locale signal, not a blind country default.
    return "dmy" if saw_rm else None


def extract_date(texts: Iterable[str], order: Optional[str]) -> Optional[str]:
    candidates: list[tuple[str, int]] = []
    for text in texts:
        for kind, score, parts in date_tokens(text):
            if kind == "iso":
                year, month, day = parts  # type: ignore[misc]
                value = safe_iso(year, month, day)
            else:
                first, _separator, second, year = parts  # type: ignore[misc]
                if first > 12 and second <= 12:
                    value = safe_iso(year, second, first)
                elif second > 12 and first <= 12:
                    value = safe_iso(year, first, second)
                elif order == "dmy":
                    value = safe_iso(year, second, first)
                elif order == "mdy":
                    value = safe_iso(year, first, second)
                else:
                    value = None
            if value:
                candidates.append((value, score))
    if not candidates:
        return None
    support = Counter(value for value, _ in candidates)
    return max(candidates, key=lambda item: (item[1] + min(support[item[0]], 4) * 5, item[1], item[0]))[0]


def validate_workbook(output: Path, expected_names: list[str]) -> None:
    workbook = load_workbook(output, data_only=False)
    if workbook.sheetnames != ["results"]:
        raise ValueError("output workbook does not contain exactly one results sheet")
    sheet = workbook["results"]
    if sheet.max_column != 3 or sheet.max_row != len(expected_names) + 1:
        raise ValueError("output workbook has an unexpected shape")
    headers = [sheet.cell(1, col).value for col in range(1, 4)]
    if headers != ["filename", "date", "total_amount"]:
        raise ValueError("output workbook headers are incorrect")
    found_names = [sheet.cell(row, 1).value for row in range(2, sheet.max_row + 1)]
    if found_names != expected_names:
        raise ValueError("output workbook filenames are not complete and sorted")


def main(config: dict) -> dict:
    input_dir = Path(config["input_dir"])
    output = Path(config["output_path"])
    if not input_dir.is_dir():
        raise ValueError(f"input_dir is not a directory: {input_dir}")
    files = image_files(input_dir)
    debug_dir = Path(config["debug_dir"]) if config.get("debug_dir") else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    transcripts: dict[Path, list[str]] = {}
    for path in files:
        texts = ocr_texts(path)
        transcripts[path] = texts
        if debug_dir:
            (debug_dir / f"{path.name}.txt").write_text("\n\n===== OCR PASS =====\n\n".join(texts), encoding="utf-8")

    order = infer_date_order(text for values in transcripts.values() for text in values)
    rows: list[tuple[str, Optional[str], Optional[str]]] = []
    for path in files:
        texts = transcripts[path]
        rows.append((path.name, extract_date(texts, order), extract_total(texts)))

    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "results"
    sheet.append(["filename", "date", "total_amount"])
    for row in rows:
        sheet.append(list(row))
    workbook.save(output)
    validate_workbook(output, [row[0] for row in rows])
    return {
        "ok": True,
        "output_path": str(output),
        "records": len(rows),
        "missing_dates": sum(row[1] is None for row in rows),
        "missing_totals": sum(row[2] is None for row in rows),
    }


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise ValueError("stdin must contain a JSON object")
        result = main(config)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
