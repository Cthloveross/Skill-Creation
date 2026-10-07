---
name: find-topk-similar-chemicals
description: >-
  Build and emit a /root/workspace/solution.py that implements
  topk_tanimoto_similarity_molecules(target_molecule_name, molecule_pool_filepath, top_k).
  It extracts a pool of chemical names from a PDF, resolves names to structures via an
  external chemistry resource (PubChem REST / pubchempy, never a hardcoded name->SMILES
  table), computes Morgan fingerprints (radius=2, chirality on) and Tanimoto similarity,
  and returns the top_k most similar pool chemicals sorted by descending similarity with
  alphabetical tie-breaking. Use when the task asks to find top-k similar chemicals from a
  molecules PDF given one or more target chemical names.
---

# Find Top-K Similar Chemicals

## What the task requires

- Deliverable file: `/root/workspace/solution.py`.
- It must define a function with this exact signature:
  `topk_tanimoto_similarity_molecules(target_molecule_name, molecule_pool_filepath, top_k) -> list`.
- Name -> structure resolution MUST use an external resource (PubChem via REST or
  `pubchempy`, or RDKit-based parsing of resolved SMILES). You may NOT hand-write a
  dictionary mapping chemical names to SMILES.
- Similarity: Morgan fingerprints with `radius=2`, chirality **included**
  (`useChirality=True`), compared with Tanimoto similarity (bounded 0..1).
- Output ordering: descending similarity; ties broken alphabetically by name.
- The pool of candidate chemical names lives inside a PDF (`molecules.pdf`, copied to
  `/root/molecules.pdf`); read it with a PDF-aware library (pdfplumber).

## Method / assumptions

1. **Extract pool names from the PDF.** PDFs have no table objects; names are text
   fragments. The helper tries `extract_tables()` first, then falls back to text lines,
   strips whitespace, drops blank/pure-numeric lines and obvious header tokens, and
   de-duplicates while preserving order. Inspect the actual PDF layout and tune the
   extractor if the real file uses a specific column.
2. **Resolve each name to a structure** through PubChem. The solution prefers
   `pubchempy` if importable and otherwise calls the PubChem PUG REST endpoint for
   `IsomericSMILES` (isomeric so chirality is retained). Results are cached per run and
   requests are gently rate-limited. Names that fail to resolve are skipped (data-quality
   concern, not a fatal error).
3. **Fingerprint + similarity** with RDKit:
   `AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, useChirality=True, nBits=2048)`
   then `DataStructs.TanimotoSimilarity`.
4. **Sort** by `(-similarity, name)` and return the first `top_k` names.

The default return value is a list of pool chemical names (strings). If local checks or
the grader expect `(name, score)` pairs, change the final `return` in
`references/solution_source.py` (one line) and regenerate — keep the sorting/tie rule.

## Dependencies

Requires `rdkit` and `pdfplumber`; `pubchempy` is optional (REST fallback is built in).
Internet is allowed. If missing, install before running the solution:

```
pip install rdkit pdfplumber pubchempy
```

(Package name for RDKit on PyPI is `rdkit`; some images ship it already.)

## How to produce the deliverable

Run the generator; it writes the solution source (from
`references/solution_source.py`) to the target path:

```
echo '{"output_path": "/root/workspace/solution.py"}' | python3 scripts/generate_solution.py
```

Stdin JSON: `{"output_path": "<path>"}` (optional; default
`/root/workspace/solution.py`). Stdout JSON: `{"written": "<path>", "bytes": <int>}`.
The script creates parent directories as needed.

## Validation (run locally, after generating)

1. Confirm the file imports and exposes the function:
   `python3 -c "import importlib.util,sys; s=importlib.util.spec_from_file_location('sol','/root/workspace/solution.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(hasattr(m,'topk_tanimoto_similarity_molecules'))"`
2. Inspect the PDF so your extractor returns real chemical names:
   `python3 scripts/inspect_pdf.py < /dev/null` (edit path inside if needed) or open with
   pdfplumber directly.
3. End-to-end smoke test with a name taken from the pool and a small `top_k` (needs
   internet + rdkit). Expect: a list of length `min(top_k, resolved_pool)`, each score in
   `[0,1]`, descending order, alphabetical ties, and a self-match (similarity 1.0) if the
   target name is itself in the pool. Example:
   `python3 scripts/smoke_test.py` (set TARGET env or edit the script).

Do not bake instance-specific answers, target names, or precomputed lists into the Skill;
read the target name and pool path at call time.
