# R2SP Top-5 Model Selection and Auditable Skill Generation Implementation Plan

> **Execution note:** The environment did not provide the referenced `spml:ml-subagent-dev`
> helper, so implementation used isolated TDD subtasks plus a final integration pass. This changes
> orchestration only, not the experiment contract or acceptance criteria below.

**Goal:** Upgrade the pilot to protocol v0.3 so the acquisition agent structurally selects exactly five previously retrieved document candidates, every generated skill has complete provenance and integrity coverage, and both deterministic and real-Qwen synthetic end-to-end runs produce inspectable `SKILL.md` artifacts.

**Experiment directory:** `experiments/pilot/`

**Hypothesis:** A typed, harness-enforced Top-5 selection step will make model choice independently observable, prevent out-of-candidate reads, and allow a live Qwen3.8 service to complete the isolated acquisition → compilation → reset → deployment pipeline without treating synthetic results as research evidence.

**Validation scope:** L0 static/package/config checks; deterministic unit and integration tests; L1 deterministic synthetic full-chain run; optional live eight-RTX Qwen3.8 synthetic full-chain run. AppWorld/H200 research readiness remains separately gated and is not inferred from either smoke mode.

**Evaluation design:** Record candidate Top-10 entry, exact-five model selection, full reads, normalized API execution, compiler input commitments, generated skill bytes/hash, reset attestation, positive/negative deployment, and canary outcomes. Every completed output is bound by a full artifact manifest. Both smoke modes are permanently `research_eligible=false`; a live-model failure is recorded as an engineering observation rather than retried into a selected success.

**Architecture:** `AgentRunner` keeps its four-tool compatibility mode but adds an acquisition-only selection mode with a dynamic `select_docs` tool and strict state transitions. The deterministic runner and a separate live-model runner share the same fixture, compiler, reset, evaluation, reporting, provenance, and artifact-integrity components; only the model client differs. The real research runner consumes the v0.3 selection settings only during acquisition.

---

## Shared Scaffold

### Existing infra (don't touch, advise if problems found)

- Resource loading and deterministic BM25: `src/r2sp/resource_pool.py`, `src/r2sp/retrieval.py`.
- Runtime boundaries: `src/r2sp/runtime/`.
- Compiler allow-list and text-only skill validation: `src/r2sp/compiler.py`.
- Reset, evaluator-owned canary, evaluation, reporting, and write-once artifacts: `src/r2sp/isolation.py`, `src/r2sp/canary.py`, `src/r2sp/evaluation.py`, `src/r2sp/reporting.py`, `src/r2sp/artifacts.py`.
- v0.2 synthetic output remains historical evidence and must not be relabeled as v0.3.

### Needs setup

- Protocol v0.3 declarations and changelog in `EXPERIMENT_PLAN.md`, `configs/experiment_plan.yaml`, `docs/protocol-changelog.md`, `README.md`, and `docs/runbook.md`.
- Acquisition selection state and tests in `src/r2sp/agent.py` and `tests/test_agent.py`.
- Task/skill/model provenance and whole-tree integrity manifests in runner artifacts.
- Separate `r2sp run-model-smoke` command for a loopback real model service.

## Subtask 1: Freeze protocol v0.3 and task provenance

**Role:** Give Top-10 candidate retrieval, exact-five model selection, and original-task provenance one unambiguous machine-readable contract.

**Implementation:** Update `configs/experiment_plan.yaml` to v0.3 with `retriever.top_k: 10`, `retriever.model_select_k: 5`, an acquisition-only selection scope, and a five-tool acquisition catalog. Update `src/r2sp/config.py` validation, the authoritative plan, runbook, README, frozen prompt, and a new changelog. Preserve the v0.2→v0.3 semantic difference explicitly. Record that synthetic tasks originate in `src/r2sp/fixtures.py`; real tasks originate from frozen AppWorld train case IDs and must match `world.task.instruction`.

**Unit Tests:** Update `tests/test_config.py` to require v0.3, reject zero/oversized selection counts, reject a read budget below five, and verify the two readiness gaps remain explicit.

**Expected Conclusion:** "Protocol v0.3 is design-valid, v0.2 results are not silently reclassified, and task origin is documented and machine-recorded."

### Steps

1. Add failing v0.3 config and cross-field validation tests.
2. Run `.venv/bin/python -m unittest tests.test_config -v`; expect failures on the old v0.2 contract.
3. Implement the v0.3 config fields, validation, prompt, plan, changelog, README, and runbook changes.
4. Re-run the config tests and `r2sp validate-config`; expect design-valid and research-not-ready only because runner/data are not frozen.
5. Commit only reviewed protocol and config files with `experiment: freeze v0.3 top5 selection protocol` if the shared dirty worktree can be scoped safely.

## Subtask 2: Harness-enforced exact-five selection

**Role:** Make Top-5 a model action with code-enforced validity, not a prompt convention or BM25 truncation.

**Implementation:** In `src/r2sp/agent.py`, retain compatibility when `selection_k=None`. When `selection_k=5`, dynamically expose `select_docs(resource_ids)` with JSON Schema `minItems=maxItems=5` and `uniqueItems=true`; maintain the ordered union of IDs returned by successful searches; atomically accept one immutable selection only when every ID was seen; reject search after selection; reject reads before selection or outside it without calling the retriever; require a valid selection before execution or successful finish; and persist candidate/selection/read traces. Reject an assistant turn containing multiple tool calls atomically so no partial side effect occurs. Hidden reasoning remains discarded.

**Unit Tests:** Extend `tests/test_agent.py` for exact length, duplicates, unseen IDs, immutable selection, search-after-selection, read-before/outside-selection, retry after invalid selection, atomic multi-call rejection, dynamic tool catalog, selection trace serialization, and a complete Top-10→Top-5→read→execute→finish episode.

**Expected Conclusion:** "The model can choose exactly five seen candidates; invalid or out-of-order actions produce no hidden read/API side effect; all agent tests pass."

### Steps

1. Write failing state-machine and tool-schema tests.
2. Run `.venv/bin/python -m unittest tests.test_agent -v`; expect failures because `select_docs` is absent.
3. Implement the optional selection state machine and durable result fields without importing tests into core code.
4. Re-run agent, model-probe, and research-runner tests; expect all pass.
5. Commit the scoped agent change with `experiment: enforce exact five document selection` if safe.

## Subtask 3: Complete skill and task provenance with artifact integrity

**Role:** Make every question, compiler input commitment, model identity, and generated `SKILL.md` independently inspectable and tamper-evident.

**Implementation:** Move reusable artifact-manifest write/verify logic into `src/r2sp/artifacts.py` and use it from both runners. Persist private `inputs/case.json` plus a body-free public task provenance record. Alongside every skill write `provenance.json` containing task ID/instruction hash, generator kind, model/revision or scripted-fixture identity, agent/compiler prompt hashes, canonical compiler-payload hash, selected/source document commitments, normalized-trace hash, seed, skill path/hash/size, and validity. Never persist API keys or hidden reasoning. Keep raw experimental skill and read bodies only in ignored private output; public reports contain commitments, not poison text.

**Unit Tests:** Extend `tests/test_runner.py`, `tests/test_artifacts.py`, and `tests/test_research_runner.py` to verify skill hashes/provenance, original task source, no credential/reasoning leak, complete-manifest coverage, and cache rejection after deleting or modifying `SKILL.md` or provenance.

**Expected Conclusion:** "Every skill and its source task are recorded, whole-tree integrity is checked on resume, and public artifacts do not leak protected bodies."

### Steps

1. Write failing provenance and corruption/resume tests.
2. Run the focused artifact/runner tests; expect missing provenance and manifest failures.
3. Implement shared manifest helpers and provenance writers; update research and synthetic serialization.
4. Re-run focused tests, then the complete suite.
5. Commit with `experiment: bind skill provenance and artifact tree` if safe.

## Subtask 4: Real-Qwen synthetic runner

**Role:** Distinguish deterministic wiring validation from a genuinely model-generated skill while retaining the same isolated, no-side-effect experiment boundaries.

**Implementation:** Add `run_model_backed_synthetic` and a separate `r2sp run-model-smoke` CLI. Accept only a loopback model URL plus explicit model/revision/timeout/context settings; never borrow unrelated API keys. Before creating output, verify model identity, tokenizer, reasoning/tool parser, and the exact-five selection tool contract. Use the real `OpenAICompatibleClient` for acquisition, compiler, positive deployment, and negative deployment with fresh message contexts. Record a sanitized service/generation fingerprint. Mark mode `synthetic_model_smoke`, `research_candidate=false`, `research_eligible=false`, regardless of outcomes.

**Unit Tests:** Add injected-client tests for all four phases, endpoint precheck before writes, loopback rejection, model fingerprint cache separation, valid generated-skill persistence, and permanent non-research labeling. Do not require canary activation from a stochastic model in unit tests.

**Expected Conclusion:** "A loopback Qwen service can generate a new persisted skill through the real model path, and the result cannot be confused with deterministic smoke or AppWorld research."

### Steps

1. Write failing CLI and injected-model-runner tests.
2. Run focused CLI/runner tests; expect the new command to be absent.
3. Implement the separate live-model path and sanitized preflight/fingerprint.
4. Re-run focused tests and verify no output is created when the endpoint is unavailable.
5. Commit with `experiment: add live qwen synthetic skill run` if safe.

## Subtask 5: Top-5 skill-generation pipeline [INTEGRATION]

**Hypothesis:** A complete isolated run can expose ten BM25 headers, record a model-originated exact-five selection, generate one valid skill from actually read sources, remove the overlay, load only that skill in fresh deployment contexts, and produce integrity-verifiable output.

**Components consumed:** `src/r2sp/config.py`, `src/r2sp/agent.py`, `src/r2sp/runner.py`, `src/r2sp/research_runner.py`, `src/r2sp/model_client.py`, `src/r2sp/compiler.py`, `src/r2sp/artifacts.py`, `src/r2sp/fixtures.py`, runtime/reset/canary/evaluation/reporting modules, prompts, and v0.3 config.

**Implementation:** Update deterministic acquisition scripts to issue `search_docs`, one exact-five `select_docs`, reads, execution, and finish; update the research acquisition runner to pass `selection_k=5`; leave deployment selection disabled. Run deterministic smoke into a new output directory. If the eight-card Qwen service can be provisioned safely, run `run-model-smoke` once into a separate output directory and retain the generated skill/provenance; otherwise record the exact external blocker without substituting scripted output.

**Integration Tests:** Full deterministic smoke asserts ten candidates, five selected IDs, the overlay's candidate/selection/read status, valid Sham/Poison skills, reset, four deployments, report, and full artifact-manifest verification. Live integration asserts completion and artifact integrity but treats selection, task success, canary, and skill validity as measured outcomes.

**Validation Pyramid:** L0 + L1 — L0 is all unit tests, Ruff, formatting, compileall, config validation, and provenance leak checks. L1 is one fresh deterministic v0.3 smoke and, when the endpoint is available, one live Qwen synthetic run using at most eight RTX GPUs.

**Evaluation contract:** Evaluate once after each complete matched case and at finalization; use the same evaluator core for in-memory completion and artifact-based report verification. Emit phase start/end and concise result summaries. Fail closed on missing/corrupt model service, empty/invalid skill, artifact mismatch, non-finite scores, or interrupted finalization. Never silently rerun a completed stochastic live-model output.

**Expected Conclusion:** Deterministic success proves v0.3 wiring. A completed live run proves that the pinned Qwen service generated an auditable skill in the synthetic environment; it still does not establish AppWorld/H200 research outcomes.

### Steps

1. Add the failing v0.3 deterministic full-chain assertions.
2. Run the integration tests; expect failure on missing selection/provenance.
3. Assemble the deterministic and live-model paths and wire research acquisition selection.
4. Run `.venv/bin/python -m unittest discover -s tests -v`; expect all tests pass.
5. Run L0: Ruff check/format, compileall, `r2sp validate-config`, and repository/artifact leak checks.
6. Run L1 deterministic: `r2sp smoke --output runs/top5-smoke-20260830`; expect five selected IDs per acquisition, generated skill files, reset/deployment completion, full artifact manifest, and `research_eligible=false`.
7. Run L1 live when service is ready: `r2sp run-model-smoke --output runs/top5-qwen-20260830 --base-url http://127.0.0.1:18000/v1 --max-model-len 65536`; retain the actual generated `SKILL.md`, provenance, model fingerprint, selection trace, and outcome without post-selection.
8. Record exact commands, hashes, task origin, selected IDs/ranks, generated skill location, measured outcomes, and remaining AppWorld/H200 blockers in `docs/run-records/2026-08-30-top5-smoke.md`.

Execution status (2026-08-30): all eight steps completed. The deterministic and live Qwen runs are
recorded in [`docs/run-records/2026-08-30-top5-smoke.md`](../../../docs/run-records/2026-08-30-top5-smoke.md).
Both are correctly marked non-research; the live Poison full chain did not activate its canary.

## Definition of done

- Top-5 is a typed model action over previously seen Top-10 candidates, not token sampling and not code choosing the first five.
- The original agent question has an explicit source and hash in every run.
- Every generated skill has bytes, hash, source commitments, compiler-payload commitment, prompt/model identity, and whole-tree integrity coverage.
- Deterministic and live-model smoke modes are visibly different and permanently non-research.
- A fresh deterministic full chain passes; a live Qwen full chain is either completed with retained artifacts or blocked with objective provisioning evidence.
- The formal AppWorld pilot remains blocked until its separately listed frozen inputs and H200-equivalent research conditions exist.
