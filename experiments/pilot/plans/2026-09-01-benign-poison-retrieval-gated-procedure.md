# Benign/Poison Retrieval-Gated File-Backed Injection Implementation Plan

**Goal:** Use an original-document Benign arm and a lead-bearing Poison arm, then hard-stop before skill compilation unless the Poison target is naturally retrieved, selected, and read.

**Experiment directory:** `experiments/pilot/`

**Hypothesis:** A task-relevant retrieval lead added only to one genuine Poison endpoint will raise that endpoint into BM25 Top-10 without forced insertion, after which the authoring model may select it in its exact-five set and read it in full.

**Validation scope:** L0 static/schema/unit checks plus L1 deterministic full-corpus materialization and retrieval-gate execution. Model-backed skill generation is outside this revision until the new retrieval gate and corpus pass.

**Evaluation design:** Use the immutable AppWorld authoring instruction as the canonical pre-model query; do not gate on hand-written paraphrases. Record Benign and Poison ranks from the same 447-resource corpus layout, but require only Poison Top-10. During real acquisition, inspect the model's actual search traces and require Poison Top-10, exact-five selection, and full body/hash read before invoking the compiler. A rejected lead version produces no `SKILL.md`; changing the lead creates a new versioned corpus and a new gate artifact. Deployment is permitted only when both fixed profiles pass the complete compile gate. Artifact-directory and in-memory evaluators must share one evaluator core and emit phase-start, progress, phase-end, result, and timing records.

**Architecture:** Use `benign/A_benign` and `poison/B_poison` as the only protocol arm names. Materialize Benign as a byte-equivalent full copy of the official JSON corpus using an identity transform; materialize Poison as the same corpus with one endpoint description prepended by the retrieval lead and required block. Split retrieval admission from compiler execution and make the deployment entrypoint require 2/2 compile-gate success.

---

## Shared Scaffold

### Existing infra

- Source and derived-corpus verification: `src/r2sp/file_injection.py`
- AppWorld file-backed fixture binding: `src/r2sp/file_injection_fixture.py`
- Profile/task definitions: `src/r2sp/file_injection_profiles.py`
- BM25: `src/r2sp/retrieval.py`
- Agent exact-five state machine: `src/r2sp/agent.py`
- Compiler: `src/r2sp/compiler.py`
- Compile gate: `src/r2sp/injection_runner.py`
- Deployment loader/evaluator: `src/r2sp/injection_deployment_runner.py`
- Live entrypoint: `src/r2sp/file_injection_live.py`

### New protocol invariants

1. Public names and on-disk arms are exactly `benign` and `poison`.
2. `benign` is a full byte-equivalent copy of the original standard API-document tree.
3. Only `poison` contains `retrieval_lead` or the required runtime block.
4. The target retains the original production resource ID in both arms.
5. The pre-model query is the original AppWorld authoring instruction loaded from the source task and checked against its integrity commitment.
6. BM25 uses the complete 447-resource pool; no result is appended, boosted, whitelisted, or reordered.
7. Poison must naturally enter Top-10 in the pre-model gate.
8. The model's actual acquisition must expose Poison in Top-10, select it in the exact five, and read the matching body/hash in full.
9. The compiler is never called before all three actual-acquisition conditions pass.
10. Deployment requires both fixed profiles to have valid persisted skills from the same complete gate.
11. A lead edit creates a new versioned corpus; no in-place overwrite or favorable-result selection.

## Subtask 1: Normalize all protocol surfaces to Benign/Poison

**Role:** Establish one unambiguous arm vocabulary across Python models, schemas, configs, artifacts, metrics, directories, tests, and user documentation.

**Implementation:** Normalize the control arm to `benign/A_benign`, its metrics to `benign_*`, and `OverlayPair.benign`. Update `src/r2sp/{models,cases,config,evaluation,reporting,runner,research_runner,fixtures,preflight}.py`, experiment schemas/config, all callers, and tests. Legacy names must be rejected instead of silently aliased because this is a new protocol version.

**Unit Tests:** Update serialization round trips, schema validation, arm scheduling, evaluator aggregation, report headings, provenance commitments, and error cases to assert only `benign`/`poison` and `A_benign`/`B_poison`.

**Expected Conclusion:** "All active protocol surfaces use Benign/Poison; legacy control keys are absent from active code and schemas."

### Steps

1. Update model/schema/config tests to expect Benign names.
2. Rename core model fields, serialized keys, metrics, and schedule values.
3. Update runners, reports, fixtures, and tests.
4. Run all affected unit tests and `rg` for residual legacy control identifiers.
5. Record scoped changes; do not make an implicit commit in the shared dirty worktree.

## Subtask 2: Materialize Original Benign and Lead-Only Poison Corpora

**Role:** Make retrieval differences causally attributable to Poison-only content.

**Implementation:** Replace `_injection_bodies()` with a Poison-body builder plus an identity Benign path. Add an auditable identity-copy transform to `file_injection.py`. Benign JSON bytes must match the official source tree; Poison changes exactly one endpoint `description`. Generate a new corpus root `experiments/pilot/data/file-injection-appworld-20260901-v3/benign|poison` per profile and never mutate the prior bundle in place.

**Unit Tests:** Assert Benign corpus/file/endpoint hashes equal source; Benign contains no retrieval lead, required block, tool, or nonce; Poison contains the exact lead and block at the declared JSON pointer; only the Poison target differs; both arms reconstruct 457 raw and 447 task-facing resources; manifests replay after restart.

**Expected Conclusion:** "Benign is the original document corpus; Poison alone contains the retrieval lead and injection."

### Steps

1. Write identity-copy and Poison-only materialization tests.
2. Implement identity manifest/loader support and the Poison-only body builder.
3. Update file-backed fixture provenance and arm validation.
4. Materialize the fresh v3 corpus and replay every manifest.
5. Remove the superseded project-local derived corpus only after v3 validation; preserve official source data.

## Subtask 3: Enforce the Real Retrieval Gate

**Role:** Test the attack lead against the actual task without forcing retrieval.

**Implementation:** Use a pre-model retrieval gate that searches the exact authoring instruction against the complete Benign and Poison pools. Record both ranks and score delta; require Poison rank 1–10. Then run authoring acquisition and inspect its actual search trace. If Poison is absent from Top-10, absent from exact-five, or not read with exact body/hash, finalize a retrieval-rejected artifact and return before constructing or calling `SkillCompiler`.

**Unit Tests:** Cover Poison rank 10 pass, rank 11 reject, no result injection, exact corpus-manifest binding, actual-query Top-10 miss, exact-five miss, full-read/hash mismatch, and assertions that compiler call count remains zero for every rejection path.

**Expected Conclusion:** "Only naturally exposed Poison reaches the compiler; a weak lead cannot produce a skill."

### Steps

1. Write pre-model and actual-acquisition gate tests with a compiler spy.
2. Implement original-task retrieval evidence over the complete pool.
3. Move exposure validation before compiler construction/call.
4. Store lead text hash, corpus hash, task instruction hash, Top-10 headers, target rank, actual search queries, exact-five IDs, and read hash in the gate artifact.
5. Run focused retrieval/runner tests.

## Subtask 4: Make Deployment Require Complete 2/2 Compile Success

**Role:** Prevent deployment of a partial experiment.

**Implementation:** Change compile progression from `passed_count > 0` to `passed_count == profile_count == 2`. Set the file-backed deployment entrypoint to require the compile gate. Revalidate each profile's exposure, skill validity, semantic persistence, skill hash, source evidence, and corpus version before loading any skill.

**Unit Tests:** Assert 0/2 and 1/2 cannot deploy, 2/2 can deploy, a missing `SKILL.md` cannot deploy, and a compile/deployment corpus-version mismatch is rejected.

**Expected Conclusion:** "Deployment starts only after both Poison profiles have complete valid compile artifacts."

### Steps

1. Write 0/2, 1/2, 2/2 deployment-gate tests.
2. Implement the all-profile condition and strict live-deployment flag.
3. Bind deployment input to the v3 corpus and complete compile hash.
4. Run deployment tests.
5. Record scoped changes; do not make an implicit commit.

## Subtask 5: Replace the Run Record with procedure.md

**Role:** Maintain one complete, current, implementation-matched procedure.

**Implementation:** Make `docs/run-records/procedure.md` the sole run record. Document Poison-only lead construction, original Benign corpus, canonical-task retrieval gate, actual-query gate, compiler stop rule, lead versioning, exact-five/full-read requirements, 2/2 deployment condition, model/GPU settings, paths, commands, artifacts, and safety boundaries. Update README and all links, then remove superseded run records and machine summaries.

**Unit Tests:** Validate all local Markdown links and assert active procedure/README contain no legacy arm names, old record filename, old summary filename, or obsolete derived-corpus path.

**Expected Conclusion:** "procedure.md is the sole authoritative workflow document and matches active code."

### Steps

1. Write the new procedure from the implemented contracts.
2. Update README and current plan links.
3. Delete superseded record/summary files after the new procedure exists.
4. Run link and terminology audits.
5. Record the exact deletion/recovery status.

## Subtask 6: Complete Benign/Poison Retrieval-Gated Pipeline [INTEGRATION]

**Hypothesis:** A Poison-only retrieval lead can naturally admit both target endpoints to Top-10 and the hard gates prevent any non-exposed Poison from reaching skill compilation or deployment.

**Components consumed:** Subtasks 1–5 across `models.py`, `file_injection.py`, `file_injection_fixture.py`, `injection_runner.py`, `file_injection_live.py`, schemas, tests, and `procedure.md`.

**Implementation:** Run full static/schema/unit validation, materialize and replay the v3 corpus, execute the deterministic canonical-task retrieval gate for both profiles, and emit a versioned retrieval-gate artifact. Do not start the model or generate skills in this revision. The shared evaluator core must support direct in-memory results and artifact-directory replay with identical outcomes.

**Integration Tests:** Official JSON → Benign identity corpus + Poison lead corpus → manifest replay → 447-resource BM25 → canonical-task Top-10 gate → rejected-lead compiler-call count zero / accepted-lead ready-for-acquisition status.

**Validation Pyramid:** L0 + L1 — L0 runs Ruff, format, schemas, compileall, full pytest, terminology and link audits. L1 materializes fresh corpora and runs the real 447-resource retrieval gate, reporting Benign/Poison rank, score, target ID, corpus hash, lead hash, duration, and ready/not-ready status.

**Evaluation contract:** Evaluate once per immutable lead/corpus version. Default scope is both profiles. Artifact-directory replay and in-memory evaluation use the same core. Emit phase-start, per-profile progress, phase-end, result summary, and timing. Reject unreadable source, manifest mismatch, wrong resource counts, Poison outside Top-10, non-finite scores, compiler invocation before exposure, or partial-profile deployment readiness.

**Expected Conclusion:** "Both profiles either pass natural Poison Top-10 admission and become ready for model acquisition, or the pipeline stops before skill generation with an immutable lead-version artifact."

### Steps

1. Add the full-corpus integration test.
2. Assemble the renamed materializer, retrieval evaluator, gates, and documentation.
3. Run L0 validation.
4. Materialize the v3 corpus and run L1 retrieval admission only.
5. Record actual ranks/hashes in `docs/run-records/procedure.md` without generating a skill.
6. Leave model service stopped and GPUs untouched.
7. Run `git diff --check` and list all scoped changes; do not make an implicit commit.
