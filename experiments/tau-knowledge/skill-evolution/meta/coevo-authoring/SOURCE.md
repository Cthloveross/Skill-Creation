# Authoring guidance provenance

The active Generator and SkillsBench Verifier prompts adapt public instructions from
CoEvoSkills commit `4380d4bff673dd6e1d58e5babeb2aaa0fe527119`:

- [Generator terminal prompt](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/prompt-templates/terminus-evolution-json.txt)
- [Skill creator meta-skill](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/meta_skills/skill-creator/SKILL.md)
- [Independent Verifier](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt)
- [Diagnosis prompt](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/evolution/prompt_templates/diagnosis_only.txt)

The active authoring guidance is embedded in `prompts/generator.md`, which is loaded
and hashed by the experiment. This source note is documentation, not an additional
model input or an instruction to execute the upstream meta-skill.

S0 remains one response with structural packaging only, without execution or
regeneration. In v4 evolution, the Generator directly operates the persistent task
environment, modifies its complete parent package, and explicitly submits the package
and actual public observation together. SkillsBench provides the official persistent
terminal; the bank adapter provides public banking tools and explicit user replies.
The independent Verifier receives only the submitted public snapshot. Fixed retrieval,
one-shot creation, restricted feedback and final safe-package selection remain explicit
experimental adaptations, described in [PROTOCOL](../../PROTOCOL.md).

Fresh SkillsBench oracle and independent evaluation import the author's unchanged
[CodexSkillOnly](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/codex_skill_only.py).
The original module, Apache-2.0 license and source hash are vendored under
`src/tau_skill_evolution/author/`. Its actual base class is supplied by
Harbor commit `3f28e5ce2acbff36d8b5df431e35e050ac13bef6`, verified from installed
package provenance and module hashes. We do not emulate Harbor or replace Codex
with a local model/tool loop.

`codex_runtime.py` adapts installation, provider configuration and environment exec
to the existing fresh Docker episode. It invokes the author's Skill staging,
read-only checks and before/after digest guard, then the actual Codex CLI. NoSkill
uses the same Harbor Codex base with no Skill instruction or mount. The CLI model alias maps explicitly to the configured Bedrock model; current configs
select `openai.gpt-5.4`.
CLI version/hash and common execution budgets are bound to each new run.

The package is mounted read-only at both `/bundle` and the author's Skill path.
The original installer cannot chmod a read-only mount. Only its exact chmod
failure is handled by separately attesting both kernel mount options, all file
hashes, a nonempty manifest containing `SKILL.md`, and absence of symlinks.
Writable mounts and every other setup failure are rejected. The author module,
barrier, staging and pre/post execution digest guard remain unmodified; the
adaptation and original setup failure are recorded in private execution evidence.

`codex_provider.py` buffers and journals provider responses before delivering SSE
to Codex. The task receives only a credential-free Unix socket relay, preserving
network-disabled task environments. Native response/tool payloads are preserved;
the host pins model, reasoning and output caps, disables POST retries, and closes
model access before official grading. These are explicit transport adaptations,
not byte-for-byte reuse of the entire author's launcher. The offline Docker/CLI
integration uses simulated model responses and is never reported as a real model
completion rate. Real Bedrock compatibility requires a valid-key smoke.

The pinned CLI uses ordinary Responses summarization for custom-provider automatic
context compaction, rather than `/responses/compact`. Its trigger is set to 85%
of the executor input admission budget, with the full native request still
journaled. A real CLI/Docker check with simulated Responses exercised the summary
request and matched CLI/provider usage; it does not establish real Bedrock
reasoning-item compatibility. Upstream implementation:
[provider capability](https://github.com/openai/codex/blob/rust-v0.160.1/codex-rs/model-provider/src/provider.rs#L462),
[turn dispatch](https://github.com/openai/codex/blob/rust-v0.160.1/codex-rs/core/src/session/turn.rs#L1494).

The seven coarse failure categories are ported from the author's
[`_safe_gt_failure_categories` controller](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py).
Test source, names, assertion values and full diagnoses stay on the audit side.
The upstream Apache-2.0 license is retained in [licenses](../../licenses/CoEvoSkills-LICENSE).

## Historical adapter notes (v3)

The following provenance describes the retired observation/debug adapter, not the v4
learning interface or runnable checkpoints. Historical evidence remains in its original
paths; current behavior is specified by PROTOCOL.

Coarse feedback is not the author's only source of evidence. The pinned
[Generator terminal prompt](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/prompt-templates/terminus-evolution-json.txt)
allows supplied inputs, public project metadata and ordinary runtime diagnostics;
it requires running the Skill, writing fixes back into the package and rerunning it.
Our earlier private-workspace restriction omitted preceding public traces and outputs.
It should not be described as denying every actual SkillsBench input: the Docker helper
image derives from the original task image, so inputs baked into that image may remain
readable even though no separate input mount is added. What was absent was the preceding
execution evidence and direct control of the formal task environment.

The corrected adapter exposes the preceding trace at `/bundle/trace.json` and debug
observations at `/work/observations/<hash>/trace.json` with copied public artifacts.
Verifier categories remain restricted; public observations do not include hidden tests,
gold, grader diagnostics, private bank state or other roles' private conversations.
Repeated editing, local checks and debug runs are one revision attempt, within the same
120-turn Generator budget and revision timeout. Only explicit submission seals a package;
debug runs are not official scores or extra content versions. M15/K5 and the S0 creation
ban on execution/self-tests remain unchanged. Each debug run also consumes its executor
episode budget and API usage; unchanged budget parameters do not imply equal total compute.
Delegating debug execution to a fresh agent
still differs from the author's direct, persistent task-environment interaction; this
change restores public evidence without asserting equivalent outcomes. Offline regression
passed (944 tests; 54 optional checks skipped), and two real Docker observation checks
passed. [Acceptance evidence](../../archive/runs/readiness-evolution-observation-20261006-001/acceptance.json)
records the scope, hashes and independent review. Paid-model compatibility and utility
gain remain `NOT_MEASURED`; historical results do not establish the new behavior.

The paper and pinned release differ on feedback detail. The currently published
[paper, section 3.3](https://arxiv.org/html/2604.01687#S3.SS3) describes surrogate
feedback containing failed checks, root causes and actionable suggestions. The pinned
release's [`_build_surrogate_feedback`](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py#L2013)
explicitly withholds the full diagnosis and projects failed test names into seven
coarse labels. Our feedback follows this release contract, not the paper's detailed
diagnostic formulation. Empty or inappropriate labels observed in the banking
adaptation remain a real limitation; authorship of the mapping does not validate it
for new task domains.

The pinned controller also locks a valid surrogate suite and its
[diagnosis worker](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/evolution/independent_verifier.py#L569)
backs up and restores tests after a read-only diagnosis. A recognized semantic false
negative has no direct unlock route in that path; oracle failure triggers escalation.
Thus the false-negative deadlock observed locally is not, by itself, evidence that
we omitted an upstream semantic-repair capability. Adding evidence-based semantic
correction would be an explicit method extension. Our host harness, program-error
repair limit, obligation checks and AST novelty guard are additional local rules;
the author's Verifier uses a fresh model session in the task container, while ours
uses a separate container with public snapshots.

Two further differences affect budget and result comparisons. The pinned release's
[r15 counter](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py#L802)
counts surrogate failures and Verifier/checklist interventions, while local M15
counts Skill revision attempts and additionally imposes 120 Generator turns. Both
use a context proportion cap, not cumulative billed tokens, but local admission
reserves output and estimates the complete request. The author
[saves the highest official reward snapshot](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py#L2124)
and may roll back to it or retain its known score at termination; we select the
successful package or last safe package and report its independent fresh evaluation.
This does not establish that the author's true success probability cannot regress,
nor does it explain away a local mismatched task obligation.

No task-specific gold answers, upstream canonical tests, released Skills, or hidden oracle
diagnostics are included in Generator input. Its own editing conversation persists
within the same task and frozen-base identity; no other role's conversation is inherited.
