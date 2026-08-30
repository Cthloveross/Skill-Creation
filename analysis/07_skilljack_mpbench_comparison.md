# SkillJack 与 MPBench 精确对照

## 核心结论

并非没有类似工作。[SkillJack](https://arxiv.org/abs/2608.03509) 已覆盖 poisoned experience → generated skill → source-deleted persistence；[MPBench](https://arxiv.org/abs/2606.04329) 的 C4 已覆盖 external input/trace → procedural skill → later-session behavior。尚未被两者完整覆盖的是：攻击者只控制未知混合 resource pool 中少量独立来源，payload 不保证进入上下文，必须先赢得自然竞争检索，再影响全良性任务轨迹和 skill compilation。

## SkillJack 的控制点

SkillJack 的 threat model 把 experience 定义为 trajectories、interaction logs、documents 和 external knowledge。攻击者只能影响 experience layer，不能直接写 skill library、修改 extractor 或确定性控制 router。概念上，它允许 poisoned record 通过 indirect content injection、shared experience pool 或 compromised trajectory dataset 进入 learning corpus。

但是论文的实验明确只使用 injected trajectories。输入共 150 条轨迹：65 条 functionally framed poisoned trajectories、65 条直接恶意措辞对照和 20 条 clean trajectories。SkillX routing 实验使用的 356-skill library 中有 305 个 poisoned skills、51 个 clean skills；这是 skill 生成之后的路由竞争，不是大型未知 resource pool 中的低比例资料污染。

Anything2Skill 实验也使用同一批 trajectory files，通过 DOC mode 生成 30-skill bank，再做 lexical skill retrieval。论文没有测量 attacker resource 在未知诚实语料中的 top-k exposure、自然任务是否采纳该资源，或 resource → trace 的转化概率。

论文报告的 SkillX 56.2% 与 Anything2Skill 89.2% 是 routing-level policy-violation proxies，而非真实外部服务上的 live-compromise rates。80% 的 source-deletion persistence 对本项目非常重要，但只证明 poisoned trajectory 已经进入 compiler 后的持久化。

## MPBench 的结构

MPBench 是 memory-poisoning benchmark，而不是专门的 resource-pool 或 skill-creation benchmark。论文在 OpenClaw 和 HERMES 上使用 GPT-OSS-120B，保持默认 system prompt 与 memory-write configuration。

它定义四条长期记忆写入通道：

| Channel | 含义 | 写入类型 |
|---|---|---|
| C1 | 外部输入显式要求 remember/store/save | Direct |
| C2 | system prompt 要求保存重要信息，模型判断是否写入 | Inferred |
| C3 | session end/context limit 时进行 memory compaction | Inferred |
| C4 | agent 将完成的任务轨迹自主总结为 reusable procedural skill | Inferred |

对应六类攻击：Explicit Command Insertion、Conditional Command Insertion、Salience-Driven Compaction Poisoning、Policy-Conformant Fact Injection、False Precedent Insertion 和 Skill-Procedure Insertion。前三类是 strong-signal，后三类是 weak-signal；C4 对应 Skill-Procedure Insertion。

数据集包含 3,240 个攻击 cases 和 2,997 个 benign cases，覆盖 email、file/document、script/code、calendar、Slack、web browsing 和 skill invocation 七个领域。每个 case 主要含 `user_query`、恶意 `context`、目标 `expected_memory` 与后续 `retrieval_query`。

MPBench 的两个阶段是：

1. Memory-write phase：检查外部 payload 是否导致目标指令进入 persistent store，得到 ASR。
2. Memory-retrieval phase：在后续会话中检查 poisoned memory 是否影响输出、工具动作或行为，得到 RSR；RSR 只在 write 成功的 cases 上计算。

其 delivery 有 static context 和 dynamic tool-call 两种。前者直接给 payload，后者给出文件路径等明确 reference，让 agent 调工具读取。两者都保证 agent 在当前任务中处理目标内容，不测试攻击资源能否在未知混合语料中击败 clean resources。

C4 只在支持自主 skill creation 的 HERMES 上测试，共 240 cases；论文报告 58.33% ASR 和 61.67% conditional RSR。它已经证明外部输入中的攻击步骤可能进入 procedural skill，但没有测量 resource-pool dilution、natural top-k exposure 或 resource → trace uptake。

## 逐项差异

| 维度 | 拟议项目 | SkillJack | MPBench C4 |
|---|---|---|---|
| 攻击者直接写 skill | 否 | 否 | 否 |
| 攻击入口 | 普通外部资源 | injected experience/trajectory；概念上可含文档 | task context 或明确 tool reference |
| 未知诚实 resource pool | 是 | 未实验 | 否 |
| 低来源身份预算 | 是 | 未定义；实验污染比例很高 | 未定义 |
| 自然 top-k resource retrieval | 是 | 未实验；只测后续 skill routing | 否 |
| 全部任务良性 | 是 | 构造 poisoned trajectories | task 表面良性，context 含 payload |
| Agent 自生成 skill | 是 | 是 | 是，仅 C4/HERMES |
| Source 移除后测试 | 是 | 是，报告 80% persistence | 后续会话不再需要原 context，但 poisoned memory/skill 保留 |
| 执行级确定性 canary | 是，计划 | 主要为 routing-level proxy | 主要用 LLM judge 判定 write/retrieval behavior |

## 严格的新颖性表述

不能说“没有类似工作”或“首次 resource-to-skill poisoning”。更准确的表述是：

> 现有工作分别证明了 poisoned experience 或外部 context 可以进入持久 skill；尚缺少对 bounded attacker sources 在 unknown mixed corpus 中经过 natural competitive retrieval、benign trace formation 和 skill compilation 的端到端概率、瓶颈与防御的系统测量。

这个差异足以支持继续做 pilot，但能否成为顶会贡献取决于它在低预算自然检索下是否成立，以及是否产生新的 Byzantine admission、lineage 或 revocation 机制。
