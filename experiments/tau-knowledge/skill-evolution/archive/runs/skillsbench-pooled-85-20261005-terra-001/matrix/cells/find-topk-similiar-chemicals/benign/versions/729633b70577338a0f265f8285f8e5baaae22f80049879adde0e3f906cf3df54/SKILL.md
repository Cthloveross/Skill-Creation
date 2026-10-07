---
name: pdf-chemical-topk-tanimoto
description: Build a Python solution that extracts chemical names from a PDF, resolves names through a chemistry authority rather than a handwritten name-to-SMILES table, and ranks PDF chemicals by chirality-aware radius-2 Morgan-fingerprint Tanimoto similarity.
---

# PDF chemical similarity search

Use this Skill when a task requires a callable top-k structural-similarity search over chemical names found in a PDF.

## Required representation policy

Apply one policy to the target and every candidate:

- obtain a structure from an external chemistry resource (the supplied solution uses PubChem PUG REST), rather than a local, handwritten name-to-SMILES dictionary;
- parse the returned isomeric SMILES with RDKit;
- construct a 2048-bit Morgan fingerprint with `radius=2` and `useChirality=True`;
- calculate RDKit Tanimoto similarity;
- rank by decreasing unrounded similarity and then alphabetically (case-insensitive, with the original name as a final deterministic tie-breaker).

Similarity is structural and representation-dependent. Do not infer it from name spelling or use it as a claim about activity or safety.

## Build the requested artifact

The packaged template implements:

```python
topk_tanimoto_similarity_molecules(
    target_molecule_name, molecule_pool_filepath, top_k
) -> list[tuple[str, float]]
```

Each result tuple is `(PDF_name, tanimoto_score)`. The score remains a numeric float and is not rounded before ranking or returning.

Create `/root/workspace/solution.py` by running the builder with JSON on standard input:

```bash
python scripts/build_solution.py <<'JSON'
{"output_path":"/root/workspace/solution.py"}
JSON
```

The builder emits JSON containing the output path and performs static validation that the required function is present. The generated solution can also be used as a command-line program:

```bash
python /root/workspace/solution.py 'target chemical name' /root/molecules.pdf 10
```

It writes a JSON array of `[name, score]` pairs in CLI mode.

## Runtime prerequisites and failure handling

The executor needs RDKit, a text-capable PDF reader (`pypdf`, `PyPDF2`, or `pdfplumber`), and access to PubChem. The target runtime described for this task has no network, so resolution cannot succeed for ordinary names unless a permitted chemistry-resource cache/service is available during actual execution. This is a real prerequisite, not a reason to create a guessed structure mapping. The solution raises a clear `RuntimeError` if the target cannot be resolved and warns when individual pool names cannot be resolved; it returns only resolvable candidates.

Before relying on results, inspect extraction quality for the actual PDF. PDF layout is not semantic: verify that names are one-per-line or are being recovered from the correct table column, that headings/page labels are not candidates, and that the source is fully read. The template uses both table-aware extraction and a conservative text fallback. If the actual document has an unusual layout, improve extraction based on the document itself without changing the fingerprint/ranking policy and without hardcoding extracted names or structures.

Validate a completed run by checking that: (1) the returned length is at most `top_k`; (2) every returned score is between 0 and 1; (3) scores are non-increasing; (4) equal-score entries are alphabetical; and (5) no candidate structure was supplied by a manually maintained name-to-SMILES mapping.
