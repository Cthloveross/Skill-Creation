# R2SP Protocol Changelog

## v0.3 — 2026-08-30

Current authoritative protocol.

### Changed

- BM25 still returns up to 10 body-free document headers per search.
- Acquisition adds the structured `select_docs(resource_ids)` model action. Qwen must commit exactly
  five unique IDs from the ordered union of headers returned by its successful searches.
- The harness rejects reads before selection, reads outside the selected set, search after selection,
  repeated selection, and execution or successful completion without a valid selection. Rejected
  actions must have no retrieval or runtime side effect.
- The acquisition unique-read cap changes from 32 to 5. Selection is acquisition-only; deployment
  retains the four-tool compatibility catalog.
- Runs must record candidate headers/ranks, ordered model selection, reads, task provenance, compiler
  input commitments, and generated-skill integrity data.

### Task provenance

- Research questions come from frozen AppWorld Train task IDs in the protected case bundle. The
  frozen instruction must exactly match `world.task.instruction` in the newly created runtime.
- Synthetic questions come from `src/r2sp/fixtures.py` and are wiring fixtures, not AppWorld evidence.
- Qwen, BM25, and overlay documents do not create or modify the original task. Every run records the
  source, task ID, and instruction hash.

### Unchanged

- `Qwen/Qwen3.8-27B` checkpoint and generation profile.
- Formal H200/BF16 target, deterministic global BM25 parameters, and Top-10 candidate count.
- 16 matched cases, Sham/Poison treatment definition, compiler boundary, hard reset, local canary,
  fixed denominators, and go/no-go thresholds.

### Evidence compatibility

v0.2 and v0.3 are different experimental protocols. Existing v0.2 artifacts, skills, smoke runs, and
reports remain v0.2 and must never be relabeled, merged into a v0.3 denominator, or used to satisfy a
v0.3 selection trace. A v0.3 run requires a new output root and its own config hash, provenance, and
artifact manifest.

## v0.2 — 2026-08-29

Initial feasibility protocol. Acquisition exposed `search_docs`, `read_doc`, `execute`, and `finish`;
an agent could read up to 32 unique documents after searching, with no explicit model-selection
commit. Historical v0.2 evidence remains immutable under that definition.
