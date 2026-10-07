# Retrieval and Skill Evolution

τ-Knowledge 与 CoEvo/SkillsBench 共用一套 pipeline、两个任务适配器。源码、配置、提示与测试集中在 [skill-evolution](experiments/tau-knowledge/skill-evolution/README.md)。

每题：多轮检索 → 冻结 B* → 一次创建 S0 → **Generator 直接执行、修改并提交** → 独立公开验证 → fresh oracle → 各内容版本独立评估。创建禁止自测和重发；M15/K5、Generator全链120轮。当前两个方法均为v4，默认Bedrock GPT-5.4／us-east-1，不设置学习模型输出配额或费用额度。

SkillsBench 的学习环境持续保留服务与依赖，正式评分使用作者 CodexSkillOnly 的 fresh 环境；τ学习直接使用银行工具，正式评分保留官方tau2执行器。Verifier只检查提交的公开快照。环境未通过预检则停止，不降级宿主执行。

```bash
make setup
make check
```

运行前按对应交接准备数据、embedding、Docker及本地凭据：

- [研究问题、威胁模型、方法与实验参数](experiments/tau-knowledge/skill-evolution/PROTOCOL.md)
- [τ：97题 × 三条件交接](experiments/tau-knowledge/skill-evolution/runs/tau/HANDOFF.md)
- [SkillsBench：GPT-5.6 Terra / Opus 4.8 两套85题交接](experiments/tau-knowledge/skill-evolution/runs/skillsbench/HANDOFF.md)

[历史实验索引](experiments/tau-knowledge/skill-evolution/archive/index.json)收纳旧结果、配置与证据，旧checkpoint不续接v4；[历史分析](experiments/tau-knowledge/skill-evolution/archive/HISTORY.md)不代表当前方法成绩。凭据、私有评分及原始模型日志不进入公开交接。
