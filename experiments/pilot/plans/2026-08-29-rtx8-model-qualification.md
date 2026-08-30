# RTX 6000 Qwen3.8 Model-Service Qualification Implementation Plan

**Goal:** Qualify the strongest model that preserves the R2SP agent/compiler contract on no more
than eight local Quadro RTX 6000 GPUs without changing the frozen H200 protocol.

**Experiment directory:** `experiments/pilot/`

**Hypothesis:** `Qwen/Qwen3.8-27B` served in FP16 through vLLM 0.28 can use the SM75
Triton/FLA fallback and satisfy the tokenizer, reasoning, tool-call, agent, compiler, and staged
context checks on an eight-GPU engineering profile.

**Validation scope:** L0 profile/schema/unit checks; L1 same-architecture small-model kernel probe;
then full-model startup and 16,384, 32,768, and 65,536-token service probes. Every result is
non-research until a separately frozen protocol is approved.

**Evaluation design:** Evaluate after every serving profile and context-length stage. Use the shared
`r2sp probe-model-service` evaluator against both a freshly started endpoint and a restarted
endpoint. Log phase start/end, per-GPU peak memory, startup time, time to first token, output rate,
all probe checks, and failures. Abort a stage on startup failure, OOM, non-finite output, malformed
reasoning/tool calls, an empty response, or a silent interval above the configured timeout.

**Architecture:** Preserve `configs/experiment_plan.yaml` as the frozen H200/BF16 v0.2 reference.
Add a separate RTX engineering profile and loopback launcher. Prefer the existing Qwen3.8-27B;
fall back to Qwen3-32B only if the Qwen3.8 hybrid-attention path fails qualification.

---

## Shared Scaffold

### Existing infra (don't touch, advise if problems found)

- Frozen protocol: `configs/experiment_plan.yaml`
- Model contract client: `src/r2sp/model_client.py`
- Loopback metadata gateway: `src/r2sp/model_gateway.py`
- Integration probe: `src/r2sp/model_probe.py`
- GPU audit and current four-card draft: `docs/gpu-compatibility.md`

### Needs setup

- A dedicated external package/model cache with at least 100 GiB free.
- A separate vLLM 0.28 environment; never add GPU runtime packages to the core `.venv`.
- An RTX engineering profile that cannot be mistaken for the H200 research profile.

## Subtask 1: RTX engineering profile

**Role:** Represent the model choice and GPU topology without weakening the frozen protocol.

**Implementation:** Add a separate profile under `experiments/pilot/configs/` with the pinned
Qwen3.8 revision, FP16, up to eight RTX 6000 GPUs, explicit TP/PP, one sequence, loopback ports,
Triton attention, disabled prefix caching/MTP, and staged context lengths. Extend validation only
for this non-research profile; do not generalize the H200 research gate.

**Unit Tests:** Reject more than eight GPUs, BF16 on SM75, unpinned revisions, non-loopback hosts,
prefix caching, and any `research_eligible=true` claim.

**Expected Conclusion:** "RTX profile implemented and validation tests pass."

### Steps

1. Write failing profile-validation tests.
2. Add the isolated RTX profile and parser.
3. Run targeted tests and the complete core suite.
4. Review the diff; commit only after explicit user approval because the worktree is shared/dirty.

## Subtask 2: Reproducible launcher and telemetry

**Role:** Make startup, shutdown, topology, and measurements repeatable.

**Implementation:** Add a launcher that validates free GPUs and ports, records `nvidia-smi` and
topology, starts vLLM on loopback, waits for readiness, captures logs and per-rank peak memory, and
terminates only its own process group. Support TP4/PP1, TP4/PP2, and TP8/PP1 candidates.

**Unit Tests:** Cover command construction, GPU ordering, occupied ports, process ownership,
timeouts, partial startup, and log redaction.

**Expected Conclusion:** "Launcher implemented and deterministic command/cleanup tests pass."

### Steps

1. Write failing command and lifecycle tests.
2. Implement the launcher without importing test or validation code.
3. Run targeted tests and static checks.
4. Review the diff; commit only after explicit user approval.

## Subtask 3: Full model-service qualification [INTEGRATION]

**Hypothesis:** The pinned Qwen3.8-27B FP16 service can satisfy the complete project contract on
the local RTX server, with an eight-GPU profile used only when it improves stability or capacity.

**Components consumed:** RTX profile, launcher/telemetry, `src/r2sp/model_probe.py`,
`src/r2sp/model_gateway.py`, and `src/r2sp/model_client.py`.

**Implementation:** First run a same-architecture small-model smoke to exercise SM75 GDN/Triton.
Then download the pinned 27B model to the approved external cache, benchmark TP4/PP1, TP4/PP2, and
TP8/PP1 where supported, select the smallest reliable topology, and run staged context probes.

**Integration Tests:** Endpoint identity/tokenization, ordinary generation, hidden reasoning,
forced tool call, four-tool agent loop, compiler output, restart behavior, and gateway declarations.

**Validation Pyramid:** L0 + L1 mandatory. L0 checks configuration, isolation, locks, and command
construction. L1 records actual startup/probe results and per-GPU memory at 16K, 32K, and 65K.

**Evaluation contract:** Run the full probe at every stage and after restart, using one shared probe
core. Print phase start/end, progress, result and efficiency summaries. Treat missing weights,
startup/restore failure, OOM, parser failure, non-finite output, or timeout as an observed failure;
do not silently retry or relabel it.

**Expected Conclusion:** Either a measured Qwen3.8-27B RTX serving profile is selected, or the same
qualification is repeated with Qwen3-32B and the model change is explicitly versioned as a new
non-comparable protocol.

### Steps

1. Run the same-architecture small-model FP16 kernel smoke on one SM75 GPU.
2. Verify the approved cache has at least 100 GiB free and download pinned model files.
3. Start at 16,384 tokens and run the complete integration probe.
4. Benchmark eligible TP/PP layouts using identical prompts and generation settings.
5. Repeat at 32,768 and 65,536 tokens only after the previous stage passes.
6. Restart the selected service and repeat the complete probe.
7. Record measured memory, latency, throughput, failures, exact versions, and the final conclusion.
8. Review all artifacts; commit only after explicit user approval.

## Qualification result (2026-08-30)

The integration hypothesis passed on `0,6,1,3,2,4,5,7` with TP=2/PP=4, FP16, vLLM 0.28.0,
and the pinned Qwen3.8-27B revision. The full service probe passed 6/6 at 16,384, 32,768, and
65,536 tokens. Real chat prompts of 30,012 and 56,012 tokens completed without OOM. See
`docs/gpu-compatibility.md` for measured time, memory, backend, and packaging details.

Subtasks 1 and 2 remain implementation work: this run used a disposable environment and manual
commands, so a checked-in RTX profile and lifecycle/telemetry launcher have not been claimed as
complete. Qwen3-32B fallback qualification is unnecessary because the primary model passed.
