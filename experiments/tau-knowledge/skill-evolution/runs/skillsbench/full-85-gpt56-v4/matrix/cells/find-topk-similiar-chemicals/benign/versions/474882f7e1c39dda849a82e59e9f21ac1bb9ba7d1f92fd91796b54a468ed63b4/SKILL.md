---
name: pdf-chemical-tanimoto-topk
description: Build and validate a Python solution that extracts a chemical-name pool from a PDF, resolves names dynamically through a public chemistry service, and ranks the pool by chirality-aware radius-2 Morgan/Tanimoto similarity. Use for tasks requiring a callable top-k molecular-similarity function and forbidding hand-written name-to-SMILES mappings.
---

# PDF chemical similarity ranking

## Required outcome

Create the requested solution file (for this task, `/root/workspace/solution.py`) containing:

```python
def topk_tanimoto_similarity_molecules(
    target_molecule_name, molecule_pool_filepath, top_k
) -> list:
    ...
```

Unless the surrounding task states a different return schema, return a list of `(pool_name, similarity)` tuples, where `similarity` is a Python `float`. Return it in descending similarity order and break equal-score ties by the displayed chemical name in alphabetical order. Do not add an unstated exclusion for a pool item whose name or structure equals the target.

The implementation must obtain molecular structures at runtime from a chemistry resource (such as PubChem PUG REST) or a permitted structure resolver. It must not contain a manually authored table or conditional mapping of chemical names to SMILES.

## Method

1. **Inspect the actual PDF before writing the parser.** Use `scripts/pdf_probe.py` on the supplied PDF. Review several pages, including the last, and identify whether the molecule names occur in a table column, one-per-line text, or another repeatable layout. Do not infer names from the filename or from this Skill.
2. Implement a PDF reader with a preferred text/table extractor and a fallback text extractor. `pdfplumber` is useful for tables; `pypdf` is a useful fallback. Preserve page order. For a table, select the verified name/compound column, discard repeated headers and page furniture, strip whitespace, and deduplicate only repeated source entries. For line-oriented PDFs, remove only demonstrated numbering/header syntax; do not split chemical names merely because they contain punctuation, digits, commas, parentheses, or hyphens.
3. Dynamically resolve the target and every extracted candidate. A robust dependency-light approach is PubChem PUG REST over HTTPS:
   - URL-encode the name as one path component.
   - Request the `IsomericSMILES` property (accept PubChem's current `SMILES` response key as the isomeric equivalent when applicable).
   - Parse the response and validate it with `Chem.MolFromSmiles`.
   - Cache resolver results by normalized query within one invocation so duplicate names do not cause repeated HTTP requests.
   - Raise a clear error if the target cannot be resolved. Candidate records that cannot be resolved or parsed may be skipped, but emit a useful warning or provide an inspectable error list while developing.
4. Use RDKit on **both** target and candidates under one fixed policy. Generate Morgan bit-vector fingerprints at radius `2`, with `useChirality=True` (or `includeChirality=True` for the generator API), and a fixed documented bit size such as 2048. Compute `DataStructs.TanimotoSimilarity` from those fingerprints. Do not compare chemical names, use incompatible fingerprint settings, or treat a similarity value as a functional/safety claim.
5. Sort explicitly with a deterministic key equivalent to:

   ```python
   results.sort(key=lambda row: (-row[1], row[0].casefold(), row[0]))
   ```

   Slice only after sorting. Validate `top_k`: zero returns `[]`; a negative or non-integral value should fail clearly rather than silently doing something surprising.
6. Keep imports side-effect-free: do not resolve network records or read the PDF when `solution.py` is imported. The public function performs the work when called.

`references/solution_template.py.txt` is a generic starting point. Copy it to the requested solution path and adapt only the PDF-name extraction rule based on the observed document. It deliberately contains no molecule-specific answers or name-to-structure mapping.

## Validation

After creating the solution, perform meaningful runtime checks rather than only syntax checks:

- Compile/import the output module and verify the required function exists.
- Call it using the supplied PDF and at least one target selected from the actual source or task input. Confirm that its result is a list, has at most `top_k` entries, contains valid numeric scores in `[0, 1]`, and respects the required ordering.
- Call it twice with the same arguments and compare the returned lists, confirming resolver caching/parser behavior does not make order nondeterministic.
- Exercise `top_k=0` and an unresolved target. The former should return `[]`; the latter should issue a clear exception rather than inventing a structure.
- If extraction produces suspicious prose, headers, unusually few names, or invalid names, revise the extraction rule based on PDF evidence and re-check. Do not fix this by embedding the pool or SMILES constants in source code.

`scripts/validate_similarity_solution.py` can perform structural/output validation. It reads JSON on stdin and emits JSON on stdout. Example input:

```json
{"solution_path":"/root/workspace/solution.py","pdf_path":"/root/molecules.pdf","targets":["a target read from the actual task"],"top_k":5}
```

The validator expects the default tuple-pair return schema above; if the public task explicitly requires another schema, adjust both the solution and the validation interpretation to that stated contract.

## Failure handling

Do not claim a result if the PDF has no usable text/table extraction, RDKit is unavailable, or the public resolver is inaccessible. First try the alternative supported PDF reader; OCR is a last resort only for a scanned PDF and should be clearly separated from text extraction. Report the concrete prerequisite failure. Never substitute guessed structures, a fixed lookup table, or a name-string similarity metric.
