# Resource-to-Skill Poisoning：项目可行性与顶会化方案

> 检索截止：2026-08-29。本文档集仅用于隔离环境中的防御性研究。实验只允许合成资源、模拟工具和无副作用 canary；不向真实网页、搜索引擎、代码仓库或公共 skill 市场注入内容，也不使用真实账号、凭据、网络回连、破坏性动作或自传播机制。

## 当前执行入口

- [正式实验计划](EXPERIMENT_PLAN.md)：当前权威协议，完整定义研究问题、AppWorld 数据拆分、457-document resource pool、Qwen3.8/H200 参数、skill creation 与 hard-reset 流程、对照组、样本量、统计分析和 go/no-go 条件。
- [机器可读实验配置](configs/experiment_plan.yaml)：固定版本、处理条件、预算、随机化、主要终点与运行前必须填入的 data/task/template manifest hashes。
- [Template incidence skeleton](configs/template_incidence.csv)：已验证的 120-block BIBD core 与 40-block nested extension，共 160 个 matched build blocks。

`analysis/` 下的文档是前期 research 记录和设计依据；正式运行若与调研文档有冲突，以以上两个文件为准。

## 一句话结论

想法可做，但宽泛的“污染外部资料，让 agent 生成带后门的持久 skill”已经与 **SkillJack、MPBench、PoisonedEvolution、Practice Makes Unsafe** 等 2026 年工作高度重合。若仍按这个表述投稿，创新性不足。

最值得继续验证的版本是：

> 在 AppWorld 单一 canonical-provider corpus 中，攻击者只能加入一条低信任 overlay；agent、构建任务和后续任务都良性。overlay 不保证被检索，必须在 457 条 clean docs 中自然竞争，经正常执行被 compiler 固化为 skill；原资源完全移除、agent/runtime 重启后，该 skill 才在新任务中触发本地无副作用 canary。attack author 通过角色隔离看不到实际 pool manifest、task/query/rank/seed；另做 corpus-known robustness。

这个问题可暂称 **Retrieval-Mediated Resource-to-Skill Poisoning（R2SP）**。这是工作名，不是“首创”声明。

## 审稿人视角的判断

- **可行性：高。** 资源检索、轨迹学习、skill 生成和跨会话复用四个组件都已有公开系统或基准，工程上可以拼成端到端试验台。
- **原始新颖性：偏低。** “experience/document → generated skill → persistence”本身已被近期论文明确提出。
- **可守的新意：中等偏高，但依赖执行质量。** 核心必须是极低 document/token budget、自然检索、完整因果链、source-removed 持久性，以及针对“短时低信任资料被提升为长期 behavior-bearing artifact”的专属防御。
- **顶会条件：攻击 + benchmark + 系统防御。** 单做一种新的 poison prompt 很容易被评价为 PoisonedRAG 与 SkillJack 的组合。
- **最重要的科学问题：** 在现实稀释和竞争检索下，这条攻击链到底还能不能成立；若不能，给出污染阈值、失败边界和可靠 admission 条件同样可能形成有价值的负结果论文。

## 文档导航

1. [文献综述与相似论文](analysis/01_literature_review.md)：按直接重合、memory/RAG、skill 供应链和良性 skill creation 四类梳理，并说明哪些结论不能再宣称。
2. [Threat model 与安全边界](analysis/02_threat_model.md)：形式化资源池、攻击者能力、端到端成功条件、因果链和隔离实验要求。
3. [实验设计与统计计划](analysis/03_experiment_design.md)：研究问题、最小可行实验、顶会规模设计、指标、基线、样本单位、统计模型和失败标准。
4. [数据集、系统与许可证](analysis/04_datasets_and_reuse.md)：可直接复用的 benchmark、代码许可、适配成本和推荐组合。
5. [新颖性、论文定位与防御](analysis/05_novelty_and_positioning.md)：三种 framing、可主张/不可主张的贡献、审稿风险和系统防御方向。
6. [项目路线图](analysis/06_project_roadmap.md)：两周可行性验证、后续里程碑、go/no-go 规则和建议仓库结构。
7. [SkillJack 与 MPBench 精确对照](analysis/07_skilljack_mpbench_comparison.md)：逐项比较攻击控制点、资源检索、skill 生成、持久性和评测指标。
8. [MPBench 与 SkillJack 复用方案](analysis/08_reuse_mpbench_skilljack.md)：说明 benign cases 的真实语义、数据清洗、matched placebo、resource-pool 转换与许可证。
9. [严格良性资源池筛选](analysis/09_strict_benign_resource_pools.md)：只保留原始文档、API schema、manual 和 policy text，比较 AppWorld、API-Bank、DocPrompting、OR-ShARC 等候选并给出最终组合。
10. [AppWorld 实验适配](analysis/10_appworld_adaptation.md)：区分任务、API 文档、可调用环境和隐藏评测器，并给出本项目的严格 resource-pool 边界与构建—部署流程。
11. [AppWorld × Qwen3.8 协议](analysis/11_appworld_qwen38_protocol.md)：明确 agent/retriever/runtime/evaluator 的可见性，给出 resource selection、skill creation、隔离部署、因果对照及单张 H200 服务配置。

## 推荐的最小决策

不要一开始做大规模攻击优化。先用固定 32 个 matched blocks：A–D 核心 128 个 acquisition/build pipeline units/768 次 deployment episodes，Eraw 增加 32 个 identity controls/192 次 episodes，paired clean-no-overlay 增加 32 个 units/192 次 episodes，再加 forced/direct-canary 机制检查；合计 180 个 pipeline units、最多 180 次 Qwen compiler invocations、232 个被 assay 的 generated/derived/prebuilt instances 和 1,312 次 episodes。完成严格 paired pilot：

- poison 与 matched placebo；
- natural retrieval 与 forced retrieval；
- skill 保留与删除；
- compiled skill 与同 input information/serializer/role/wrapper/token budget 的 identity compiler-packet artifact；
- trigger present 与 absent；
- acquisition 后删除所有攻击资源和相关 memory，再做 deployment。

主结果是三个 trigger-positive 新任务上的 artifact-level 平均：assigned overlay 必须自然 `read_doc` 全文、acquisition 成功、skill 被加载、source removed 后正确 canary 被调用且 AppWorld task 通过；未读取样本按 ITT 记 0，不做事后筛选。trigger-negative 误触独立作为固定设计 FPR safety gate。若同一攻击来源的 1–3 条文档在自然检索下端到端风险差接近零，就停止“攻击论文”路线，转向鲁棒 admission 或负结果测量。

## 建议论文主线

最强的主线不是“又一个后门”，而是：

> **Untrusted Evidence Promotion in Skill Synthesis**：测量单一 canonical corpus 中极低 document/token-share overlay 经检索与 compilation 变成持久行为 artifact 的风险传递函数，并设计 provenance-preserving admission 与 descendant-aware revocation。若未来加入真正 multi-origin corpus，再扩展到 Byzantine-source/quorum 主张。

这条主线同时包含可证伪的攻击问题、可复用 benchmark 和系统性防御，最接近 USENIX Security、CCS、NDSS 或 NeurIPS Datasets & Benchmarks 对完整贡献的期待。
