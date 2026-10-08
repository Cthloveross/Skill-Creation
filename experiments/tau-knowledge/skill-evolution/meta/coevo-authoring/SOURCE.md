# CoEvoSkills sources and migration contract

All author references in this experiment are fixed to CoEvoSkills commit
`4380d4bff673dd6e1d58e5babeb2aaa0fe527119`; Harbor is fixed to
`3f28e5ce2acbff36d8b5df431e35e050ac13bef6`. This record distinguishes reused
implementation from local adapters. The active method is specified in
[PROTOCOL](../../PROTOCOL.md), with τ v4 and SkillsBench v5 contracts kept separate.

## Reused implementation

SkillsBench v5 executes the author's
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
Run identity binds the manifest, all vendored Python and all author `.txt` prompts.
V5 config no longer selects the retired local `verifier-skillsbench.md` prompt.

`author_verifier.py` adapts the existing official task Runner to the author's
`BaseEnvironment` interface and bridges its LLM factory to the run-bound provider
client. The original agent has a fresh model context and terminal access in the
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

## SkillsBench v5 controller alignment

The shared engine ports the relevant branches of the author's
[evolution controller](https://github.com/Zhang-Henry/CoEvoSkills/blob/4380d4bff673dd6e1d58e5babeb2aaa0fe527119/libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py).
It does not import the entire Harbor orchestration runtime.

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
  timeout to be multiplied. V5 starts a persistent absolute learning deadline before
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
implicitly. Verifier retains the original command/log review. Generator's local terminal
ports the controller's exact `_HIDDEN_EVALUATOR_ACCESS_RE` and rejection message to
block direct inspection of evaluator paths before dispatch. This is a heuristic command
boundary, not a filesystem sandbox. Same-container access restores execution evidence but
provides weaker physical isolation than the retired separate-container verifier.

The source's pytest result parser and audit are retained. They can miss semantic errors,
incorrect public premises and certain skipped-test patterns; the bank-specific obligation
checker, AST novelty guard and one-program-repair quota are **not** imposed on the v5
Verifier. A valid but wrong locked suite can still block GT. Reusing the author code is
not proof of surrogate correctness or arbitrary-code security.

## Deliberate experiment adapters

Both domains retain pooled retrieval and frozen B*, a one-POST S0 with no creation
execution/self-repair, explicit submission, restricted oracle feedback, and separate
all-content-version evaluation. Fixed Generator inputs are sent once, its own continuation
persists, and tool responses are bounded previews with raw evidence references. The local
context admission uses a 272K window, β0.7 and a 32K reserve; this is not the author's exact
LiteLLM tokenizer metadata rule. Output token and fee quotas remain disabled as requested.
The author's idle/stale automatic completion does not seal an unsubmitted local draft.

Transport uses a single-POST host Journal instead of upstream HTTP retries. A received
provider response is saved before normalization; UNKNOWN is not retried. Native Codex
receives a credential-free Unix relay. GPT/Opus protocol conversion and the pinned CLI
are transport adaptations, not a claim of byte-for-byte launcher reuse. The author Skill
mount is read-only: only the exact installer chmod failure is handled by attesting kernel
mount options, full file hashes and absence of links; all other setup failures are rejected.
Source installation and pre/post digest guards remain unmodified.

Native Codex automatic compaction uses ordinary Responses summaries for a custom provider,
with complete requests still journaled. Offline simulated-provider checks exercise transport
and container behavior, not true model compatibility or task success. Real model smoke and
full matrices remain `NOT_MEASURED` until actual evidence is archived.

τ remains v4: an external Generator drives bank tools and the user simulator, Verifier runs
in an isolated public container, M15 counts revision attempts and K5 effective judgments,
and unsuccessful chains select their last safely submitted package. SkillsBench v5 uses
r15 and author best/terminal selection. Historical v3/v4 results and retired verifier notes
remain archived and cannot serve as v5 checkpoints. These domain adapters and the additional
independent evaluation prevent labeling the whole project as a full paper reproduction.
