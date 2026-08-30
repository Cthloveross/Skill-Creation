# 文献综述：外部资源、记忆与 Agent Skill 投毒

> 检索截止：2026-08-29。范围包括 2023–2026 年与 indirect prompt injection、RAG/KB poisoning、memory poisoning、agent-authored skill poisoning、skill supply chain 和 skill creation 直接相关的原始论文与官方代码页。2026 年多篇论文仍是极新的 arXiv 预印本，本文按与课题的技术邻近度分类，不把“最新”误写成“已形成学界共识”，也不声称穷尽所有同时上传的预印本。

## 1. 结论先行

宽泛命题——“攻击者污染外部经验或资料，良性 agent 将其总结为带后门的持久 skill”——已经有直接先例，不能再作为首创贡献：

- [SkillJack: Persistent Skill Backdoors in Self-Evolving Agents](https://arxiv.org/abs/2608.03509) 直接研究 poisoned experience 经 skill extraction 被提升为持久 skill，并覆盖 SkillX 与 Anything2Skill。论文还测试了原始证据删除后的持久性。
- [From Untrusted Input to Trusted Memory / MPBench](https://arxiv.org/abs/2606.04329) 把 `experience-to-procedure write` 和 `Skill-Procedure Insertion` 纳入 memory poisoning taxonomy；外部网页、文档、邮件或工具输出可以被总结成 procedural memory/skill。
- [When Experience Becomes Instruction / PoisonedEvolution](https://arxiv.org/abs/2608.05563) 允许攻击者向 trajectory pool 提交有限、表面良性的证据，随后由 SkillClaw 或 Trace2Skill 生成目标化 skill。
- [Practice Makes Unsafe](https://arxiv.org/abs/2608.12851) 已覆盖 exposure、agent authoring、skill retrieval 与 fresh-session harm 的完整生命周期。
- [Query-Only Backdoor Attacks on Self-Evolving Skills via Trajectory Poisoning](https://arxiv.org/abs/2608.08303) 通过攻击者提交的 queries 诱导目标轨迹，再让可信 skill-evolution pipeline 固化条件后门；它控制 query/trajectory formation，而非外部资源池。
- [EVOMAL](https://arxiv.org/abs/2608.25776) 更进一步展示了 coding agent 在创建新 skill 时复用恶意 skill，从而出现 self-poisoning/self-propagation。

仍未被充分研究的交集是：**攻击者只控制未知混合语料中的极少量原始资源，不控制任务、轨迹、skill 或排序；攻击资源先要通过自然竞争检索，再经良性任务执行和 skill compilation，最后在原资源被移除后造成新的执行级行为。** 这比“把恶意轨迹直接放进学习池”更弱，也比普通 RAG poisoning 多出一次持久的权限提升。

## 2. 相似度总表

| 工作 | 攻击者控制点 | Agent 自生成 skill | 原始 source 移除后仍有效 | 自然竞争检索 | 与本课题的关键差异 |
|---|---|---:|---:|---:|---|
| SkillJack | experience/trajectory/document evidence | 是 | 是 | 部分；主要实验不是低占比未知诚实池 | 最接近；主要需超越其直接 evidence 注入、单模型和高污染 skill library 设置 |
| MPBench | 当前外部 context/tool output | procedure/memory | 可跨会话 | 否，目标内容通常已进入上下文 | 已覆盖 resource-to-procedure write，但缺少大型混合池的 retrieval competition |
| PoisonedEvolution | trajectory pool 的有限证据 | 是 | 主要测 artifact | 否 | 攻击者直接贡献学习轨迹，而不是只贡献外部资源 |
| Practice Makes Unsafe | 恶意学习任务/指令 | 是 | 是 | 否 | 学习任务本身不良性，攻击者能力更强 |
| Query-Only Trajectory Backdoor | 攻击者提交的 queries、由此产生的轨迹 | 是 | 是 | 否 | 控制 query/trajectory formation，不控制外部资源池 |
| EVOMAL | skill authoring 时可检索的恶意 skill | 是 | 是 | 有 skill retrieval | source 是已有 skill，不是普通低权限资料 |
| MemoryGraft | 外部文档/经验 artifact | 经验记忆 | 是 | 有 experience retrieval | 持久对象是 memory，不是独立 skill compiler 的输出 |
| eTAMP | web/environment observation | memory | 是 | 有环境暴露 | 重点是 memory persistence，不是 resource-to-skill promotion |
| AgentPoison / MINJA | KB、memory 或 query-only memory write | 否 | 是 | memory retrieval | 不产生新的 skill artifact |
| PoisonedRAG | corpus 文档 | 否 | 否 | 是 | 只影响当前答案，没有 execution trace 和 skill persistence |
| InjecAgent / AgentDojo | 工具返回或外部 observation | 否 | 否 | 通常否 | 研究当轮 indirect prompt injection |
| Skill-Inject 等 | 最终 skill 文件/包 | 否，直接供应 | 是 | skill routing | 绕过了 agent 的资源检索和自主创建过程 |
| Anything2Skill / SkillX | 良性文档、日志、轨迹 | 是 | 是 | 是/依系统 | 是干净管线，不是攻击研究 |

## 3. S 级：直接覆盖 experience/resource → generated skill

### 3.1 SkillJack

[SkillJack](https://arxiv.org/abs/2608.03509) 是当前必须正面比较的工作。它把 experience 定义得很宽，包括轨迹、交互日志、文档和外部知识；攻击者不需要直接修改 skill store、skill code 或 router，只需让 poisoned experience 进入后续 skill extraction。

论文的重要结果包括：原始轨迹上的检测率在被抽取为 skill 后显著下降；目标行为可在 SkillX 和 Anything2Skill 中触发；删除原始 evidence 后，部分持久效果仍存在。它也存在可利用的实验缺口：主要设置使用合成轨迹、单一模型；SkillX routing library 中 poisoned skill 占比很高；部分结果是 routing-level proxy，而不是未知诚实资源池中低预算污染的完整执行链。

对本项目的约束是明确的：不能再宣称首次发现“外部证据被 skill compiler 洗白并持久化”。可比较的新变量应是 retrieval exposure、来源身份预算、未知诚实池、source-removed 执行级结果和防御。

### 3.2 MPBench：从不可信输入到 procedural memory

[Dash et al.](https://arxiv.org/abs/2606.04329) 系统研究外部输入如何被写进可信 memory。其 taxonomy 包含 `experience-to-procedure write`，MPBench 还单列 `Skill-Procedure Insertion`。这意味着“网页/文档/邮件/tool output 中的内容被总结成以后执行的程序性规则”已经是明确命名的攻击面。

MPBench 的不同之处在于，恶意内容通常直接处在 agent 当前上下文或工具返回中，不必在攻击者未知的大型诚实池里竞争 top-k。它非常适合复用 payload 类型、write/retrieve 两阶段结构和良性对照，但不能单独回答本项目的 retrieval bottleneck。

### 3.3 PoisonedEvolution

[PoisonedEvolution](https://arxiv.org/abs/2608.05563) 研究表面正常的 trajectory evidence 如何驱动 SkillClaw 和 Trace2Skill 生成目标化 skill。其攻击者能观察目标 skill，并向 evolution pool 提供有限证据，但不能查看私有池、修改 evolution logic 或直接编辑 skill bank。论文报告少量证据即可显著操纵 skill 演化，并提出 provenance-diversity gate。

它与本项目的差别不是“有没有预算”，而是**预算落在哪一层**：PoisonedEvolution 直接控制 compiler 消费的 trajectory evidence；本项目只允许攻击者控制更上游的普通资源，资源是否被检索、是否被执行采纳、是否进入轨迹都不确定。

### 3.4 Practice Makes Unsafe 与 EVOMAL

[Practice Makes Unsafe](https://arxiv.org/abs/2608.12851) 构建了从恶意任务暴露、skill authoring 到新会话 carryover 的完整评测，并提出 SafeEvolve。它证明生命周期测量是必要的，但其攻击者能提交恶意学习任务，强于“所有任务良性”的约束。

[EVOMAL](https://arxiv.org/abs/2608.25776) 研究 coding agent 在创建新 skill 时检索并复制恶意 skill，得到自我传播。它说明二次编译会放大供应链污染，但 source 本身已经是 skill。本项目的 source 是低权限资料，核心风险是从 data plane 到 control plane 的提升。

### 3.5 其他高度相关的持久化工作

- [SkillHarm](https://arxiv.org/abs/2606.02540) 研究 fixed 和 self-mutating skill payload 的生命周期，属于最终 skill 层攻击。
- [OEP](https://arxiv.org/abs/2605.18930) 展示 locally correct、non-transferable experiences 如何误导 reflection，提示本项目应区分显式后门与正常形态的错误程序知识。
- [MemoryGraft](https://arxiv.org/abs/2512.16962) 让外部文档成为可复用 procedural experience，跨会话影响后续行为，但没有独立 skill artifact。
- [eTAMP: Poison Once, Exploit Forever](https://arxiv.org/abs/2604.02623) 从环境 observation 污染 web-agent memory，突出跨会话 persistence。
- [InjecMEM](https://arxiv.org/abs/2608.23471) 研究一次注入如何写入长期 agent memory。
- [TMA-NM](https://arxiv.org/abs/2606.24322) 提出 origin-bound authority/non-malleable memory，与本项目可能的 provenance 防御高度相关。

## 4. A 级：长期 memory 与 KB poisoning

这些论文奠定了“检索到的持久状态可以操纵 agent”的基础，但没有 resource → trace → skill compiler：

- [AgentPoison](https://papers.nips.cc/paper_files/paper/2024/hash/eb113910e9c3f6242541c1652e30dfd6-Abstract-Conference.html), NeurIPS 2024, DOI: [10.52202/079017-4136](https://doi.org/10.52202/079017-4136)。向 memory/KB 注入极少条目，借助触发查询实现目标行为。
- [Memory Injection Attacks on LLM Agents via Query-Only Interaction（MINJA）](https://arxiv.org/abs/2503.03704), NeurIPS 2025, DOI: [10.52202/085713-1554](https://doi.org/10.52202/085713-1554)。攻击者不能直接写 memory，而通过 query-only interaction 和 bridging steps 诱导写入。
- [Agent Security Bench](https://openreview.net/forum?id=V4y0CpX4hK), ICLR 2025。统一覆盖 observation injection、memory poisoning、tool poisoning 等攻击。
- [MemSecBench](https://arxiv.org/abs/2607.27080) 聚焦长期 memory 安全评测。
- [Hidden in Memory](https://arxiv.org/abs/2605.15338) 研究 sleeper-style memory poisoning。
- [Visual Inception](https://aclanthology.org/2026.acl-long.954/), ACL 2026, DOI: [10.18653/v1/2026.acl-long.954](https://doi.org/10.18653/v1/2026.acl-long.954)。说明跨模态外部输入也可能污染长期规划。

本项目应把 AgentPoison 与 MINJA 当作更强权限的上界，并通过 `source removed + memory disabled + only generated skill enabled` 排除普通 memory poisoning 解释。

## 5. B 级：RAG poisoning 与 indirect prompt injection

### 5.1 检索污染

- [PoisonedRAG](https://www.usenix.org/conference/usenixsecurity25/presentation/zou-poisonedrag), USENIX Security 2025。研究少量对抗文档在大规模语料中控制目标问题输出；它最适合提供 corpus-level retrieval attack 基线。
- [AgentPoison](https://arxiv.org/abs/2407.12784) 同时包含 memory/knowledge-base retrieval backdoor，可作为 embedding-space 优化对照。
- [PoisonArena](https://arxiv.org/abs/2505.12574) 研究多攻击者竞争的 RAG poisoning，提醒本项目不能只用单攻击者、静态干净池。
- [Benchmarking Poisoning Attacks against RAG](https://arxiv.org/abs/2505.18543) 比较不同 RAG poisoning 方法和系统条件。
- [RobustRAG](https://arxiv.org/abs/2405.15556) 研究面对检索语料污染时的可证明鲁棒聚合，是 Byzantine source synthesis 的直接防御参照。
- [Overcoming the Retrieval Barrier](https://www.usenix.org/conference/usenixsecurity26/presentation/chang-hongyan), USENIX Security 2026，以及 [Confundo](https://www.usenix.org/conference/usenixsecurity26/presentation/hu-haoyang), USENIX Security 2026，强调真实检索中的 query mismatch、chunking 和跨 embedding 模型问题。

这些工作只测当次输出或行动。本项目的区别必须由 deployment 隔离来证明：acquisition 后删除攻击资源，关闭相关 memory，在新会话仅加载生成 skill。

### 5.2 间接提示注入与 agent security benchmark

- [Not What You've Signed Up For](https://arxiv.org/abs/2302.12173), ACM AISec 2023, DOI: [10.1145/3605764.3623985](https://doi.org/10.1145/3605764.3623985)，是网页、邮件等间接提示注入的奠基性工作。
- [InjecAgent](https://aclanthology.org/2024.findings-acl.624/), Findings of ACL 2024, DOI: [10.18653/v1/2024.findings-acl.624](https://doi.org/10.18653/v1/2024.findings-acl.624)，提供良性用户任务、工具权限和 attacker-controlled observation。
- [AgentDojo](https://papers.nips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html), NeurIPS 2024 Datasets & Benchmarks, DOI: [10.52202/079017-2636](https://doi.org/10.52202/079017-2636)，提供动态工具环境、utility 与 security 双指标。
- [Task Shield](https://aclanthology.org/2025.acl-long.1435/), ACL 2025, DOI: [10.18653/v1/2025.acl-long.1435](https://doi.org/10.18653/v1/2025.acl-long.1435)，将用户任务与外部指令对齐用于防御。
- [Adaptive Attacks Break Defenses](https://aclanthology.org/2025.findings-naacl.395/), Findings of NAACL 2025, DOI: [10.18653/v1/2025.findings-naacl.395](https://doi.org/10.18653/v1/2025.findings-naacl.395)，说明静态防御结果必须接受自适应评估。
- [One Shot Dominance](https://aclanthology.org/2025.findings-emnlp.1023/), Findings of EMNLP 2025, DOI: [10.18653/v1/2025.findings-emnlp.1023](https://doi.org/10.18653/v1/2025.findings-emnlp.1023)，进一步测量一次间接注入的支配性。
- [RIPRAG](https://aclanthology.org/2026.findings-acl.833/), Findings of ACL 2026, DOI: [10.18653/v1/2026.findings-acl.833](https://doi.org/10.18653/v1/2026.findings-acl.833)，和 [PRA-RAG](https://aclanthology.org/2026.findings-acl.1794/), DOI: [10.18653/v1/2026.findings-acl.1794](https://doi.org/10.18653/v1/2026.findings-acl.1794)，提供近期 RAG prompt-injection 攻防参照。

为了不让论文退化成普通 IPI，应单独报告 overt imperative injection 与 weak-signal procedural misinformation。若去掉“忽略先前指令”类文本后效果消失，创新性会显著下降。

## 6. C 级：skill 文件与供应链攻击

这类工作证明 skill 生态确实危险，但攻击者直接控制最终 artifact：

- [Skill-Inject](https://arxiv.org/abs/2602.20156)：系统评估 skill file attacks，公开代码采用 MIT 许可证。
- [Towards Secure Agent Skills](https://arxiv.org/abs/2604.02837)：架构与威胁 taxonomy。
- [Supply-Chain Poisoning Attacks Against LLM Coding Agent Skill Ecosystems](https://arxiv.org/abs/2604.03081)：编码 agent skill 供应链污染。
- [BadSkill](https://arxiv.org/abs/2604.09378)：model-in-skill poisoning。
- [RouteGuard](https://arxiv.org/abs/2604.22888)：用 internal signals 检测 skill poisoning。
- [Exploiting LLM Agent Supply Chains via Payload-less Skills](https://arxiv.org/abs/2605.14460)：由恶意 skill 诱导模型在运行时合成 payload。
- [Poise](https://arxiv.org/abs/2606.07943)：position-aware skill instruction injection。
- [SkillGate](https://arxiv.org/abs/2607.25619)：skill admission 防御。
- [Towards a Risk Assessment of Malicious Skill Files in Coding Agents](https://arxiv.org/abs/2608.05223)：面向 coding-agent skill 的风险测量。
- [SkillBloat](https://arxiv.org/abs/2608.21929)：skill 库膨胀与路由/安全风险。

这些是“直接安装恶意 skill”的强攻击上界。本项目不能把其结果说成 resource poisoning；相反，应强调攻击者从未写 skill，是良性 compiler 把低权限 evidence 提升成高权限 artifact。

## 7. D 级：良性 skill creation 基础设施

- [Anything2Skill](https://arxiv.org/abs/2606.09316) 把文档、manual、对话、日志和轨迹编译为持久 SkillBank，是本项目最贴近的干净管线。其官方 AutoSkill 仓库截至检索日未检测到明确许可证，不能默认复制或再分发代码。
- [SkillX](https://arxiv.org/abs/2604.04804) 提供动态 skill extraction/routing；官方仓库为 MIT 许可证。
- [SkillsBench](https://arxiv.org/abs/2602.12670) 提供 86 个可验证 agent skill 任务；官方仓库为 Apache-2.0，可用作 deterministic task harness。
- [SkillAlchemy](https://arxiv.org/abs/2608.23417) 直接定义 source-grounded skill creation，是本项目需要跟进的最新良性基线。
- [SkillOS](https://arxiv.org/abs/2605.06614)、[Corpus2Skill](https://arxiv.org/abs/2604.14572)、[From Raw Experience to Skill Consumption](https://arxiv.org/abs/2605.23899) 和 [SkillCorpus](https://arxiv.org/abs/2607.15557) 分别覆盖 skill 系统、语料到 skill、skill 生命周期和数据资源。
- [SkillWeaver](https://arxiv.org/abs/2504.07079) 从网页探索中发现并磨炼可复用 skill。
- [AutoManual](https://papers.nips.cc/paper_files/paper/2024/hash/0142921fad7ef9192bd87229cdafa9d4-Abstract-Conference.html), NeurIPS 2024, DOI: [10.52202/079017-0019](https://doi.org/10.52202/079017-0019)，从交互轨迹构建可复用 manual。
- [Voyager](https://arxiv.org/abs/2305.16291) 是 executable skill library 的经典系统。
- [ExpeL](https://ojs.aaai.org/index.php/AAAI/article/view/29936), AAAI 2024, DOI: [10.1609/aaai.v38i17.29936](https://doi.org/10.1609/aaai.v38i17.29936)，从成功/失败轨迹提炼跨任务经验。

## 8. 防御文献与本项目的可守空间

简单做一个文本扫描器不够新。更有机会的方向是保留 resource → claim → trace → skill span → runtime action 的 lineage，并限制权限提升：

- [TMA-NM](https://arxiv.org/abs/2606.24322) 的 origin-bound authority 提醒我们，派生记忆不应拥有超过来源的权限。
- [PIPES](https://arxiv.org/abs/2608.12789) 研究 provenance 与先验信任。
- [PACT](https://arxiv.org/abs/2605.11039) 将 argument-level provenance 与 capability contracts 结合。
- [Progent](https://arxiv.org/abs/2504.11703) 提供可编程 privilege control。
- [RobustRAG](https://arxiv.org/abs/2405.15556) 提供面对少量 Byzantine retrieval evidence 的可证明鲁棒思路。

因此可贡献的不是笼统的 provenance，而是 **provenance closure for generated skills**：skill 中每条可执行规则追踪到独立来源集合；单一低信任来源不能授权副作用；source 删除或降级时，所有 descendant skills 自动重审、隔离或撤销。

## 9. 研究空位与严格表述

可以表述为：

> 我们测量一个此前未被系统刻画的 transfer function：攻击者控制未知混合语料中受来源身份约束的少量资源时，恶意语义经过自然竞争检索、良性任务执行和 skill compilation，最终成为 source-removed、agent-authored、可复用控制逻辑的概率。

不能表述为：

- “首个 agent skill poisoning 攻击”；
- “首个由文档/经验生成恶意 skill 的攻击”；
- “首个跨会话持久 agent 攻击”；
- “首个 skill 供应链攻击”；
- “证明任何少量污染都能控制 skill”。

真正的研究贡献应同时回答三个问题：

1. 在低预算、未知诚实池、natural retrieval 下，端到端风险是否仍非零且可复现？
2. 风险在 retrieval、uptake、compilation、routing 和 execution 哪一层被放大或衰减？
3. 哪种来源 admission、lineage 与 revocation 机制能阻断 data-to-control promotion，同时保持 clean utility？

若只完成第一个问题，像现有攻击的组合；完成前两个可形成强测量论文；三个都完成，才具有顶级安全/ML 论文的完整度。
