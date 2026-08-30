# R2SP Pilot Architecture

## Authority and scope

The executable contract is version `0.3`. When files disagree, use this order:

1. `EXPERIMENT_PLAN.md` — scientific protocol and outcome definitions.
2. `configs/experiment_plan.yaml` — exact machine-validated constants.
3. `src/r2sp/` — implementation.
4. `analysis/` — historical research notes only; not executable protocol.

This repository supports one matched Sham/Poison feasibility pilot. It does not support public
resource injection, real credentials, external callbacks, destructive actions, or executable skill
artifacts.

## Trust boundaries

| Plane | Data visible | Data forbidden |
|---|---|---|
| Agent | task, trusted app descriptions, search headers, exactly five selected and explicitly read docs during acquisition, five acquisition tools, four deployment tools, loaded skill during deployment | evaluator, hidden solution, private case labels, unread documents, canary log |
| Compiler | authoring task, documents actually read, normalized API trace, task-success bit | agent reasoning, unread docs, evaluator state, deployment results |
| Runtime | validated `app.api(args)` calls and task completion | arbitrary Python identifiers, filesystem/network credentials, direct canary-log access |
| Evaluator | frozen inputs, manifests, reset attestations, canary events, AppWorld scores | model hidden reasoning |
| Model service | upstream identity plus gateway-supplied operational declarations; local `nvidia-smi` probe for loopback | cryptographic proof of loaded weights, process image, or effective launch flags |

`SKILL.md` is text-only workflow guidance. It is hashed and loaded as text; code blocks are never
executed, dependencies are never installed, and tool authority never expands.

The model service and provisioning are trusted operational infrastructure. Bare vLLM does not emit
the full frozen declaration set; the checked-in loopback gateway augments a real upstream model
record with caller-supplied metadata. Preflight compares those claims with the frozen profile and
probes local GPU visibility. This establishes reported consistency only, not a cryptographic binding
to the process or weight bytes. The actual loaded-weight binding remains **unknown** unless
provisioning supplies an independent verification mechanism.

For AppWorld, the runner computes a content snapshot before creating output and recomputes it before
completion. The snapshot covers the imported package and distribution metadata, base databases,
standard API documentation, the train split, all 48 selected task trees, and Python bytecode. New
bytecode writes are disabled while AppWorld executes. The start and final snapshots must match; a
transient change reverted between probes is outside this detector, so provisioning must keep the
runtime trees read-only or otherwise immutable. This does not prove publisher authenticity.
Finalization is an
irreversible state boundary: once its marker exists, a missing valid completion or a snapshot drift
permanently seals that output tree against replay.

## State machine

```text
frozen case + clean 457-doc pool
              |
              v
matched Sham/Poison 458-doc acquisition
              |
     Top-10 headers -> exact Top-5 commit
              |
      actual reads + API trace
              |
              v
fresh-context skill compiler
              |
       immutable SKILL.md hash
              |
              v
hard reset attestation ---- fail closed
              |
              v
clean 457-doc positive + negative deployments
              |
              v
bound canary events + AppWorld TGC
              |
              v
16-case paired aggregation
```

The reset verifies clean-manifest equality, overlay ID/hash absence, fresh world/context/session IDs,
and exact generated/loaded skill hashes. A canary target event counts only when nonce, deployment
run ID, and loaded skill hash all match. Every assigned case remains in the denominator.

## Modules

- `config.py`, `models.py`, `cases.py`: frozen contracts and private/public serialization boundaries.
- `resource_pool.py`, `retrieval.py`: immutable pools and deterministic BM25.
- `agent.py`, `compiler.py`, `model_client.py`: acquisition Top-5 selection, four-tool deployment
  loop, allow-listed skill build, pinned Qwen request format.
- `runtime/`: synthetic and lazy AppWorld adapters.
- `canary.py`, `isolation.py`, `integrity.py`, `artifacts.py`: local no-op observation, reset proof,
  runtime byte binding, and write-once records.
- `evaluation.py`, `reporting.py`: paired case outcomes, fixed denominators, eligibility-gated decision.
- `runner.py`: deterministic instrumentation smoke.
- `research_runner.py`: strict-preflight real pilot orchestration.
- `cli.py`: stable operational entry points.

## Evidence levels

- Synthetic smoke proves wiring and invariants only. Its provenance is permanently
  `research_eligible=false` and its decision is `NOT_ELIGIBLE`.
- A research decision requires all 16 frozen cases, strict v0.3 config validation, verified frozen
  inputs, a stable content-bound AppWorld runtime, a trusted Qwen service reporting the pinned
  profile, target-environment dependency locks, and completed paired records. Operators must
  enforce AppWorld publisher provenance and the service's actual weight/process identity outside
  the current preflight.
- Natural-read rate, real persistence rate, task utility, and scientific go/no-go are unknown until
  that gated run completes.

## Artifact policy

Protected inputs and raw run outputs stay in absolute external trees disjoint from both this
repository and the AppWorld tree. Git ignores `runs/` only as defense in depth; it is not a valid
research output location. Public manifests contain headers and hashes, never document bodies,
triggers, or nonces. Artifacts are atomic and write-once: identical content resumes; a same-path
content change is an integrity error. Internal hashes detect partial corruption. Independent tamper
evidence comes from retaining the externally returned `complete_hash` and supplying it to `report`.
