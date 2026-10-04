# Retrieval and Skill Evolution

当前支持 τ-Knowledge 与 CoEvo/SkillsBench 两个适配实验，共用一套代码。
源码、配置、提示、测试和运行资料均位于 [skill-evolution](experiments/tau-knowledge/skill-evolution/README.md)。

每题独立进行：多轮检索 → 冻结 B* → 一次生成 S0 → Skill/公开测试交替演化 → 每个实际版本独立评估。
创建阶段禁止执行、自测和重新生成；演化最多 15 次修订、5 次 fresh oracle，只回传 pass/fail。
所有生成与执行模型为 Bedrock GPT-5.5，区域 us-east-1。

SkillsBench共享检索仅包含85题的背景资料；当前题的任务说明与environment作为提供的输入，原始文件只在当前题的隔离环境中使用。

```bash
make setup
make check
.venv/bin/r2sp preflight --experiment tau --env-file key.env
.venv/bin/r2sp preflight --experiment skillsbench --env-file key.env
```

`make check` 是离线验收。正式矩阵要求 Docker 权限、真实镜像 digest 和每题环境通过 preflight；不会降级为宿主执行。
Bubblewrap smoke 是单题演示，不能作为正式矩阵结果。当前两份交接目录：

- [τ 全97题 × 三条件](experiments/tau-knowledge/skill-evolution/runs/tau-full-97-20261004-001/HANDOFF.md)
- [SkillsBench 全85题共享资料池](experiments/tau-knowledge/skill-evolution/runs/skillsbench-pooled-85-20261004-001/HANDOFF.md)

[实验参数与边界](experiments/tau-knowledge/skill-evolution/PROTOCOL.md)、[提示来源](experiments/tau-knowledge/skill-evolution/meta/coevo-authoring/SOURCE.md)。
历史 runs、原始资料及用户 analysis 保留，旧 checkpoint 不进入新协议。
