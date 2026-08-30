# 数据集、系统与代码复用建议

> 状态与许可证检查截止：2026-08-29。表中许可证指官方代码仓库当日可见的 repository license，不自动覆盖第三方网页、API 文档、模型权重、数据附件或外部资产；正式发布前仍需固定 commit 并做逐项 license audit。

> 更新：本文是宽口径组件盘点；其中把 τ `banking_knowledge` 作为首选的结论已被后续严格筛选取代。只讨论“纯 benign resource pool”的当前结论见[严格良性资源池筛选](09_strict_benign_resource_pools.md)：开放 PoC 先用 API-Bank，论文主环境用 AppWorld，跨域复制用 DocPrompting-CoNaLa 与 OR-ShARC。

## 1. 总体判断

目前没有一个成熟 benchmark 原生覆盖完整链：

```text
部分外部资源受攻击者控制
→ 良性任务中的竞争检索
→ 成功的良性执行轨迹
→ agent 自动创建 skill
→ 删除 source/memory
→ 新会话加载 skill
→ 规则化验证的无害 canary
```

因此不能“直接拿一个数据集跑完”。但每一段都有公开、可复用的组件。最稳妥的策略是发布一个薄的 orchestration layer 和新标注，而不是 fork 并重新分发所有上游数据。

## 2. 优先级最高的现成组件

| 组件 | 覆盖阶段 | 许可/状态 | 推荐用途 | 主要缺口 |
|---|---|---|---|---|
| [SkillJack code/data](https://github.com/Tencent/AI-Infra-Guard) | poisoned evidence → generated skill | Apache-2.0 | 最近邻攻击基线；复用其 skill artifacts/trajectory setup | 不是未知 honest pool 下的低预算自然检索 |
| [MPBench](https://github.com/Digital-Trust-Lab/mp-bench) | external context → memory/procedure write → later retrieval | Apache-2.0 | payload taxonomy、benign/adversarial pairs、Skill-Procedure Insertion | 主要是数据集，目标 context 常已直接提供 |
| [SkillX](https://github.com/zjunlp/SkillX) | trajectory/resource → skill extraction/routing | MIT | 第一个真实 skill creator/router | 需增加 resource-pool acquisition adapter 和执行级 verifier |
| [SkillsBench](https://github.com/benchflow-ai/skillsbench) | skill-enabled container tasks | Apache-2.0 | 86 个 deterministic-verifier 任务，适合做 deployment utility | 不原生提供受控 resource pool |
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) | benign tool tasks + attacker-controlled observation | MIT | utility/security 双指标、结构化状态和动态工具环境 | 原版是当轮 injection，没有 skill-write phase |
| [PoisonedRAG](https://github.com/sleeepeer/PoisonedRAG) | 少量文档 → competitive retrieval | MIT code；上游数据另计 | retrieval-optimized resource 作为强基线 | 目标是错误答案，不是程序性 skill |
| [AWM](https://github.com/zorazrw/agent-workflow-memory) | successful trace → textual workflow memory | Apache-2.0 | 接入成本最低的文本 skill compiler | workflow 权限/类型弱，需自己加 provenance |
| [ASI](https://github.com/zorazrw/agent-skill-induction) | trace → tested Python workflow skill | CC-BY-SA-4.0 | 第二个程序化、带 verifier 的 creator | ShareAlike 义务；正式使用前验证 skill 确实被加载执行 |

## 3. 任务环境与资源池候选

### 3.1 开箱即用：τ knowledge retrieval

[τ²-bench 当前仓库](https://github.com/sierra-research/tau2-bench) 采用 MIT 许可证。其后续 knowledge-retrieval 配置包含文档集合和 BM25/dense/rerank 等路径，很适合把 resource pool 显式拆成 unknown-clean 与 attacker-writable。

优点：

- 任务、policy、数据库和工具都可保持良性；
- 文档检索是一等组件，容易记录 exposure/rank；
- 结构化任务适合 state diff 和 unauthorized-action evaluator；
- 可以构造 acquisition/deployment task pairs。

风险：

- outcome evaluator 可能只检查目标状态，漏掉额外副作用；必须增加完整 action trace 和 state-diff verifier；
- 版本中的 knowledge/grading 修订可能改变可比性，需 pin commit、数据 hash 和版本；
- 新增 skill lifecycle 仍需工程集成。

### 3.2 稳定工具文档域：StableToolBench

[StableToolBench](https://github.com/THUNLP-MT/StableToolBench) 采用 Apache-2.0，并用 MirrorAPI 提供更稳定的模拟工具。API description、example 和 response 可以自然构成 resource pool。

它比原 [ToolBench](https://github.com/OpenBMB/ToolBench) 更适合可重复实验。ToolBench 代码为 Apache-2.0、规模大，但真实 RapidAPI 服务和第三方 API docs 已漂移，且第三方内容不一定受仓库许可证覆盖。

### 3.3 Web 域：BrowserGym + WebArena-Verified

- [BrowserGym](https://github.com/ServiceNow/BrowserGym) 提供统一浏览器环境；仓库内不同组件可能有独立许可，正式复用要逐组件检查。
- [WebArena](https://github.com/web-arena-x/webarena) 为 Apache-2.0；商品描述、论坛帖子和 wiki 页可作为离线、受控的 attacker-owned resource。
- [WebArena-Verified](https://github.com/ServiceNow/webarena-verified) 提供更可靠的任务/evaluator，适合作为后期外部有效性验证。
- [WorkArena](https://github.com/ServiceNow/WorkArena) 代码为 Apache-2.0，knowledge base → enterprise action 链路现实性高，但实例访问、版本和运行成本使其不适合 MVP。

Web 环境的主要陷阱是“最终页面状态正确”不代表过程安全。必须审计额外点击、发送、删除、下载和网络请求；本项目仍只允许本地 canary。

### 3.4 通用 agent 环境

- [AgentBench](https://github.com/THUDM/AgentBench)，Apache-2.0：有 OS、DB、KG、WebShop 等多域，但 resource pool 不是一等对象，适合补充泛化而非主实验。
- [AgentDojo](https://github.com/ethz-spylab/agentdojo)，MIT：97 utility tasks、629 security cases，最适合安全/效用双指标和 mock-tool integration。
- [DoomArena](https://github.com/ServiceNow/DoomArena)，Apache-2.0：可以在 BrowserGym、τ-bench、OSWorld 等环境中插入 adversarial environment layer，适合实现“攻击者控制部分 observation/resource”的 adapter。

## 4. 检索、RAG 与安全基准

| 数据/代码 | 许可与限制 | 本项目角色 |
|---|---|---|
| [PoisonedRAG](https://github.com/sleeepeer/PoisonedRAG) | MIT code；NQ、HotpotQA、MS MARCO 各有独立条款 | random/keyword poison 之外的 retrieval-optimized 强基线 |
| [PoisonArena](https://github.com/yxf203/PoisonArena) | 截止检索日未检测到明确 repo license | 借鉴 multi-attacker/competition 设计；未获许可前不复制或再分发 |
| [AgentPoison](https://github.com/AI-secure/AgentPoison) | MIT code；nuScenes、MIMIC/eICU 等数据需独立授权 | direct memory/KB write 强权限上界；优先用无受限数据的子设置 |
| [MINJA](https://github.com/dsh3n77/MINJA) | MIT | query-only memory poisoning 的不同攻击通道对照 |
| [InjecAgent](https://github.com/uiuc-kang-lab/InjecAgent) | MIT | overt IPI payload 与 transient attack baseline |
| [ASB](https://github.com/agiresearch/ASB) | MIT | 攻击 taxonomy、跨 agent 横向对照 |
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) | MIT | benign task + untrusted observation + security/utility evaluation |

[HotpotQA](https://hotpotqa.github.io/) 标注为 CC BY-SA 4.0；[MS MARCO](https://microsoft.github.io/msmarco/) 带非商业研究等独立条款。即使 PoisonedRAG 代码是 MIT，也不能把上游语料当作 MIT 数据重新发布。

## 5. Skill creation 与 skill library 候选

| 系统/数据 | 许可/状态 | 适配价值 | 风险 |
|---|---|---|---|
| [SkillX](https://github.com/zjunlp/SkillX) | MIT | 真实 extraction + routing；近期攻击论文也用，便于可比 | 需审计其 task-level proxy 与真实执行差距 |
| [Anything2Skill / AutoSkill](https://github.com/ECNU-ICALK/AutoSkill) | 截止检索日未检测到明确 license | 文档/manual/log/trajectory → SkillBank 与课题完全匹配 | 未获作者许可前，不复制、修改或再分发代码；可按论文 clean-room reimplement |
| [SkillsBench](https://github.com/benchflow-ai/skillsbench) | Apache-2.0 | deterministic verifier 和容器任务 | 是 skill-use benchmark，不是完整 creator |
| [AWM](https://github.com/zorazrw/agent-workflow-memory) | Apache-2.0 | 最快接入的 text workflow creator | artifact 易污染但缺少权限类型，需补 lineage |
| [ASI](https://github.com/zorazrw/agent-skill-induction) | CC-BY-SA-4.0 | Python workflow + generated tests；适合测 verifier blind spot | 许可证传播义务和当前集成成熟度需评估 |
| [SRA-Bench / SR-Agents](https://github.com/oneal2000/SR-Agents) | MIT code | 将 skill use 拆成 retrieval → incorporation → execution；有大量 distractors | 已有 skill pool，不含 agent 自主创建；web-collected content 许可另计 |
| [SkillRL](https://github.com/aiming-lab/SkillRL) | MIT | 分层 SKILLBANK 和动态更新 | GPU/RL 成本高，与参数更新混杂，不适合 MVP |
| [AFTER](https://github.com/DavydenkoGr/AFTER) | Apache-2.0 | held-out transfer、跨角色/跨模型 | 外部 resource retrieval 较弱，论文很新 |
| [SkillEvolBench](https://github.com/AIoT-MLSys-Lab/SkillEvolBench) | 截止检索日未见明确 license | acquisition → context shift → adversarial → composition split 值得借鉴 | 不默认复制或再分发 |
| [Voyager](https://github.com/MineDojo/Voyager) | MIT code | 经典 executable skill library | Minecraft 域重，第三方 MineDojo 数据多许可，不适合作主基准 |

`CRAFT`、`LATM` 等从任务创建工具的方法也有参考价值，但未见清晰许可证时只引用论文和重实现思想，不把代码并入可发布仓库。

## 6. 两套推荐组合

### 6.1 快速可行性组合

目标是两周内回答“链路能不能成立”，不追求生态规模：

1. **Resource pool：** API-Bank 的 73 条可运行 API descriptions；只索引 description 与参数 metadata。
2. **Attack resources：** 完全由本项目另行构造，不使用 MPBench payload 或 benign cases。
3. **Retriever：** 先复用 API-Bank `ToolSearcher`，再增加 BM25 作为结构不同的对照。
4. **Skill creator：** AWM 或 SkillX；另做一个简单、固定、可审计 compiler 作为机制对照。
5. **Task/verifier：** 使用 level-2/3 良性对话与可运行 API checker，增加本地无副作用 canary verifier。
6. **Baselines：** clean pool、matched placebo resource、forced retrieval 和 SkillJack direct-trajectory 上界。
7. **Isolation：** deployment 前清除 resource/context/memory，只保留 skill artifact。

这套组合为 Apache-2.0、工程最轻、因果解释干净。缺点是可运行 pool 只有 73 条，1 条注入约占 1.35%，因此只能作为 pilot。

### 6.2 顶会规模组合

主实验选择三个互补域，每个组件有清晰角色：

- **AppWorld：** 457 条 API docs + 750 个状态化良性任务；
- **DocPrompting-CoNaLa：** 34,003 条技术文档 + 代码执行子集；
- **OR-ShARC：** 651 条自然语言政策规则 + open retrieval。

使用两个主要 skill 形态：

- AWM/SkillX 的文本 workflow；
- ASI 或 clean-room creator 的程序化、带 verifier skill。

增加第三个 creator 做外部有效性，不一定进入完整 factorial。模型至少三个家族，builder 与 executor cross-swap。retriever 使用 BM25、dense、hybrid，另把 reranker 作为 screening 因素。

四类攻击基线：

- random/keyword contamination；
- overt IPI；
- PoisonedRAG-style retrieval optimization；
- direct trajectory/memory/final-skill attack 上界。

四类防御：

- provenance filtering；
- independent-source corroboration；
- capability/side-effect contract；
- descendant-aware revocation。

## 7. 新 benchmark 应发布什么

建议发布 **ResourcePoolBench**，但只发布本项目新增的安全、许可清楚的数据层和适配器：

- frozen clean resource-pool manifests 与 hashes；
- attacker/placebo resource deltas，不含可用于真实系统的 payload；
- independent-origin metadata；
- benign acquisition/deployment task pairs；
- resource → chunk → retrieval → trace → skill span → action lineage；
- no-op canary mock tools 和 deterministic verifier；
- build/deployment isolation harness；
- evaluation scripts、pre-registered splits 和 container images；
- 对受限制上游数据仅提供下载脚本/ID，不重新分发内容。

数据 split 应按 source family、task family、poison template 和时间同时隔离，避免近重复泄漏。攻击模板的 development/test 也要分离。

## 8. 许可与复现清单

正式写代码前逐项完成：

- [ ] pin 上游 commit/tag、record repository license；
- [ ] 区分 code license、dataset license、website content、model/API terms；
- [ ] 对无明确许可证的 AutoSkill、PoisonArena、SkillEvolBench 只引用，不复制；
- [ ] 对 CC-BY-SA 组件确认衍生数据/代码的 ShareAlike 范围；
- [ ] 对 HotpotQA、MS MARCO、MIMIC/eICU、nuScenes 等遵守各自条款；
- [ ] 不重新分发 web-collected distractors，除非逐项授权；
- [ ] container 中不打包真实 API credentials 或受限 assets；
- [ ] 生成 software/data bill of materials；
- [ ] 在 artifact appendix 写明每个实验所用数据版本和 hash。

## 9. 最终推荐

MVP 首选：**API-Bank 的纯 API-description pool + 自建攻击资源 + SkillX/AWM + 本地 deterministic verifier**。MPBench 不作为 resource pool，只作为 memory-poisoning related-work 对照。

论文主实验首选：**AppWorld API docs + SkillX/AWM 或程序化 creator**，再用 **DocPrompting-CoNaLa** 和 **OR-ShARC** 做跨资源类型复制；τ Knowledge 只保留为新基准 sanity check，Gorilla APIBench 只做 retrieval scaling。SkillJack、MPBench、PoisonedRAG、AgentDojo 分别作为 experience-to-skill、memory write、retrieval poisoning 和 current-run agent injection 的最近邻基线。

Anything2Skill 在概念上最匹配，但官方仓库未检测到明确许可证。除非获得作者授权，否则建议根据论文规格 clean-room 实现兼容基线，并在论文中透明说明。
