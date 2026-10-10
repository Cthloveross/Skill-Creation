# Retrieval and Skill Evolution

τ-Knowledge 与 SkillsBench 共用一套 pipeline、两个任务适配器。源码、配置、提示与测试集中在 [skill-evolution](experiments/tau-knowledge/skill-evolution/README.md)。

每题：多轮检索 → 冻结 B* → 一次创建 S0 → **Generator 直接执行、修改并提交** → 独立公开验证 → fresh oracle → 各内容版本独立评估。创建禁止自测和重发。τ 使用 `tau.skill-evolution.v4`；SkillsBench v8 使用作者的 r15/K5/120-effective-episode 控制器，并在 85 个任务上比较 benign 与四类注入的 5%／10% 条件。默认 Bedrock GPT-5.4／us-east-1。

SkillsBench 的学习环境持续保留服务与依赖，正式评分使用作者 CodexSkillOnly 的 fresh 环境；τ学习直接使用银行工具，正式评分保留官方tau2执行器。τ Verifier检查公开快照；SkillsBench复用作者Verifier，在同一学习容器中使用独立模型会话。环境未通过预检则停止，不降级宿主执行。

```bash
make setup
make check
```

SkillsBench 同事交接直接使用 GitHub clone，首次在已具备 Docker/Compose 和 NVIDIA GPU 的机器上执行：

```bash
make skillsbench-prepare GPU=0 PREP_JOBS=8
```

此命令自动下载固定工具和模型、准备九条件资料池与索引、构建85题镜像并封存本机配置；不读取凭据或调用付费模型。后续操作见 [全量 SkillsBench 交接入口](experiments/tau-knowledge/skill-evolution/runs/skillsbench/full-85-v8-handoff/HANDOFF.md)。ZIP仅是可选备份。

运行前按对应交接准备本地凭据并通过环境预检：

- [通用方法论：问题、威胁模型、演化与跨数据集实验设计](docs/skill-evolution-method.md)
- [当前实验规范：τ／SkillsBench 的具体合同与参数](experiments/tau-knowledge/skill-evolution/PROTOCOL.md)
- [SkillsBench：四类注入的实际文本、抽样、暴露与ASR判定](docs/skillsbench-injection-design.md)
- [τ：97题 × 三条件交接](experiments/tau-knowledge/skill-evolution/runs/tau/HANDOFF.md)
- [SkillsBench：v8 注入设计、retrieval pilot 与 765-cell 运行交接](experiments/tau-knowledge/skill-evolution/runs/skillsbench/HANDOFF.md)

[历史实验索引](experiments/tau-knowledge/skill-evolution/archive/index.json)收纳旧结果、配置与证据，旧checkpoint不续接新源码身份；[历史分析](experiments/tau-knowledge/skill-evolution/archive/HISTORY.md)不代表当前方法成绩。凭据、私有评分及原始模型日志不进入公开交接。
