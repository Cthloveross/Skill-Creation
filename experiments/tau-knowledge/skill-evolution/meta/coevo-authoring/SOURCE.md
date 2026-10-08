# CoEvoSkills sources and migration contract

All author references in this experiment are fixed to CoEvoSkills commit
`4380d4bff673dd6e1d58e5babeb2aaa0fe527119`; Harbor is fixed to
`3f28e5ce2acbff36d8b5df431e35e050ac13bef6`. This record distinguishes reused
implementation from local adapters. The active method is specified in
[PROTOCOL](../../PROTOCOL.md), with τ v4 and SkillsBench v6 contracts kept separate.

## Reused implementation

SkillsBench v6 executes the author's
[IndependentVerifier](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/evolution/independent_verifier.py),
[SelfVerifier](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/evolution/self_verifier.py),
their agent, parser and conversation dependencies, and the original
[independent-verifier](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt)
and [diagnosis](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/evolution/prompt_templates/diagnosis_only.txt)
prompts. The code and prompt bytes are preserved under
`src/tau_skill_evolution/author/coevo/`; the author's Skill schema validator is
`author/skill_schema.py`. `author/VERIFIER_SOURCE.json` records each original path
and SHA256. Namespace package layout omits eager upstream aggregate initializers;
it does not rewrite implementation or prompt bodies. Runtime validates those hashes.
Run identity binds the manifest and every vendored resource, including the original
skill-creator Markdown, HTML, scripts and prompt files.
V6 config no longer selects the retired local `verifier-skillsbench.md` prompt.

`author_controller.py` connects the existing official task Runner to the author's
environment interface and binds its LLM factory to per-role provider clients,
using the transport primitives in `author_verifier.py`. The original agent has a fresh model context and terminal access in the
**same persistent task container** as Generator. Frozen documents are staged as
public background. Model and terminal operations use the existing Journal, and
raw results are archived before parsing. Known diagnosis errors are recorded without
replacing a measured surrogate failure; fatal authentication, UNKNOWN and cleanup
conditions stop the chain. No private grader or hidden result is exposed to this agent.

Fresh oracle and independent evaluation execute the unchanged
[CodexSkillOnly](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/codex_skill_only.py)
with its actual pinned Harbor Codex base and native Codex CLI. The source, license
and hash are recorded in `author/SOURCE.json`; CLI and companion binaries are pinned
by configuration. NoSkill uses the same Codex base without the task Skill. The
upstream Apache-2.0 license is retained under `licenses/` and `author/`.

## Generator guidance and feedback

`prompts/generator.md` adapts the author's
[terminal evolution prompt](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/prompt-templates/terminus-evolution-json.txt)
and [skill-creator](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/meta_skills/skill-creator/SKILL.md)
guidance: reusable functions, complete execution entry points, parameter derivation,
file organization, self-reflection and writing reusable fixes into the package.
This prompt is locally adapted; it is not the original controller or an invocation
of a separate meta-skill. Creation instructions prohibit self-testing and repeated S0
creation, while evolution explicitly permits completing the task and observing results.

The released controller's
[`_build_surrogate_feedback`](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py#L2013)
projects failures to coarse categories and withholds full diagnosis. Generator receives
that restricted feedback, oracle pass/fail, its own public schema errors and progress
checklist, and its own terminal observations. Test code, names, exact assertions,
tracebacks, complete diagnoses and official scores remain on the audit/host side.
The release also derives broad GT failure dimensions and implicated public schema
fields; this experiment retains a boolean oracle and does not forward those GT-derived
fields. Public candidate schema and checklist feedback do not come from hidden grading.
The [paper section 3.3](https://arxiv.org/html/2604.01687#S3.SS3) describes more detailed
feedback, so this is the fixed release contract rather than a claim that paper prose
and published code are identical. Bank-domain category usefulness remains a limitation.

## SkillsBench v6 controller alignment

The active SkillsBench adapter directly invokes the author's
[evolution controller](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py).
It invokes `HarborTerminus2Evolution.setup/run` without replacing its execution, verification, intervention, or best-selection loop. The original dependency closure and skill-creator are vendored byte-for-byte; Harbor task scheduling is not imported. The retired locally ported SkillsBench state machine is removed; the shared engine now handles only the bank contract.

- A valid surrogate suite is locked on ordinary task failure. Diagnosis preserves
  its bytes. Failed initial generation stays unlocked; an invalid suite cannot be
  silently treated as a permanent valid lock. Valid GT failure causes Generator
  editing/execution followed by a new adversarial verifier generation.
- r15 is a cumulative count of surrogate and Verifier interventions, including the
  first incomplete checklist. It is not a fifteen-revision limit. Missing/invalid
  Skill schema has two repair opportunities and a third-failure stop outside r15.
  A second incomplete checklist is advisory and may proceed to GT, as in the release.
- The active skills agent defaults to 120 effective episodes. Parsed executable
  terminal/submission responses count once; pure Skill tools and parse errors do not.
  Raw model responses, actual POSTs, commands, submissions and revision attempts are
  separately reported. Invalid drafts never become a version without safe submission.
- K5 limits normal GT interventions. Infrastructure failures refund that intervention;
  the consecutive infrastructure counter resets after a valid GT result. Cap-final and
  post-final GT calls remain separately recorded. The source has reachable six-call
  terminal paths, so K5 is not advertised as a strict total-call cap.
- The author's launch script sets `timeout_multiplier=5` and `run_exp --timeout 7200`.
  `run_exp` applies the latter as a hard subprocess wall deadline, not as an agent
  timeout to be multiplied. V6 starts a persistent absolute learning deadline before
  creating the task episode, including Generator, Verifier and learning GT; retrieval,
  single-response S0 and additional independent evaluations are separate stages.
  Commands use task-agent timeout times five, capped at 900 seconds; Verifier generation
  and diagnosis retain their default 900-second limits. Every operation also observes
  remaining learning time. Fresh GT agent time scales by the task-agent timeout;
  independent evaluation's 7200 seconds is an additional experimental measurement budget.
- Best selection uses only packages actually scored by GT: finite canonical reward
  takes precedence, otherwise valid official pass/total counts can supply the score.
  Strictly greater scores replace best; ties retain the earlier package. Independent
  all-version scores do not select a package. Source final-schema failure precedes
  best reuse; normal-K exhaustion and terminal recheck/rollback paths are distinct.
  Recorded best, actual terminal outcome, retained historical score and selected package
  are separate fields, never relabeled as one fresh measurement.

The persistent environment keeps files, services and installed dependencies. Each
command starts the author's new shell; shell cwd and exported variables do not persist
implicitly. Verifier retains the original command/log review. Generator's terminal
uses the original controller's `_HIDDEN_EVALUATOR_ACCESS_RE` and rejection message to
block direct inspection of evaluator paths before dispatch. This is a heuristic command
boundary, not a filesystem sandbox. Same-container access restores execution evidence but
provides weaker physical isolation than the retired separate-container verifier.

The local sealing bridge accepts canonical relative UTF-8 files, including the
creator's `evals/`, `assets/` and non-Python scripts; host `manifest.json` remains
reserved. Path traversal, links, special files and file-hash checks remain enforced.
Runtime caches are excluded only while collecting a mutable candidate, never while
checking a sealed bundle. The export hook supplements the author's scripts/references
export with the complete safe text package, so GT, best snapshots and rollback share
one content hash. Invalid draft checks retain raw verifier evidence without claiming
that a sealed parent package passed. Binary Skill attachments remain unsupported;
binary task deliverables are collected separately as public artifacts.

The source's pytest result parser and audit are retained. They can miss semantic errors,
incorrect public premises and certain skipped-test patterns; the bank-specific obligation
checker, AST novelty guard and one-program-repair quota are **not** imposed on the v6
Verifier. A valid but wrong locked suite can still block GT. Reusing the author code is
not proof of surrogate correctness or arbitrary-code security.

## Deliberate experiment adapters

Both domains retain pooled retrieval and frozen B*, a one-POST S0 with no creation
execution/self-repair, explicit submission, restricted oracle feedback, and separate
all-content-version evaluation. Fixed Generator inputs are sent once, its own continuation
persists, and tool responses are bounded previews with raw evidence references.
SkillsBench context admission uses the smaller of the configured 272,000 window and
the observed provider window, with unchanged β0.7 and a 32,768 reserve. It compares the
full visible conversation estimate with the last provider input/output, including reasoning, plus
the subsequent visible increment. Cumulative billed tokens are not context occupancy.
Opaque usage is projected only when continuing the same thread; a new independent
Verifier Chat keeps the observed window, not prior occupancy or billing totals in its
context estimate.
This is a declared transport adaptation, not the author's exact LiteLLM tokenizer rule.
An effective-episode hook projects occupancy into the original `token_budget` stop.
A proven Generator predispatch `InputTokenBudgetExceeded` disables further Generator
requests but leaves the original schema/best/reuse/post-final branches available. Only
that exact exception, with a parseable original run log recording `token_budget`, can
finish as a budget stop; no model response is fabricated and UNKNOWN is never replayed.
Output token and fee quotas remain disabled as requested.
The author's idle/stale automatic completion remains active. Safe complete packages
entering that gate are sealed as host-forced submissions, separately from explicit
model task_complete events; invalid drafts remain unversioned.

Transport uses a single-POST host Journal instead of upstream HTTP retries. A received
provider response is saved before normalization; UNKNOWN is not retried. Native Codex
receives a credential-free Unix relay. GPT/Opus protocol conversion and the pinned CLI
are transport adaptations, not a claim of byte-for-byte launcher reuse. The author Skill
mount is read-only: only the exact installer chmod failure is handled by attesting kernel
mount options, full file hashes and absence of links; all other setup failures are rejected.
Source installation and pre/post digest guards remain unmodified.

For API-backed custom providers, native Codex automatic compaction uses ordinary
Responses summaries, with complete requests still journaled. Offline simulated-provider checks exercise transport
and container behavior, not true model compatibility or task success. Real model smoke and
full matrices remain `NOT_MEASURED` until actual evidence is archived.

The optional ChatGPT subscription transport uses the official app-server and one
observable Codex creation turn; underlying HTTP calls/retries are `NOT_OBSERVABLE`,
so this is not the single-POST Bedrock contract. Its native-tool and compaction events
are distinct fatal gates: received event streams are sealed privately before parsing,
then the operation stops UNKNOWN without replay. The exact event subtype of historical
`codex-author-fix-20261008-003` is not established by its retained evidence. Provider
usage and system/opaque-context estimation remain separate from billing totals.

τ remains v4: an external Generator drives bank tools and the user simulator, Verifier runs
in an isolated public container, M15 counts revision attempts and K5 effective judgments,
and unsuccessful chains select their last safely submitted package. SkillsBench v6 uses
r15 and author best/terminal selection. Historical v3/v4 results and retired verifier notes
remain archived and cannot serve as v6 checkpoints. These domain adapters and the additional
independent evaluation prevent labeling the whole project as a full paper reproduction.

## V6 transport and public-input adaptations

`skillsbench_evolution.py` invokes the published controller through
`author_controller.py`. Run-bound clients keep Generator and Verifier conversations
separate. MAIN belongs to the existing LearningSession; the bridge does not own
cleanup. Fresh oracle/evaluation still use the pinned CodexSkillOnly adapter.
Transparent hooks archive complete submitted packages, the author's actual pytest
results, native counters and scoring phases. Partial host exports without references
are not treated as newly measured packages. UNKNOWN/authentication/cleanup failures
stop all subsequent dispatches even if an upstream exception handler catches them.

The only additional runtime instruction is
`prompts/skillsbench-verifier-adapter.txt`: read-only original public-input locations,
`evo-current` seed/package naming, current-task requirements versus background
examples, and explicit treatment of unprovided conventions as uncertainty rather
than unconditional-failure placeholder checks. This is an experiment adaptation,
not original author prompt text. Each public original is whitelisted and hashed;
private grader files are not exposed. Host and Verifier logs are not copied into
Generator-readable terminal-evidence files.

The effective host/provider window and occupancy rule above replace the author's catalog
fallback for this provider; original terminal selection branches remain in use. Output
caps are not reinstated. The boolean GT feedback boundary is retained
by omitting GT detail fields from the controller-facing projection; complete reward,
counts and evidence remain in private oracle history. This differs from the release's
coarse GT-derived labels. These differences, frozen retrieval and one-shot untested
S0 make this an explicitly adapted experiment rather than an exact reproduction.

The native controller resets on run. Incomplete native learning cannot be resumed
by repeating setup/run: completed results are reused, interrupted chains require
an independently identified trial. Old checkpoints and measurements are preserved.
