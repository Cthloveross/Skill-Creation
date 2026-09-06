# Tau benign Skill batches — r8 / v2

This protocol narrows the active workflow to benign-only Skill creation and independent ordinary-task evaluation. It does not generate poison corpora or execute legacy canary deployments. Historical ASR records retain their original artifacts and replay evidence; independent verification requires the corresponding historical tools and source identity. Frozen r3/r5/r7 documents remain unchanged historical references, and their launch commands are not current v2 instructions.

The v2 constants, compiler, model client, outcomes, services, and official runtime/worker use separate `batch_*` modules. Existing legacy entrypoints and defaults remain unchanged. The r7 phase runner and standalone engineering-smoke execution/replay additions are outside this release. Image construction and model qualification are currently paused; this protocol specifies software behavior, not completed live qualification.

## Identity

The dataset is the complete 698-document, 97-task banking-knowledge snapshot at tau2-bench commit `fc0055dc4e0a316c3f83133267fbd6faaa770992`. Creation and evaluation each declare a strict v2 spec, unique batch ID, explicit item/trial list, pinned model identity, endpoint, seeds, and output root. Evaluation may use a different supported model; the identities remain separate.

The candidate primary model, pending independent runtime qualification, is `Qwen/Qwen3.8-Flash-Next-FP8` revision `236dfdf285828023ca3bcd3f37366c58a3469b13`. The diagnostic model is `Qwen/Qwen3.8-27B-FP8` revision `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`. There is no silent fallback. Context is 65,536 tokens.

## Creation

An arbitrary non-empty items list declares unique skill_id, official acquisition_task_id, corpus=benign, and seed. Each item gets a fresh runtime over original verified data. Each query fuses body-only BM25 Top-10 and embedding Top-10 with RRF k=60. It shows at most twenty unique documents without scores or channel identities; duplicate overlap and previously displayed documents are not backfilled. At most two queries expose at most forty unique documents. One successful selection chooses exactly ten distinct IDs from the cumulative displayed union and closes retrieval. The Agent selects ten previously displayed documents; only those full documents, the first user utterance, and sanitized public trace enter a fresh compiler. Hidden evaluator truth stays outside model input. Invalid compilation is recorded; generated Skills are never manually repaired.

Acquisition and compilation artifacts, timings, identities, and failures are recorded per item. generation-complete.json seals the batch and source archive. Creation ends without deployment. Scripted execution uses synthetic benign fixtures and is never model-behavior evidence.

## Evaluation

Sources identify sealed v2 creation roots and externally recorded completion hashes. Trials bind source_id, skill_id, official task_id, descriptive category, and seed. Multiple creation batches may be combined. Verify source seals and Skill hashes before any model call.

Each trial starts a fresh official process with only the current task, verified Skill, and ordinary tools. Retrieval, acquisition context, and canary tools are absent. Evaluation never reruns acquisition or compilation. Report utility and failed/skipped denominators; positive/negative labels do not imply attack metrics.

## Checkpoints and source

Specs, source archives, stage artifacts, and failures are immutable. Resume unfinished work only with matching stable spec/source/model identities and verified checkpoint hashes. Completed stages are skipped; recorded failures are not silently retried. Changed identities require a new batch.

A submitted job runs a deterministic source bundle containing required untracked v2 source and tests. Request, archive, manifest, and individual files are verified. Check the actual executing source again before publication. Fresh runtime assets are independently checked on resume; transient job/GPU/timing metadata does not replace stable provenance.

## Submission

submit_generation.sh --spec PATH and submit_evaluation.sh --spec PATH default to dry-run. Dry-run validates specs and source identity without starting a model or submitting a job, and explicitly reports unverified asset readiness. --submit validates runtime assets, persists the bundle and sealed request, invokes sbatch --parsable, prints the ID, and returns without monitoring. Creation never submits evaluation.

This document defines software behavior, not a completed r8 model experiment. See [WORKFLOW.md](../../../WORKFLOW.md) for operations and [RESULTS.md](../../../RESULTS.md) for evidence.
