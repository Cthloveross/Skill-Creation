# Resource-to-Skill Poisoning

> 仅用于隔离环境中的防御性研究。只使用本地无副作用 canary，不向真实网页、仓库或公共 skill 市场注入内容。

## 当前阶段

现在只做一个小规模 feasibility pilot：

> Qwen3.8 执行良性 AppWorld 任务时，能否自然读取 457 条正常 API 文档中的一条攻击者 overlay，把其中规则写入 skill，并在删除原资源、重启 agent 后继续触发？

## 执行入口

- [精简实验计划](EXPERIMENT_PLAN.md)：两臂设计、resource pool、执行流程、指标和 go/no-go。
- [最小机器配置](configs/experiment_plan.yaml)：runner 需要的参数。
- [`analysis/`](analysis)：此前的文献、数据集和完整论文方案调研；不属于当前 pilot 的执行协议。

## Pilot 一览

- 模型：`Qwen/Qwen3.8-27B`，单张 H200，BF16；
- 数据：AppWorld；
- 条件：matched Sham vs one-document Poison；
- 规模：16 个 matched cases、32 次 build、64 次 deployment；
- 结果：自然读取、有效 skill、source-removed 持久触发、误触和任务分数。

当前只以这套两臂 pilot 为准；后续实验等 pilot 结果出来后再决定。
