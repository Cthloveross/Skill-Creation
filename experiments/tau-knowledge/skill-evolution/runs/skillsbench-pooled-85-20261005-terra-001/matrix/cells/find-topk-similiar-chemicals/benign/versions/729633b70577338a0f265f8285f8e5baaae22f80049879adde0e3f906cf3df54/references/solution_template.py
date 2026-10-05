#!/usr/bin/env python3
"""Find structurally similar chemicals named in a PDF.

The public function returns a list of (source_name, similarity) tuples.  It
uses PubChem as the name-to-structure authority; this file intentionally does
not contain a chemical-name-to-SMILES mapping.
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import AllChem
except ImportError as exc:  # Keep import failure understandable to task users.
    raise RuntimeError("RDKit is required for Morgan fingerprints and Tanimoto similarity") from exc


# A cache is optional and is deliberately data-only: it may contain structures
# exported from an external chemistry authority, never a source-code mapping.
_CACHE_ENVIRONMENT_VARIABLE = "PUBCHEM_STRUCTURE_CACHE"


def _normalise_name(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def _load_external_cache() -> dict[str, str]:
    """Read an optional JSON cache generated from an external authority.

    Its schema is {"chemical name": "isomeric SMILES"}.  This facility is
    useful in network-isolated deployments only when such a provenance-bearing
    cache has been supplied by the caller/environment; it is not populated by
    this program and must not be replaced by a handwritten mapping.
    """
    location = os.environ.get(_CACHE_ENVIRONMENT_VARIABLE)
    if not location:
        return {}
    try:
        raw = json.loads(Path(location).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read {_CACHE_ENVIRONMENT_VARIABLE}={location!r}") from exc
    if not isinstance(raw, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw.items()):
        raise RuntimeError("external structure cache must be a JSON object of names to SMILES strings")
    return {_normalise_name(name).casefold(): smiles for name, smiles in raw.items()}


@lru_cache(maxsize=4096)
def _pubchem_smiles(normalised_name: str) -> str:
    """Resolve a name via PubChem's public PUG REST property endpoint."""
    cached = _load_external_cache().get(normalised_name.casefold())
    if cached:
        return cached

    encoded_name = quote(normalised_name, safe="")
    endpoint = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{encoded_name}/property/IsomericSMILES,CanonicalSMILES/JSON"
    )
    request = Request(endpoint, headers={"Accept": "application/json", "User-Agent": "pdf-chemical-similarity/1.0"})
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"PubChem could not resolve {normalised_name!r}. "
            "Network access or a supplied provenance-bearing PUBCHEM_STRUCTURE_CACHE is required."
        ) from exc

    properties = payload.get("PropertyTable", {}).get("Properties", [])
    if not properties or not isinstance(properties[0], dict):
        raise RuntimeError(f"PubChem returned no structure for {normalised_name!r}")
    # PubChem field spelling has varied across API versions; accept either
    # documented property result rather than manufacturing a structure.
    smiles = properties[0].get("IsomericSMILES") or properties[0].get("CanonicalSMILES") or properties[0].get("SMILES")
    if not isinstance(smiles, str) or not smiles.strip():
        raise RuntimeError(f"PubChem returned no usable SMILES for {normalised_name!r}")
    return smiles.strip()


def _molecule_from_name(name: str):
    clean_name = _normalise_name(name)
    if not clean_name:
        raise ValueError("chemical name must not be blank")
    smiles = _pubchem_smiles(clean_name)
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise RuntimeError(f"PubChem returned an RDKit-unparseable SMILES for {clean_name!r}")
    return molecule


def _fingerprint(molecule):
    """The single required fingerprint policy for both target and candidates."""
    return AllChem.GetMorganFingerprintAsBitVect(
        molecule, radius=2, nBits=2048, useChirality=True
    )


def _clean_pdf_line(line: str) -> str:
    line = _normalise_name(line)
    # Common PDF list/table decorations, not chemical normalization.
    line = re.sub(r"^[\u2022\u2023\u25e6\-*]+\s*", "", line)
    line = re.sub(r"^\(?\d{1,6}[.)]\s*", "", line)
    return line.strip(" \t\"'")


def _looks_like_non_name(line: str) -> bool:
    lowered = line.casefold()
    if not line or len(line) > 160 or re.fullmatch(r"(?:page\s*)?\d+(?:\s+of\s+\d+)?", lowered):
        return True
    if re.fullmatch(r"[\W_]+", line):
        return True
    # Reject headings and boilerplate while retaining actual multiword names.
    heading_words = {"chemical", "chemicals", "chemical name", "compound", "compounds", "molecule", "molecules", "name", "names", "page"}
    return lowered in heading_words


def _table_names(pdf_path: Path) -> list[str]:
    """Extract cells from a column labelled as a name/chemical/molecule column."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return []

    values: list[str] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    if not table:
                        continue
                    header = table[0] or []
                    index = next(
                        (
                            i for i, cell in enumerate(header)
                            if cell and any(token in _normalise_name(cell).casefold() for token in ("chemical", "molecule", "compound", "name"))
                        ),
                        None,
                    )
                    if index is None:
                        continue
                    for row in table[1:]:
                        if index < len(row) and row[index]:
                            cell = _clean_pdf_line(str(row[index]))
                            if not _looks_like_non_name(cell):
                                values.append(cell)
    except Exception as exc:
        warnings.warn(f"table-aware PDF extraction failed ({exc}); using text extraction", RuntimeWarning)
    return values


def _pdf_text(pdf_path: Path) -> str:
    """Read every page with an embedded-text PDF reader."""
    reader_class = None
    try:
        from pypdf import PdfReader  # type: ignore
        reader_class = PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
            reader_class = PdfReader
        except ImportError as exc:
            raise RuntimeError("install pypdf, PyPDF2, or pdfplumber to extract text from the PDF") from exc
    try:
        reader = reader_class(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise RuntimeError(f"could not extract embedded text from {pdf_path}") from exc


def _text_names(text: str) -> list[str]:
    values: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_pdf_line(raw_line)
        # In whitespace-aligned tables, the first nonnumeric field is usually
        # the name. Split only on a tab or a broad layout gap, never on hyphens.
        fields = [field.strip() for field in re.split(r"\t+|\s{3,}", line) if field.strip()]
        if len(fields) > 1:
            line = fields[1] if re.fullmatch(r"\d+", fields[0]) else fields[0]
            line = _clean_pdf_line(line)
        if not _looks_like_non_name(line):
            values.append(line)
    return values


def extract_molecule_names(molecule_pool_filepath: str | os.PathLike[str]) -> list[str]:
    """Extract unique source labels while preserving their source spelling."""
    pdf_path = Path(molecule_pool_filepath)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"molecule pool PDF does not exist: {pdf_path}")

    table_values = _table_names(pdf_path)
    # A labelled table column is more reliable than PDF text reading order.
    raw_values: Iterable[str] = table_values if table_values else _text_names(_pdf_text(pdf_path))
    names: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        name = _normalise_name(raw)
        identity = name.casefold()
        if name and identity not in seen:
            seen.add(identity)
            names.append(name)
    if not names:
        raise RuntimeError("no candidate chemical names were extracted from the PDF; inspect its layout or OCR status")
    return names


def topk_tanimoto_similarity_molecules(
    target_molecule_name: str,
    molecule_pool_filepath: str | os.PathLike[str],
    top_k: int,
) -> list[tuple[str, float]]:
    """Return up to ``top_k`` PDF candidates ranked by structural similarity.

    Candidate labels are retained exactly (apart from whitespace cleanup), so
    output provenance remains the PDF. A target that is also in the PDF is not
    implicitly excluded: the request did not specify self-exclusion.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    if not isinstance(target_molecule_name, str) or not _normalise_name(target_molecule_name):
        raise ValueError("target_molecule_name must be a nonempty string")

    target_fp = _fingerprint(_molecule_from_name(target_molecule_name))
    scored: list[tuple[str, float]] = []
    unresolved: list[str] = []
    for candidate_name in extract_molecule_names(molecule_pool_filepath):
        try:
            candidate_fp = _fingerprint(_molecule_from_name(candidate_name))
        except (RuntimeError, ValueError) as exc:
            unresolved.append(f"{candidate_name!r}: {exc}")
            continue
        score = float(DataStructs.TanimotoSimilarity(target_fp, candidate_fp))
        scored.append((candidate_name, score))

    if unresolved:
        warnings.warn(
            f"skipped {len(unresolved)} PDF names that could not be resolved; first issue: {unresolved[0]}",
            RuntimeWarning,
        )
    if not scored:
        raise RuntimeError("none of the PDF candidate names could be resolved to valid structures")

    scored.sort(key=lambda item: (-item[1], item[0].casefold(), item[0]))
    return scored[:top_k]


def _main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(f"usage: {argv[0]} TARGET_NAME MOLECULES.pdf TOP_K", file=sys.stderr)
        return 2
    try:
        result = topk_tanimoto_similarity_molecules(argv[1], argv[2], int(argv[3]))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
