# Retrieval 与 Skill Evolution

当前共享方法为：**只读输入发现与检索 → 冻结B* → 一次创建S0 → Generator直接执行和修改 → 独立Verifier → fresh官方评分与逐版本独立评估**。创建阶段禁止执行、自测和重发；每题独立创建和演化Skill。

| 实验 | 方法与规模 | 配置 | 交接 |
|---|---|---|---|
| τ-Knowledge | `tau.skill-evolution.v4`；97题×benign/5%/10% | [experiment.yaml](configs/experiment.yaml) | [τ HANDOFF](runs/tau/HANDOFF.md) |
| SkillsBench | `skillsbench.skill-evolution.v8`；85题×benign/四类注入的5%/10%，共765条链 | [skillsbench.yaml](configs/skillsbench.yaml) | [SkillsBench HANDOFF](runs/skillsbench/HANDOFF.md) |

当前工作入口为 [SkillsBench retrieve](runs/skillsbench/retrieve/)：**85题×5条件＝425次整篇文档检索与B*冻结**，先由GPT-5.4完成；复用此前已完成的15份整篇获取，补做410份，后续模型复用同一批封存B*。五条件为benign、HTTP5／10、File Delete5／10；本阶段不创建S0、不演化，也不运行NoSkill或执行ASR。实际进度以该目录的运行记录为准。

此前三轮检索、三份smoke目录、历史readiness和两份preflight已原样移入 [archive/runs/skillsbench](archive/runs/skillsbench/)，公开结果及原始私有证据均保留。已完成的分块与整篇小样本各15组，分析见 [结果§5.4–5.5](../../../docs/skillsbench-v8-results-20261013.md#54-实际检索校验原始背景都找到充分性判断存在问题)。历史readiness只记录当时的代码验收，不能代表当前任务环境READY；归档checkpoint不原地续跑。

```text
src/tau_skill_evolution/   共享封存、模型接口、作者组件与两个任务适配器
configs/                  当前配置和固定数据manifest
prompts/、meta/、licenses/  实际提示及作者出处
runtime/                  依赖、镜像和逐题环境锁
scripts/、tests/           准备、运行、回归和显式集成检查
data/                     本地输入、私有grader、背景池、索引和环境
runs/skillsbench/         HANDOFF、正式矩阵交接包与当前retrieve工作区
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
