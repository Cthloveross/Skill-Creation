#!/usr/bin/env python3
"""Content-based, byte-preserving organizer for five research subjects.

stdin: {"source_dir": absolute path, "destination_dir": absolute path}
stdout: report JSON. Exit 0 only after a complete validated move.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

SUBJECTS = ("LLM", "trapped_ion_and_qc", "black_hole", "DNA", "music_history")
# Phrases are deliberately domain-specific.  Scores provide explainable evidence,
# rather than relying on names or locations of individual input files.
PATTERNS = {
    "LLM": {
        "large language model": 10, "large language models": 10,
        "language model": 7, "language models": 7, "llm": 7,
        "transformer": 5, "transformers": 5, "attention mechanism": 5,
        "self-attention": 5, "prompting": 4, "prompt engineering": 5,
        "in-context learning": 6, "instruction tuning": 6,
        "reinforcement learning from human feedback": 8, "rlhf": 7,
        "tokenization": 4, "tokenizer": 4, "pretraining": 3,
        "fine-tuning": 3, "generative pretrained": 6,
    },
    "trapped_ion_and_qc": {
        "trapped ion": 10, "trapped ions": 10, "ion trap": 8,
        "quantum computing": 8, "quantum computer": 8, "quantum computation": 7,
        "quantum information": 6, "quantum gate": 6, "qubit": 6,
        "qubits": 6, "quantum error correction": 8, "quantum simulation": 6,
        "paul trap": 8, "ytterbium ion": 8, "calcium ion": 6,
        "motional mode": 5, "rabi oscillation": 5, "entangling gate": 6,
    },
    "black_hole": {
        "black hole": 10, "black holes": 10, "event horizon": 8,
        "hawking radiation": 9, "gravitational singularity": 8,
        "schwarzschild": 7, "kerr black": 8, "accretion disk": 6,
        "gravitational wave": 5, "gravitational waves": 5,
        "general relativity": 5, "spacetime": 3, "astrophysical": 2,
        "supermassive": 5, "photon sphere": 7,
    },
    "DNA": {
        "deoxyribonucleic acid": 12, "dna sequencing": 10, "dna": 9,
        "dna sequence": 8, "genome": 6, "genomic": 6, "genetics": 5,
        "nucleotide": 6, "nucleotides": 6, "base pair": 6,
        "double helix": 7, "polymerase chain reaction": 8, "pcr": 5,
        "crispr": 7, "gene expression": 5, "chromosome": 5,
        "molecular biology": 5, "ribonucleic": 3,
    },
    # Music is both an explicit subject and the residual category.  These
    # terms identify music-focused work even when it uses NLP or genomics
    # methods and therefore mentions another subject's vocabulary.
    "music_history": {
        "music history": 14, "history of music": 14, "musicology": 12,
        "popular music": 12, "classical music": 12, "electronic music": 12,
        "music manuscript": 12, "musical manuscript": 12, "music": 9,
        "musical": 9, "melody": 10, "harmony": 10, "lyrics": 10,
        "lyric": 8, "hip-hop": 12, "hip hop": 12, "rap vocal": 10,
        "song": 7, "songs": 7, "composer": 8, "vocal": 7,
        "musical scale": 10,
    },
}


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_ooxml(path, kind):
    """Extract visible-ish strings from document/slides/notes XML, no mutation."""
    prefix = "word/" if kind == ".docx" else "ppt/"
    allowed = ("document", "header", "footer", "footnotes", "endnotes") if kind == ".docx" else ("slides/", "notesSlides/")
    pieces = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if n.startswith(prefix) and n.endswith(".xml"))
        for name in names:
            relative = name[len(prefix):]
            if kind == ".docx":
                if not relative.startswith(allowed):
                    continue
            elif not relative.startswith(allowed):
                continue
            raw = archive.read(name).decode("utf-8", "ignore")
            # XML text nodes are sufficient for topical recognition; separating
            # adjacent tags avoids gluing words together.
            pieces.append(re.sub(r"</(?:[^:>]+:)?t>", " ", raw))
    return clean_text(" ".join(pieces)), "ooxml_xml"


def extract_pdf(path):
    try:
        result = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=120, check=False)
        text = result.stdout.decode("utf-8", "ignore")
        if len(clean_text(text)) >= 40:
            return clean_text(text), "pdftotext"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    # A bounded printable-string fallback can recover text from some malformed PDFs.
    try:
        data = path.read_bytes()
        chunks = re.findall(rb"[\x20-\x7e]{4,}", data[:20_000_000])
        return clean_text(" ".join(x.decode("latin-1", "ignore") for x in chunks)), "pdf_strings_fallback"
    except OSError:
        return "", "unreadable"


def extract(path):
    suffix = path.suffix.lower()
    try:
        if suffix in (".docx", ".pptx"):
            return extract_ooxml(path, suffix)
        if suffix == ".pdf":
            return extract_pdf(path)
        # Text-like inputs are included rather than left behind.
        if suffix in (".txt", ".md", ".tex", ".rtf", ".csv", ".html", ".htm"):
            return clean_text(path.read_text(encoding="utf-8", errors="ignore")), "plain_text"
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return "", "extraction_error"
    return "", "unsupported"


def phrase_count(text, phrase):
    """Count a phrase as words, avoiding accidental substring matches."""
    return len(re.findall(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


def classify(text):
    folded = text.casefold()
    # PDF text normally begins with the title.  Giving this concise statement
    # of the work's subject extra weight prevents long method/background
    # sections from overpowering the document's primary topic.
    title_region = folded[:1600]
    scores = {}
    hits = {}
    for subject, phrases in PATTERNS.items():
        found = []
        score = 0
        for phrase, weight in phrases.items():
            total_hits = phrase_count(folded, phrase)
            title_hits = phrase_count(title_region, phrase)
            if total_hits:
                # Repeated boilerplate cannot dominate; one title occurrence
                # has five additional evidence units.
                score += weight * (min(total_hits, 4) + 5 * min(title_hits, 1))
                found.append(phrase)
        scores[subject] = score
        hits[subject] = found
    winner = max(SUBJECTS, key=lambda s: scores[s])
    # Music history is the specified exhaustive remainder if no subject term
    # is recoverable, and also wins normally on explicit music evidence.
    if scores[winner] == 0:
        return "music_history", scores, []
    return winner, scores, hits[winner]

def regular_files(root):
    return sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p))


def main():
    try:
        request = json.load(sys.stdin)
        source = Path(request["source_dir"]).resolve()
        destination = Path(request["destination_dir"]).resolve()
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SystemExit("stdin must be JSON with source_dir and destination_dir: " + str(exc))
    if not source.is_dir():
        raise SystemExit("source_dir is not a directory")
    # A destination *parent* may be an ancestor of the source (for example,
    # /root/papers for source /root/papers/all).  Only a destination within
    # the source would be re-inventoried during the move.
    if source == destination or source in destination.parents:
        raise SystemExit("destination_dir must not be source_dir or inside it")

    files = regular_files(source)
    plan, collisions = [], []
    occupied = set()
    for file_path in files:
        text, method = extract(file_path)
        subject, scores, evidence = classify(text)
        target = destination / subject / file_path.name
        if target in occupied or target.exists():
            collisions.append({"source": str(file_path), "target": str(target)})
        occupied.add(target)
        plan.append({"source": str(file_path), "relative_source": str(file_path.relative_to(source)),
                     "filename": file_path.name, "subject": subject, "target": str(target),
                     "extractor": method, "text_characters": len(text), "scores": scores,
                     "evidence": evidence, "needs_review": len(text) < 40})
    if collisions:
        print(json.dumps({"ok": False, "reason": "destination filename collision", "collisions": collisions,
                          "source_before_count": len(files), "moved": []}, indent=2))
        return 2

    for subject in SUBJECTS:
        (destination / subject).mkdir(parents=True, exist_ok=True)
    moved = []
    try:
        for item in plan:
            target = Path(item["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(item["source"], target)
            moved.append(item)
    except OSError as exc:
        # Report exact partial state; never pretend a partial move is success.
        print(json.dumps({"ok": False, "reason": "move failed: " + str(exc), "moved": moved,
                          "source_remaining": [str(x) for x in regular_files(source)]}, indent=2))
        return 3

    remaining = regular_files(source)
    dest_files = []
    for subject in SUBJECTS:
        dest_files.extend(regular_files(destination / subject))
    dest_names = Counter(str(p.relative_to(destination)) for p in dest_files)
    expected_names = Counter(str(Path(x["subject"]) / x["filename"]) for x in plan)
    ok = not remaining and len(dest_files) == len(files) and dest_names == expected_names
    report = {"ok": ok, "source_before_count": len(files), "source_after": [str(x) for x in remaining],
              "destination_inventory_count": len(dest_files), "moved": moved, "collisions": [],
              "needs_review": [x["filename"] for x in moved if x["needs_review"]]}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 4

if __name__ == "__main__":
    sys.exit(main())
