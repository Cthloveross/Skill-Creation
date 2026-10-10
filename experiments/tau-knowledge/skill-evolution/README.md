# Retrieval 与 Skill Evolution

当前共享方法为：**只读输入发现与检索 → 冻结B* → 一次创建S0 → Generator直接执行和修改 → 独立Verifier → fresh官方评分与逐版本独立评估**。创建阶段禁止执行、自测和重发；每题独立创建和演化Skill。

| 实验 | 方法与规模 | 配置 | 交接 |
|---|---|---|---|
| τ-Knowledge | `tau.skill-evolution.v4`；97题×benign/5%/10% | [experiment.yaml](configs/experiment.yaml) | [τ HANDOFF](runs/tau/HANDOFF.md) |
| SkillsBench | `skillsbench.skill-evolution.v7`；85题benign | [skillsbench.yaml](configs/skillsbench.yaml) | [SkillsBench HANDOFF](runs/skillsbench/HANDOFF.md) |

**最新SkillsBench结果只有 [input-discovery-five-gpt54-20261008-003](runs/skillsbench/input-discovery-five-gpt54-20261008-003/public-summary.json)。** GPT-5.4 API五题已完成，NoSkill/S0/Final Task pass为1/5、3/5、3/5，22个实际内容版本均独立评分。完整85题矩阵尚未测量，不据五题外推。

[readiness-skillsbench-input-discovery-20261008-001](runs/readiness-skillsbench-input-discovery-20261008-001/final-status.json)是这版代码的**验收证据目录**：回归、真实Docker配合模拟provider、交叉审查和清理检查。它不是额外模型实验，也不是全部85题环境READY的证明。

```text
src/tau_skill_evolution/   共享封存、模型接口、作者组件与两个任务适配器
configs/                  当前配置和固定数据manifest
prompts/、meta/、licenses/  实际提示及作者出处
runtime/                  依赖、镜像和逐题环境锁
scripts/、tests/           准备、运行、回归和显式集成检查
data/                     本地输入、私有grader、背景池、索引和环境
runs/skillsbench/         当前HANDOFF与唯一最新五题结果
runs/readiness-*/         当前代码验收证据
runs/tau/                 τ交接与保留的运行记录
archive/                  既有历史归档
```

方法定义和信息边界见 [PROTOCOL](PROTOCOL.md)；跨数据集方法论见 [skill-evolution-method.md](../../../docs/skill-evolution-method.md)。作者出处保存在 [SOURCE](meta/coevo-authoring/SOURCE.md)。SkillsBench Analyzer只预先接收原始instruction、工作目录和授权输入根，通过只读列举/读取发现原始输入，背景资料合池检索；学习使用官方持续环境和作者控制器，评分使用fresh CodexSkillOnly。τ的银行执行及合同不随此次整理改变。

```bash
make setup
make check
```

CLI为 `preflight / create / evolve / evaluate / report / run`，默认tau；准确SkillsBench新trial命令见HANDOFF。`run`不自动执行NoSkill，需先调用`evaluate --no-skill`。付费入口必须先通过本机准入，环境不可用时不回退host或历史工作区。

已完成封存复用，UNKNOWN不重发；修改源码、提示、模型或配置须使用新身份和空run目录。SkillsBench未完成作者学习循环不能重新run重置计数；学习容器丢失或关闭失败不能伪装恢复。凭据仅本机提供，缺测保持null/`NOT_MEASURED`，独评不回流学习或挑选最终版本。
