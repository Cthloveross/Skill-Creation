# R2SP Pilot Runbook

## 1. Core development environment

The dependency-light core and synthetic smoke support Python 3.10+. The real AppWorld environment
requires Python 3.11.

```bash
make setup
make check
make smoke
```

Expected fresh v0.3 smoke conclusion: `decision=NOT_ELIGIBLE` and `research_eligible=false`. This is
a wiring test, not pilot evidence. Never relabel an existing v0.2 smoke directory as v0.3; use a new
output root.

`r2sp smoke` uses a checked-in scripted client. It deliberately chooses the fixture's first five
retrieved IDs and emits checked-in fixture skill text; it does not measure model choice or model
skill generation. A successful scripted smoke must not be described as a Qwen run.

## 2. Prepare target-specific locks

The repository provides direct dependency inputs only. Generate complete transitive locks on the
actual Python 3.11 AppWorld host and H200/CUDA model-service host; do not generate them on an
incompatible workstation and do not replace them with hand-written placeholder files.

```bash
uv pip compile --python 3.11 --generate-hashes requirements/appworld.in -o requirements/appworld.lock
uv pip compile --python 3.11 --generate-hashes requirements/model-service.in -o requirements/model-service.lock
```

Review and commit the resolved locks before changing `protocol.runner_ready` to `true`. Re-run the
preflight after any dependency, CUDA, model, data, prompt, retriever, or case change.

## 3. Prepare protected AppWorld data

Keep the AppWorld root, clean manifest, private cases, overlay attestation, and run output tree
outside this repository. Every one of these runtime paths must be absolute, and its tree must be
disjoint from the repository; `output_root: runs` is intentionally rejected. Set the official
AppWorld root before importing AppWorld:

```bash
export APPWORLD_ROOT=/absolute/external/appworld-root
```

Build the clean public manifest from the pinned standard API docs:

```bash
r2sp build-manifest \
  --source "$APPWORLD_ROOT/data/api_docs/standard" \
  --expected-count 457 \
  --output /absolute/external/frozen/clean-manifest.json
```

Validate the private 16-case bundle and emit the body/trigger/nonce-free paired schedule:

```bash
r2sp freeze-pilot \
  --cases /absolute/external/frozen/cases.json \
  --output /absolute/external/frozen/public-schedule.json
```

The private bundle must use the checked-in JSON schema and the pinned Qwen tokenizer/revision. The
Sham/Poison token counts must be precomputed with that tokenizer and differ by at most 5%.

The original questions have two deliberately separate sources:

- Research pilot: the private bundle supplies three frozen AppWorld Train task IDs per case. Before
  execution, the runner verifies each ID is in the installed frozen Train split and that the frozen
  instruction exactly equals the newly created world's `world.task.instruction`.
- Synthetic smoke: `src/r2sp/fixtures.py` supplies repository-owned fixture instructions. These are
  not AppWorld questions and can never support research eligibility.

Qwen, BM25, and the Sham/Poison overlay do not generate or rewrite either kind of question. Keep the
task source, task ID, and instruction hash in run provenance; do not expose private instructions in
public reports.

Before writing a research run, the runner hashes the installed AppWorld package and distribution
metadata, base databases, standard API docs, train split, all 48 selected task trees, and executable
Python bytecode. It disables new bytecode-cache writes while AppWorld executes and repeats the
snapshot before completion. The two snapshots must match. A transient change fully reverted between
those probes is not detectable, so formal provisioning must also keep these trees read-only or
otherwise immutable for the whole run. This binds observed bytes; it does not prove official origin.

### 3.1 Acquisition Top-5 contract

Protocol v0.3 keeps deterministic global BM25 at `top_k=10`. Search results contain headers only.
During acquisition, Qwen receives a fifth tool, `select_docs(resource_ids)`, and the runner enforces
this state transition:

1. one or more successful searches append unseen IDs to an ordered candidate union;
2. Qwen submits exactly five unique IDs, all already present in that union;
3. the valid selection is committed once and cannot be changed;
4. reads before selection or outside the selected set are rejected without touching the retriever;
5. no further search is accepted after selection, and execution/successful finish requires a valid
   selection.

`select_docs` exposes no document body and does not itself count as exposure. The maximum unique read
budget is five. Deployment omits `select_docs` and uses the four-tool compatibility catalog because
the selection intervention is acquisition-only. Persist candidate rank/ID, selected ID/order, full
reads, and invalid attempts in the private run trace.

Do not confuse the three different values: BM25 candidate `top_k=10`, model document
`model_select_k=5`, and generation token sampling `top_k=20`.

## 4. Model service declarations and probes

This section is the frozen research profile. It is not a generic minimum requirement. The audited
local RTX 6000 server cannot run this BF16/TP=1 profile; see
[GPU compatibility](gpu-compatibility.md) for a separate FP16 multi-GPU instrumentation trial that
must remain research-ineligible.

Serve `Qwen/Qwen3.8-27B` revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` in BF16 with vLLM `0.28.0`, prefix caching disabled,
and no server-side sessions. Use one H200, one active sequence, language-model-only mode, the
`qwen3` reasoning parser, and `qwen3_coder` auto tool parser. These parsers are required for the
runner's hidden-reasoning and dynamic acquisition/deployment tool contracts. The loopback metadata gateway must expose
model ID, revision, dtype, generation settings, serving settings, runtime version, and hardware. It
first requires a real matching upstream model record, then adds caller-supplied declarations.
Preflight checks those declarations against the frozen configuration; a model ID alone is
insufficient.

These declarations are operational claims from a trusted provisioning boundary. The gateway does
not verify them against the vLLM process. They are not cryptographic proof of loaded weight bytes,
the process image, or effective launch flags. For a
loopback URL, preflight separately probes `nvidia-smi` for a visible H200, but it intentionally does
not inspect the runner Python environment for vLLM because the model service may use a separate
environment. The binding between the declared revision and the weights actually loaded by the
service is **unknown** in this implementation and must be controlled during provisioning.

The corresponding vLLM serving flags are:

```bash
vllm serve Qwen/Qwen3.8-27B \
  --revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --tokenizer-revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 1 \
  --max-model-len 65536 \
  --max-num-seqs 1 \
  --language-model-only \
  --no-enable-prefix-caching \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --host 127.0.0.1 \
  --port 18001
```

In a second process, place the checked-in gateway on port 18000. It proxies model calls to vLLM and
augments only an existing matching `/v1/models` record:

```bash
r2sp serve-model-gateway \
  --config configs/experiment_plan.yaml \
  --backend-url http://127.0.0.1:18001 \
  --host 127.0.0.1 \
  --port 18000 \
  --timeout-seconds 300
```

The resulting `/v1/models` record places these declarations under `metadata`. If vLLM uses
`--api-key`, store that value only in the runtime contract's named environment variable
(`R2SP_MODEL_API_KEY` in the example). The gateway and preflight forward the same explicit
authorization value; neither path falls back to `OPENAI_API_KEY`. Example record:

```json
{
  "id": "Qwen/Qwen3.8-27B",
  "metadata": {
    "revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
    "dtype": "bfloat16",
    "generation": {
      "enable_thinking": true,
      "preserve_thinking": false,
      "reasoning_effort": "xhigh",
      "temperature": 1.0,
      "top_p": 0.95,
      "top_k": 20,
      "max_output_tokens_per_turn": 8192
    },
    "runtime": {
      "max_model_len": 65536,
      "prefix_caching": false,
      "server_sessions": false,
      "tokenizer_revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
      "tensor_parallel_size": 1,
      "pipeline_parallel_size": 1,
      "max_num_seqs": 1,
      "language_model_only": true,
      "enable_auto_tool_choice": true,
      "tool_call_parser": "qwen3_coder",
      "reasoning_parser": "qwen3"
    },
    "vllm_version": "0.28.0",
    "gpu": "NVIDIA_H200_141GB"
  }
}
```

### 4.1 Live-model synthetic full chain

After the service passes its probes, run the real client through acquisition, fresh-context skill
compilation, hard reset, and fresh positive/negative deployments:

```bash
r2sp run-model-smoke \
  --output runs/top5-qwen-YYYYMMDD \
  --config configs/experiment_plan.yaml \
  --project-root "$PWD" \
  --base-url http://127.0.0.1:18000/v1 \
  --model-id Qwen/Qwen3.8-27B \
  --revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --timeout-seconds 900 \
  --max-model-len 65536 \
  --max-agent-turns 16
```

The command refuses non-loopback endpoints and verifies model identity, tokenization, structured
tool parsing, and exact-five selection parsing before creating the output tree. It records the
declared revision and service response hash, but those are not cryptographic proof of loaded weight
bytes. The fixture tasks and runtime remain synthetic, so this mode is permanently
`research_eligible=false`, regardless of task or canary outcomes. Never reuse an output path to
select a favorable stochastic result.

The completed 2026-08-30 RTX 6000/FP16 example, including the exact task source, selected IDs,
generated skills, hashes, outcomes, and evidence limitations, is recorded in
[`run-records/2026-08-30-top5-smoke.md`](run-records/2026-08-30-top5-smoke.md).

## 5. Strict preflight

Copy `experiments/pilot/configs/runtime.example.yaml` outside the repository and replace every
absolute placeholder. `preflight --runtime-config` validates the complete runtime contract,
including research mode, safe logging, resume semantics, absolute external paths, loopback model
URL, and exactly two absolute lockfile paths. Explicit preflight flags still override the validated
runtime values for targeted diagnostics. Then run:

```bash
r2sp preflight \
  --config configs/experiment_plan.yaml \
  --runtime-config /absolute/external/runtime.yaml \
  --research-ready
```

Every required check must pass. A warning may document a non-protocol operational concern; a failed
required check blocks `run-pilot` before it creates a run directory or starts an AppWorld task. A
pass on the model checks means that endpoint declarations are internally consistent and, for
loopback, that the required GPU is locally visible. It does not prove the identity of loaded weight
bytes.

## 6. Run and inspect

```bash
r2sp run-pilot \
  --config configs/experiment_plan.yaml \
  --runtime-config /absolute/external/runtime.yaml

r2sp report \
  --run-directory /path/reported/by/run-pilot \
  --format markdown \
  --expected-complete-sha256 COMPLETE_HASH_FROM_RUN_PILOT
```

The runner writes immutable per-phase records under the configured absolute external output root.
An explicitly supplied output directory is also rejected if it overlaps either the repository or
the AppWorld tree. On restart, completed artifacts are verified and reused. A phase that has a start
record but no completion is retained as an interrupted failure; it is not silently rerun, which
prevents duplicate canary events and selected-success bias.

After the final arm is durable, the runner writes `finalization-start.json` before recomputing the
AppWorld runtime snapshot and producing reports. A snapshot mismatch writes a permanent
`interrupted.json` marker. Any run with finalization started but no valid `complete.json` is also
non-resumable: restoring changed bytes or deleting a completion marker cannot turn an uncertain
finalization into research evidence. Start a new output root after resolving the underlying issue.
The `complete_hash` returned by `run-pilot` or `smoke` must be retained outside the output tree and
passed to `report`; it is the trust root that prevents rewriting both artifacts and internal hashes.

For every v0.3 acquisition, inspect the candidate union, exact-five selection, selected reads, task
source/ID/instruction hash, generated `SKILL.md` hash, and compiler-input commitment. Absence of any
one of these means the run is incomplete; it cannot be repaired by assigning a new version label.

## 7. Failure handling

- Do not delete a failed case to improve the denominator.
- Do not edit an artifact in place; use a new output root after an intentional protocol/input change.
- Only host outage or corrupt input can justify a rerun, and the reason must be retained.
- A reset mismatch, stale canary binding, invalid skill, missing score, or non-finite score is a
  recorded failure, never a success.
- Never publish raw run bundles: they can contain protected AppWorld content and generated skill
  text.
- Never merge v0.2 and v0.3 outputs as one protocol population. v0.2 allowed up to 32 reads without
  an exact-five selection action; v0.3 requires the acquisition selection trace and a five-read cap.
