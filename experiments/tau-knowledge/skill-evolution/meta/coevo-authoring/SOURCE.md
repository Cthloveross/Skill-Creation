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

The adaptation retains reusable helpers, clear interfaces, input-grounded methods,
complete task coverage, documented execution, package inheritance, independent verification,
and accumulated public feedback. It removes the terminal-response protocol and meta-skill
instructions to execute drafts, spawn subagents, create with/without-Skill baselines,
grade experiments, or repeat initial generation. S0 remains one model call with structural
packaging only; all task execution and repairs occur in evolution.

No task-specific gold answers, upstream canonical tests, released Skills, or hidden oracle
diagnostics are included. Historical public feedback is replayed explicitly within the
same frozen-base identity, rather than sharing server-side conversations between roles.
