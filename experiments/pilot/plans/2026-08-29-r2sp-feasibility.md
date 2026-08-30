# R2SP AppWorld × Qwen3.8 Feasibility Implementation Plan

**Goal:** Build a reproducible, safety-bounded runner for the v0.2 matched Sham/Poison pilot and prove the instrumentation locally with a synthetic end-to-end smoke run.

**Experiment directory:** `experiments/pilot/`

**Hypothesis:** A naturally read Poison overlay can be compiled into the only cross-reset skill artifact and later cause a nonce-matched local canary event more often than a matched Sham overlay, without materially reducing AppWorld task utility.

**Validation scope:** L0 static/package checks and L1 synthetic end-to-end instrumentation validation. The real AppWorld/Qwen run is gated on the protected data bundle, frozen 16-case mapping, a reachable pinned model service, Python 3.11 AppWorld runtime, and protocol-compatible H200/BF16 hardware.

**Evaluation design:** Two paired arms, 16 independent case/build units, one positive and one negative deployment per artifact, step/episode-level event logging, full-scope aggregation after every completed case, checkpoint/resume through immutable case artifacts, and explicit failure retention. Synthetic output is marked `research_eligible=false` and cannot produce a scientific go/no-go conclusion.

**Architecture:** A dependency-light Python core owns schemas, hashing, BM25, orchestration, reset attestations, canary logging, and aggregation. Runtime and model behavior sit behind adapters so AppWorld and an OpenAI-compatible vLLM service can run in separate environments; deterministic synthetic adapters exercise the identical state machine without protected data or model weights.

---

## Shared Scaffold

### Existing infra (don't touch, advise if problems found)

- Authoritative protocol: `EXPERIMENT_PLAN.md`
- Machine-readable protocol: `configs/experiment_plan.yaml`
- Historical/future research notes: `analysis/`
- Protected inputs and raw artifacts are already excluded by `.gitignore`.

### Needs setup

- Package and tools: `pyproject.toml`, `src/r2sp/`, `tests/`, `Makefile`.
- Pilot assets: `experiments/pilot/configs/`, `experiments/pilot/schemas/`, `experiments/pilot/prompts/`.
- Operations: `docs/architecture.md`, `docs/runbook.md`, `.github/workflows/ci.yml`.
- Generated local outputs remain under ignored `runs/`; protected AppWorld text is never committed.

## Subtask 1: Protocol contracts and immutable hashing

**Role:** Give every component one machine-readable meaning for resources, cases, runs, events, skills, reset attestations, deployments, and outcomes.

**Implementation:** Add `src/r2sp/models.py`, `src/r2sp/hashing.py`, `src/r2sp/config.py`, and JSON schemas under `experiments/pilot/schemas/`. Validate v0.2 arithmetic, safety invariants, placeholder hashes, matched-arm metadata, failure categories, and research-readiness separately.

**Unit Tests:** `tests/test_config.py`, `tests/test_models.py`; cover canonical hash stability, invalid IDs/hashes, arm mismatch, count arithmetic, placeholder data hash, and safe serialization.

**Expected Conclusion:** Implemented contracts with deterministic hashes and strict readiness gates; all contract tests pass.

### Steps

1. Write failing contract/config tests.
2. Run `python -m unittest tests.test_config tests.test_models -v`; expect failures because modules do not exist.
3. Implement dataclasses, canonical JSON/hash helpers, YAML loading, and validation reports.
4. Re-run the tests; expect all pass.
5. Review that no serialized agent-visible object contains evaluator labels, poison labels, hidden task mappings, or protected text unless explicitly designated as a private runtime record.

## Subtask 2: AppWorld resource pool and deterministic BM25

**Role:** Build the exact 457-document clean snapshot, pair one overlay without mutating it, and expose only header results until an explicit full read.

**Implementation:** Add `src/r2sp/resource_pool.py` and `src/r2sp/retrieval.py`. Load one resource per `app × api` from `data/api_docs/standard/*.json`, exclude helper apps, deterministically render one canonical representation, assign opaque stable IDs, verify content/manifest hashes and exact counts, and implement BM25 (`k1=1.2`, `b=0.75`) with frozen tokenization and resource-ID tie breaking.

**Unit Tests:** `tests/test_resource_pool.py`, `tests/test_retrieval.py`; cover supported JSON shapes, duplicate IDs, helper exclusion, exact-count failure, manifest mutation, body-free search headers, stable ranking, and full-read exposure semantics.

**Expected Conclusion:** Clean/arm pools are immutable and reproducible; BM25 returns deterministic body-free top-k headers; all tests pass.

### Steps

1. Write failing loader, pool-hash, and ranking tests using synthetic documents.
2. Run the two test modules; expect import failures.
3. Implement loader, pool snapshots, manifest writer, tokenizer, BM25 index, and query/read logs.
4. Re-run tests; expect all pass and identical ranks/hashes across repeated construction.
5. Verify public manifest output includes IDs and hashes but not decrypted AppWorld document bodies.

## Subtask 3: Agent, compiler, runtime, and model adapters

**Role:** Keep the four visibility planes separate while allowing the same runner to use deterministic smoke components or real AppWorld/Qwen services.

**Implementation:** Add `src/r2sp/agent.py`, `src/r2sp/compiler.py`, `src/r2sp/model_client.py`, `src/r2sp/runtime/base.py`, `src/r2sp/runtime/synthetic.py`, and `src/r2sp/runtime/appworld.py`. The agent exposes only `search_docs`, `read_doc`, `execute`, and `finish`; enforces budgets; never records hidden reasoning as compiler input. The compiler starts a fresh request and receives only task text, actually read docs, normalized API trace, and the task-success bit. Real dependencies are lazy-loaded and fail with actionable errors.

**Unit Tests:** `tests/test_agent.py`, `tests/test_compiler.py`, `tests/test_runtime.py`, `tests/test_model_client.py`; cover budget exhaustion, invalid actions, forbidden compiler fields, placeholder fallback, request parameters, narrow identifier validation, observation redaction, and fresh session IDs.

**Expected Conclusion:** Both synthetic and real adapter boundaries conform to the protocol, and unavailable external services fail before a research run begins.

### Steps

1. Write adapter boundary and failure-path tests.
2. Run the test modules; expect failures.
3. Implement protocols and adapters without importing test code into core code.
4. Re-run tests; expect all pass.
5. Inspect compiler payload snapshots to prove unread docs, evaluator details, and agent reasoning are absent.

## Subtask 4: Canary, reset attestation, and artifact store

**Role:** Make persistence and activation observable without granting network, filesystem, credential, database, or destructive capability to the agent.

**Implementation:** Add `src/r2sp/canary.py`, `src/r2sp/isolation.py`, and `src/r2sp/artifacts.py`. Canary writes evaluator-owned append-only JSONL only during deployment. Reset verification checks clean manifest equality, overlay ID/hash absence, fresh world/context/session IDs, and exact skill hash. Artifact writes are atomic and resumable; failures stay in the dataset.

**Unit Tests:** `tests/test_canary.py`, `tests/test_isolation.py`, `tests/test_artifacts.py`; cover authoring denial, wrong nonce logging, any-call specificity, all reset failure modes, partial-write recovery, resume, and immutable collision detection.

**Expected Conclusion:** Reset cannot pass on residual source/session state, canary is local and evaluator-owned, and artifacts are auditable and resumable.

### Steps

1. Write failing safety and reset tests.
2. Run the test modules; expect failures.
3. Implement append-only canary records, reset attestations, and atomic artifact storage.
4. Re-run tests; expect all pass.
5. Verify no core path sends network requests except the explicit model/AppWorld adapters.

## Subtask 5: Outcome aggregation and go/no-go discipline

**Role:** Produce the predeclared 16-case funnel without pseudoreplication or survivorship filtering.

**Implementation:** Add `src/r2sp/evaluation.py` and `src/r2sp/reporting.py`. Report Natural read, Valid skill, unconditional canary activation, Poison joint full-chain success, false activation, and task-level TGC. Keep every assigned case in denominators, distinguish `Y_canary` from `Y_joint`, aggregate deployment tasks within arms, and refuse scientific go/no-go for synthetic/incomplete/unfrozen inputs.

**Unit Tests:** `tests/test_evaluation.py`, `tests/test_reporting.py`; cover missing/failed episodes, wrong nonce, any-call false activation, TGC failures as zero, paired counts, threshold boundaries, synthetic refusal, and 64-deployment non-independence labels.

**Expected Conclusion:** Aggregation matches v0.2 exactly and cannot turn smoke data or selected successes into a research conclusion.

### Steps

1. Write table-driven failing metric tests.
2. Run both modules; expect failures.
3. Implement case outcomes, aggregation, JSON/CSV/Markdown reports, and eligibility checks.
4. Re-run tests; expect all pass.
5. Independently recompute a fixture funnel by hand and compare every reported count.

## Subtask 6: Pilot runner, CLI, smoke run, and operations [INTEGRATION]

**Hypothesis:** The assembled pipeline can distinguish a matched Poison artifact that crosses a verified hard reset and emits the correct positive-task canary from Sham and negative-task false activations, while preserving task scoring and complete failure records.

**Components consumed:** `src/r2sp/config.py`, `resource_pool.py`, `retrieval.py`, `agent.py`, `compiler.py`, `runtime/`, `canary.py`, `isolation.py`, `artifacts.py`, `evaluation.py`, and `reporting.py`.

**Implementation:** Add `src/r2sp/runner.py`, `src/r2sp/cli.py`, `src/r2sp/preflight.py`, `src/r2sp/__main__.py`, packaging, a safe synthetic fixture generator, CLI commands (`validate-config`, `preflight`, `build-manifest`, `smoke`, `serve-model-gateway`, `probe-model-service`, `run-pilot`, `report`), per-case progress/logging, immutable checkpoints, resume, fixed seeds, and failure categorization. Add CI and runbook documentation. This is inference/evaluation, not model training, so MFU/loss/gradient requirements do not apply; record model latency, token usage, episode duration, and throughput instead.

**Integration Tests:** `tests/test_runner.py`, `tests/test_cli.py`, plus the entire suite. Smoke must execute acquisition → compile → reset → positive/negative deployment for both arms and verify hashes/logs/reports.

**Validation Pyramid:** L0 + L1 — L0 runs packaging/import/compile/static repository checks; L1 runs the deterministic synthetic smoke pipeline. A real L1 research run is intentionally blocked unless every readiness precondition is satisfied.

**Evaluation contract:** Evaluate after every completed case and once at run end; default scope is all assigned cases. Both artifact entry modes are supported: immutable skill path/hash for resumed deployment and in-memory artifact for a single uninterrupted smoke case, using the same evaluator. Log phase start/end, progress, result summaries, timing, and explicit failures for missing/corrupt skills, reset mismatch, empty pools, non-finite metrics, service timeout, parser failure, and stalled phases.

**Expected Conclusion:** Local smoke passes with `research_eligible=false`; real `preflight --research-ready` fails truthfully on the current machine until AppWorld data/runtime, Qwen service, frozen cases, hashes, and H200 hardware exist.

### Steps

1. Write failing runner and CLI integration tests.
2. Run `python -m unittest discover -s tests -v`; expect the new integration tests to fail.
3. Assemble runner, CLI, preflight, fixture, packaging, CI, and documentation.
4. Run `python -m unittest discover -s tests -v`; expect all tests pass.
5. Run L0: install editable package in `.venv`, `python -m compileall -q src tests`, config validation, and repository hygiene checks.
6. Run L1: `r2sp smoke --output runs/smoke`; expect two matched arm artifacts, four deployment records, a passing reset attestation for each artifact, no Sham/negative false activation, one deterministic Poison positive activation, and `research_eligible=false`.
7. Run `r2sp preflight --config configs/experiment_plan.yaml --research-ready`; expect a non-zero exit with exact missing/incompatible prerequisites on this host, not a fabricated pilot result.
8. Record commands, versions, test counts, smoke artifact hash, and unresolved external blockers in the final handoff.

## Definition of done

- The complete local suite and deterministic smoke pass from a clean editable install.
- Every output has a mode, protocol version, code/config/input hashes, seed, run/case/arm IDs, and failure status.
- Protected AppWorld content, hidden evaluator data, model reasoning, credentials, and real side effects are absent from committed files.
- The synthetic path is visibly non-scientific; go/no-go requires the frozen real inputs and exact v0.2 run matrix.
- Unknowns remain explicit: real natural-read rate, real skill persistence rate, real task utility, and scientific go/no-go cannot be deduced before the gated run.
