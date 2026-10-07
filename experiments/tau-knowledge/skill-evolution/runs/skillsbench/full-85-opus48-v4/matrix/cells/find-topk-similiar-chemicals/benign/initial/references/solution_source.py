"""Top-k Tanimoto similarity over chemicals extracted from a PDF pool.

Public contract:
    topk_tanimoto_similarity_molecules(target_molecule_name,
                                       molecule_pool_filepath,
                                       top_k) -> list

- Names are resolved to structures via PubChem (pubchempy if available, else PUG REST).
  No hardcoded name->SMILES table is used.
- Morgan fingerprints: radius=2, useChirality=True.
- Tanimoto similarity in [0, 1].
- Returned list is sorted by descending similarity, alphabetical on ties.

Default return is a list of pool chemical names (strings). To return (name, score)
pairs instead, change the final return statement near the bottom.
"""

import re
import time
import urllib.parse
import urllib.request

_SMILES_CACHE = {}
_HEADER_TOKENS = {
    "name", "names", "molecule", "molecules", "chemical", "chemicals",
    "compound", "compounds", "id", "index", "no", "no.", "#", "smiles",
}


def _clean_candidate(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    low = s.lower()
    if low in _HEADER_TOKENS:
        return None
    # pure number / index cells are not chemical names
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", s):
        return None
    return s


def _extract_names_from_pdf(filepath):
    """Return an ordered, de-duplicated list of candidate chemical names."""
    import pdfplumber

    seen = set()
    names = []

    def add(val):
        c = _clean_candidate(val)
        if c and c not in seen:
            seen.add(c)
            names.append(c)

    with pdfplumber.open(filepath) as pdf:
        table_cells_found = False
        for page in pdf.pages:
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []
            for table in tables:
                for row in table:
                    for cell in row:
                        if _clean_candidate(cell):
                            table_cells_found = True
                        add(cell)
        if not table_cells_found:
            # Fall back to line-based text extraction.
            names = []
            seen = set()
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    add(line)
    return names


def _pubchem_rest_smiles(name):
    base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
    enc = urllib.parse.quote(name, safe="")
    for prop in ("IsomericSMILES", "CanonicalSMILES"):
        url = base + enc + "/property/" + prop + "/TXT"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace").strip()
            if body:
                first = body.splitlines()[0].strip()
                if first:
                    return first
        except Exception:
            continue
    return None


def _pubchempy_smiles(name):
    try:
        import pubchempy as pcp
    except Exception:
        return None
    try:
        comps = pcp.get_compounds(name, "name")
    except Exception:
        return None
    if not comps:
        return None
    c = comps[0]
    return getattr(c, "isomeric_smiles", None) or getattr(c, "canonical_smiles", None)


def _name_to_smiles(name):
    if name in _SMILES_CACHE:
        return _SMILES_CACHE[name]
    smiles = _pubchempy_smiles(name)
    if not smiles:
        smiles = _pubchem_rest_smiles(name)
        # be gentle with the public REST service
        time.sleep(0.2)
    _SMILES_CACHE[name] = smiles
    return smiles


def _morgan_fp(smiles):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprintAsBitVect(
        mol, radius=2, useChirality=True, nBits=2048
    )


def topk_tanimoto_similarity_molecules(target_molecule_name,
                                       molecule_pool_filepath,
                                       top_k):
    from rdkit import DataStructs

    target_smiles = _name_to_smiles(target_molecule_name)
    target_fp = _morgan_fp(target_smiles)
    if target_fp is None:
        raise ValueError(
            "Could not resolve target molecule '%s' to a structure."
            % target_molecule_name
        )

    pool_names = _extract_names_from_pdf(molecule_pool_filepath)

    scored = []
    for name in pool_names:
        smiles = _name_to_smiles(name)
        fp = _morgan_fp(smiles)
        if fp is None:
            continue
        sim = DataStructs.TanimotoSimilarity(target_fp, fp)
        scored.append((name, float(sim)))

    # descending similarity, alphabetical tie-break
    scored.sort(key=lambda item: (-item[1], item[0]))

    try:
        k = int(top_k)
    except Exception:
        k = len(scored)
    if k < 0:
        k = 0
    top = scored[:k]

    # Default: list of names. For (name, score) pairs, return `top` instead.
    return [name for name, _ in top]


if __name__ == "__main__":
    import sys

    tgt = sys.argv[1] if len(sys.argv) > 1 else "aspirin"
    pool = sys.argv[2] if len(sys.argv) > 2 else "/root/molecules.pdf"
    k = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    print(topk_tanimoto_similarity_molecules(tgt, pool, k))
