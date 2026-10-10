# Retrieval 与 Skill Evolution

当前共享方法为：**只读输入发现与检索 → 冻结B* → 一次创建S0 → Generator直接执行和修改 → 独立Verifier → fresh官方评分与逐版本独立评估**。创建阶段禁止执行、自测和重发；每题独立创建和演化Skill。

| 实验 | 方法与规模 | 配置 | 交接 |
|---|---|---|---|
| τ-Knowledge | `tau.skill-evolution.v4`；97题×benign/5%/10% | [experiment.yaml](configs/experiment.yaml) | [τ HANDOFF](runs/tau/HANDOFF.md) |
| SkillsBench | `skillsbench.skill-evolution.v8`；85题×benign/四类注入的5%/10%，共765条链 | [skillsbench.yaml](configs/skillsbench.yaml) | [SkillsBench HANDOFF](runs/skillsbench/HANDOFF.md) |

**当前 SkillsBench v8 结果只有 [15-cell retrieval pilot](runs/skillsbench/retrieval-pilot-dymal4-gpt54-20261009-001/public-summary.json)。** 它只验证 Analyzer 检索和冻结：15/15 条 acquisition 已测，未创建 S0，也未执行 evolution、oracle、utility 或 ASR。完整 765-cell 矩阵尚未运行。

当前 v8 代码验收证据位于 `runs/skillsbench/readiness-dymal4-v8-20261010-001/`。该目录是机器检查记录，不是模型实验结果，也不代表 85 个任务已经全部通过 fresh preflight。旧 v7 结果与 readiness 已移入 `archive/runs/`，不能接入 v8 checkpoint。

```text
src/tau_skill_evolution/   共享封存、模型接口、作者组件与两个任务适配器
configs/                  当前配置和固定数据manifest
prompts/、meta/、licenses/  实际提示及作者出处
runtime/                  依赖、镜像和逐题环境锁
scripts/、tests/           准备、运行、回归和显式集成检查
data/                     本地输入、私有grader、背景池、索引和环境
runs/skillsbench/         当前HANDOFF、v8 retrieval pilot与v8 readiness
runs/tau/                 τ交接与保留的运行记录
archive/                  既有历史归档
```

方法定义和信息边界见 [PROTOCOL](PROTOCOL.md)；跨数据集方法论见 [skill-evolution-method.md](../../../docs/skill-evolution-method.md)。作者出处保存在 [SOURCE](meta/coevo-authoring/SOURCE.md)。SkillsBench Analyzer 通过只读输入发现和背景池检索建立 B*；学习使用官方持续环境和作者控制器，评分使用 fresh CodexSkillOnly。四类实际注入文本位于 `injections/skillsbench/`，完整构造与判定见 [injection design](../../../docs/skillsbench-injection-design.md)。τ 的银行执行合同不随此次整理改变。

```bash
make setup
make check
```

CLI为 `preflight / create / evolve / evaluate / report / run`，默认tau；准确SkillsBench新trial命令见HANDOFF。`run`不自动执行NoSkill，需先调用`evaluate --no-skill`。付费入口必须先通过本机准入，环境不可用时不回退host或历史工作区。

已完成封存复用，UNKNOWN不重发；修改源码、提示、模型或配置须使用新身份和空run目录。SkillsBench未完成作者学习循环不能重新run重置计数；学习容器丢失或关闭失败不能伪装恢复。凭据仅本机提供，缺测保持null/`NOT_MEASURED`，独评不回流学习或挑选最终版本。
