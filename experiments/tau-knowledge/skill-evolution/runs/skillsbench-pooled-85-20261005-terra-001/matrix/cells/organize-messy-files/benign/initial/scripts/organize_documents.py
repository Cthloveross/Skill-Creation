#!/usr/bin/env python3
"""Plan and safely execute content-based research-document organization.

Reads one JSON object from stdin and emits one JSON object to stdout.  See
SKILL.md for the public input and output contract.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

CATEGORIES = ("LLM", "trapped_ion_and_qc", "black_hole", "DNA", "music_history")

# Terms express broad subject concepts, not assumptions about particular files.
TERMS: dict[str, tuple[tuple[str, int], ...]] = {
    "LLM": (
        ("large language model", 10), ("language model", 7),
        ("transformer", 5), ("instruction tuning", 7), ("prompt engineering", 6),
        ("prompting", 4), ("tokenization", 5), ("pretraining", 5),
        ("fine-tuning", 4), ("fine tuning", 4), ("retrieval augmented", 6),
        ("generative ai", 4), ("in-context learning", 6),
    ),
    "trapped_ion_and_qc": (
        ("trapped ion", 11), ("ion trap", 10), ("quantum computing", 9),
        ("quantum computer", 8), ("quantum information", 7), ("qubit", 6),
        ("quantum gate", 6), ("quantum simulation", 6), ("entanglement", 4),
        ("decoherence", 4), ("rydberg", 6), ("quantum error correction", 7),
    ),
    "black_hole": (
        ("black hole", 12), ("event horizon", 8), ("hawking radiation", 9),
        ("gravitational wave", 7), ("accretion disk", 7), ("accretion", 3),
        ("kerr", 6), ("schwarzschild", 7), ("singularity", 5),
        ("general relativity", 5), ("astrophysical", 3),
    ),
    "DNA": (
        ("deoxyribonucleic acid", 10), ("dna sequencing", 9), ("genome", 6),
        ("genomic", 6), ("nucleotide", 6), ("gene expression", 7),
        ("genetics", 5), ("crispr", 8), ("molecular biology", 5),
        ("chromosome", 5), ("polymerase", 5), ("dna", 4),
    ),
    "music_history": (
        ("music history", 11), ("history of music", 10), ("musicology", 8),
        ("composer", 5), ("baroque", 6), ("classical music", 7), ("romantic era", 6),
        ("medieval music", 7), ("opera", 4), ("symphony", 4), ("jazz history", 7),
        ("ethnomusicology", 7),
    ),
}

TEXT_SUFFIXES = {".txt", ".md", ".rst", ".tex", ".html", ".htm", ".csv", ".tsv", ".rtf"}
OOXML_SUFFIXES = {".docx", ".pptx", ".xlsx"}
MAX_TEXT_CHARS = 1_500_000


class InputError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def poor_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 80:
        return True
    letters = sum(c.isalpha() for c in compact)
    return letters < 20


def run_capture(command: list[str], timeout: int) -> str | None:
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def extract_zip_xml(path: Path, kind: str) -> str:
    if kind == ".docx":
        prefixes = ("word/",)
    elif kind == ".pptx":
        prefixes = ("ppt/slides/", "ppt/notesSlides/")
    else:  # xlsx shared strings and worksheets can contain useful title metadata
        prefixes = ("xl/sharedStrings", "xl/worksheets/")
    parts: list[str] = []
    with zipfile.ZipFile(path) as package:
        for name in sorted(package.namelist()):
            if not name.endswith(".xml") or not name.startswith(prefixes):
                continue
            try:
                root = ET.fromstring(package.read(name))
                parts.extend(node.text for node in root.iter() if node.text)
            except (ET.ParseError, KeyError):
                continue
    return clean_text(" ".join(parts))


def ocr_pdf(path: Path, page_count: int) -> str | None:
    if not (shutil.which("pdftoppm") and shutil.which("tesseract")):
        return None
    with tempfile.TemporaryDirectory(prefix="document-ocr-") as temp_dir:
        prefix = str(Path(temp_dir) / "page")
        command = ["pdftoppm", "-f", "1", "-l", str(page_count), "-r", "160", "-png", str(path), prefix]
        try:
            render = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if render.returncode != 0:
            return None
        pages: list[str] = []
        for image in sorted(Path(temp_dir).glob("page-*.png")):
            text = run_capture(["tesseract", str(image), "stdout"], 90)
            if text:
                pages.append(text)
        return clean_text(" ".join(pages)) if pages else None


def extract_text(path: Path, use_ocr: bool, ocr_pages: int) -> tuple[str, str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            text = run_capture(["pdftotext", "-layout", str(path), "-"], 120) if shutil.which("pdftotext") else None
            if text and not poor_text(text):
                return clean_text(text)[:MAX_TEXT_CHARS], "pdftotext"
            if use_ocr:
                ocr_text = ocr_pdf(path, ocr_pages)
                if ocr_text and not poor_text(ocr_text):
                    return ocr_text[:MAX_TEXT_CHARS], "ocr"
            return clean_text(text or "")[:MAX_TEXT_CHARS], "pdf-no-usable-text"
        if suffix in OOXML_SUFFIXES:
            return extract_zip_xml(path, suffix)[:MAX_TEXT_CHARS], "ooxml-xml"
        if suffix in TEXT_SUFFIXES:
            return clean_text(path.read_text(encoding="utf-8", errors="replace"))[:MAX_TEXT_CHARS], "plain-text"
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        return "", "extraction-error:" + type(exc).__name__
    return "", "unsupported-format"


def count_phrase(haystack: str, phrase: str) -> int:
    # Boundary matching avoids treating a short word as part of an unrelated word.
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return len(re.findall(pattern, haystack))


def classify(text: str, filename: str) -> tuple[str, dict[str, int], list[str], bool]:
    body = text.lower()
    name = filename.lower()
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {category: [] for category in CATEGORIES}
    for category, terms in TERMS.items():
        total = 0
        for phrase, weight in terms:
            body_count = min(count_phrase(body, phrase), 8)
            name_count = min(count_phrase(name, phrase), 2)
            if body_count or name_count:
                total += body_count * weight + name_count * (weight * 2)
                matched[category].append(phrase)
        scores[category] = total
    best_score = max(scores.values())
    if best_score == 0:
        return "music_history", scores, [], True
    # CATEGORIES supplies stable behavior for a true score tie.
    chosen = next(category for category in CATEGORIES if scores[category] == best_score)
    runner_up = max(score for category, score in scores.items() if category != chosen)
    evidence = matched[chosen][:8]
    low_confidence = best_score < 6 or best_score - runner_up < 3 or poor_text(text)
    return chosen, scores, evidence, low_confidence


def validate_args(raw: Any) -> tuple[Path, Path, bool, bool, int, dict[str, str]]:
    if not isinstance(raw, dict):
        raise InputError("input must be a JSON object")
    for key in ("source_dir", "destination_root"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise InputError(f"{key} must be a nonempty string")
    source = Path(raw["source_dir"]).expanduser().resolve()
    destination = Path(raw["destination_root"]).expanduser().resolve()
    if not source.is_dir():
        raise InputError("source_dir does not exist or is not a directory")
    if destination == source or source in destination.parents:
        raise InputError("destination_root must not be the source directory or be inside it")
    perform = raw.get("perform_move", False)
    use_ocr = raw.get("ocr_fallback", True)
    pages = raw.get("ocr_pages", 3)
    if not isinstance(perform, bool) or not isinstance(use_ocr, bool):
        raise InputError("perform_move and ocr_fallback must be booleans")
    if not isinstance(pages, int) or isinstance(pages, bool) or not 1 <= pages <= 20:
        raise InputError("ocr_pages must be an integer from 1 through 20")
    overrides = raw.get("overrides", {})
    if not isinstance(overrides, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in overrides.items()):
        raise InputError("overrides must be an object mapping paths to categories")
    if any(v not in CATEGORIES for v in overrides.values()):
        raise InputError("an override has an unsupported category")
    return source, destination, perform, use_ocr, pages, overrides


def collect_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(source.rglob("*"), key=lambda p: p.as_posix()):
        if path.is_symlink():
            raise InputError(f"symlink is not supported: {path.relative_to(source).as_posix()}")
        if path.is_file():
            files.append(path)
    if not files:
        raise InputError("source_dir contains no regular files")
    return files


def build_plan(source: Path, files: list[Path], use_ocr: bool, pages: int,
               overrides: dict[str, str]) -> list[dict[str, Any]]:
    expected_override_paths = set(overrides)
    plan: list[dict[str, Any]] = []
    for path in files:
        rel = path.relative_to(source).as_posix()
        text, extractor = extract_text(path, use_ocr, pages)
        category, scores, evidence, low = classify(text, path.name)
        if rel in overrides:
            category = overrides[rel]
            extractor = "override"
            evidence = ["user-reviewed override"]
            low = False
        plan.append({
            "source_relative_path": rel,
            "filename": path.name,
            "category": category,
            "destination_relative_path": f"{category}/{path.name}",
            "extractor": extractor,
            "scores": scores,
            "evidence": evidence,
            "low_confidence": low,
            "size_bytes": path.stat().st_size,
        })
        expected_override_paths.discard(rel)
    if expected_override_paths:
        unknown = sorted(expected_override_paths)[0]
        raise InputError(f"override does not name a source file: {unknown}")
    targets = [entry["destination_relative_path"] for entry in plan]
    duplicates = [name for name, count in Counter(targets).items() if count > 1]
    if duplicates:
        raise InputError("destination filename collision; preserve names by resolving externally: " + duplicates[0])
    return plan


def preflight_destination(destination: Path) -> None:
    if destination.exists() and not destination.is_dir():
        raise InputError("destination_root exists but is not a directory")
    for category in CATEGORIES:
        target = destination / category
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise InputError(f"target subject folder must be absent or empty: {target}")


def execute(source: Path, destination: Path, files: list[Path], plan: list[dict[str, Any]]) -> dict[str, Any]:
    preflight_destination(destination)
    original_hashes = {entry["source_relative_path"]: sha256_file(source / entry["source_relative_path"]) for entry in plan}
    destination.mkdir(parents=True, exist_ok=True)
    for category in CATEGORIES:
        (destination / category).mkdir(exist_ok=True)
    moved: list[dict[str, str]] = []
    for entry in plan:
        src = source / entry["source_relative_path"]
        dst = destination / entry["destination_relative_path"]
        if not src.is_file() or dst.exists():
            raise RuntimeError(f"move precondition failed for {entry['source_relative_path']}")
        shutil.move(str(src), str(dst))
        moved.append({"source_relative_path": entry["source_relative_path"],
                      "destination_relative_path": entry["destination_relative_path"],
                      "sha256": sha256_file(dst)})
    remaining = collect_regular_paths(source)
    expected = {entry["destination_relative_path"] for entry in plan}
    actual: set[str] = set()
    hashes_ok = True
    for item in moved:
        rel = item["destination_relative_path"]
        actual.add(rel)
        source_rel = item["source_relative_path"]
        hashes_ok = hashes_ok and item["sha256"] == original_hashes[source_rel]
    validation_ok = not remaining and actual == expected and hashes_ok
    return {"ok": validation_ok, "remaining_source_files": remaining,
            "expected_destination_paths": len(expected), "actual_destination_paths": len(actual),
            "hashes_match": hashes_ok, "moved": moved}


def collect_regular_paths(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in sorted(root.rglob("*"), key=lambda x: x.as_posix())
            if p.is_file() and not p.is_symlink()]


def main() -> None:
    try:
        raw = json.load(sys.stdin)
        source, destination, perform, use_ocr, pages, overrides = validate_args(raw)
        files = collect_files(source)
        plan = build_plan(source, files, use_ocr, pages, overrides)
        summary = dict(Counter(entry["category"] for entry in plan))
        result: dict[str, Any] = {"ok": True, "performed_move": perform, "manifest": plan,
                                  "summary": {category: summary.get(category, 0) for category in CATEGORIES}}
        if perform:
            result["validation"] = execute(source, destination, files, plan)
            result["ok"] = result["validation"]["ok"]
        else:
            preflight_destination(destination)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
