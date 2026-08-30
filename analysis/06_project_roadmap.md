# 项目路线图：先证伪，再扩成完整论文

## 1. 项目目标

项目不应以“制造高 ASR payload”为目标，而应回答一个可证伪的系统问题：

> 当攻击者只能控制未知混合资源池中少量独立来源，而 agent、任务、检索器和 skill creator 都良性时，外部 evidence 被提升为持久控制逻辑的风险有多大；风险在哪一层产生；哪些 admission 与 revocation 机制足以阻断它？

最终可交付物应包括：

- 一套明确且弱权限的 threat model；
- 一个可复现的 ResourcePoolBench；
- 至少两个不同 skill creators 和三个任务域的结果；
- 完整因果链与统计分析；
- 一个 provenance/authority-aware 防御；
- 只使用本地无副作用 canary 的安全 artifact；
- 一篇面向安全或 ML 顶会的论文。

## 2. Phase 0：范围冻结与复现准备（第 1 周）

### 任务

- 冻结 primary threat model、out-of-scope、canary 和 go/no-go threshold；
- 建立文献表，逐项记录与 SkillJack、MPBench、PoisonedEvolution、Practice Makes Unsafe 的差异；
- 选择一个主 task domain、一个 text creator、BM25 + dense retriever；
- pin 所有上游 commit、许可证、模型版本和 container image；
- 定义 resource、origin、chunk、trace、skill rule 和 action 的统一 schema；
- 预先写好 acquisition/deployment state reset protocol。

### Exit criteria

- oracle canary、clean verifier、router log 和 source removal 都有自动测试；
- 任何实验都无法访问公网或真实 secret；
- paired poison/placebo 数据结构已确定；
- primary outcome 和样本单位已写进 preregistration 草案。

## 3. Phase 1：两周可行性 pilot（第 2–3 周）

### 实现范围

- 10 个 acquisition/deployment task pairs；
- 30–50 个独立 skill builds/主要比较；
- 1/3 origins；
- poison/placebo、natural/forced retrieval、skill enabled/deleted、trigger present/absent；
- 一个文本 creator + 一个简单可审计 creator；
- deterministic canary 与 task verifier。

### 必须输出的图表

- 端到端 funnel：retrieval → uptake → compilation → routing → action；
- natural vs forced retrieval 的 paired risk difference；
- source retained/removed 与 skill retained/deleted 的因果对照；
- clean utility 与 collateral activation；
- 按 pool snapshot 和 template 展开的分布，而不只报均值。

### Decision Gate A

**继续 attack-centered 路线：** natural retrieval 的 placebo-adjusted E2E risk 有实际意义，且 skill deletion intervention 证明 artifact 必要。

**转 measurement/defense 路线：** forced exposure 有效但 natural exposure 很低，或 multi-source conflict 很容易阻断。

**停止当前设计：** oracle/clean instrumentation 不可靠，或所谓成功无法与 RAG/memory 区分。

## 4. Phase 2：Benchmark 工程（第 4–7 周）

### 三个域

1. stateful tool use：AppWorld API docs；
2. technical documentation：DocPrompting-CoNaLa；
3. natural-language policy：OR-ShARC。

若资源有限，先完成 AppWorld 主实验和 OR-ShARC 轻量复制；DocPrompting 先做 retrieval-scaling subset。

### 两种 skill 形态

- textual workflow：AWM 或 SkillX；
- programmatic workflow：ASI 或 clean-room creator。

### 需要新增的数据资产

- clean pool manifests 与 source identity graph；
- paired poison/placebo deltas；
- acquisition/deployment task pairs；
- trigger-present、semantic paraphrase、trigger-absent 与 unrelated tasks；
- rule/span lineage annotation；
- deterministic action/state verifiers；
- frozen development、validation、confirmatory splits。

### Decision Gate B

- 至少两个 creators、两个 domains 能完整运行；
- source removal、memory clearing、skill-only deployment 有自动审计；
- end-to-end result 不依赖单一 template；
- 上游 license audit 通过，可公开部分明确。

## 5. Phase 3：筛选与主假设冻结（第 8–9 周）

用 Resolution-IV fractional factorial 或 D-optimal design 筛选：

- top-k；
- chunk size/overlap；
- resource type；
- attacker knowledge；
- retriever/reranker；
- skill representation；
- conflict evidence；
- source diversity；
- builder/executor mismatch。

只用 development pools。根据筛选结果冻结 2–3 个关键交互和最终 primary factorial。此后不得再根据 confirmatory results 修改 payload、threshold 或 benchmark split。

### Decision Gate C

- hierarchical power simulation 完成；
- sample size、randomization、blocking、primary contrast、non-inferiority margin 全部冻结；
- static attacks 冻结；adaptive attack 预算单独定义；
- 统计分析脚本可对 synthetic null data 正确控制 error rate。

## 6. Phase 4：防御系统（第 8–12 周，可与 Phase 3 并行）

实现最小闭环：

1. resource/claim/skill-rule/action lineage；
2. source-independence graph；
3. side-effecting rule 的 evidence quorum；
4. capability non-amplification；
5. leave-one-source-out counterfactual build test；
6. source revoke → affected descendants → quarantine/rebuild。

防御不是只追求低 ASR，还要测：

- clean task success；
- build/deployment latency；
- token/compute cost；
- false quarantine；
- 对单来源正确文档的伤害；
- adaptive-but-inert attacker；
- source conflict 与 provenance 缺失时的 degradation。

## 7. Phase 5：Confirmatory run（第 13–16 周）

### 推荐主设计

- content：weak-signal poison / matched placebo；
- budget：1 / 3 origins；
- retriever：BM25 / dense / hybrid；
- defense：off / on；
- creators/models/domains 作为预注册 replication blocks；
- trigger present/absent 为 skill-build 内 repeated measure。

### 运行纪律

- 保存每次 run 的 immutable manifest；
- 失败、timeout、retrieval miss 全部进入 intent-to-treat 主分析；
- 不能只重跑“不听话”的模型；
- API/model version 改变时新开 block，不混入旧 block；
- blind audit 一部分 skill artifacts 和 action logs；
- confirmatory set 上不再人工改 poison 或 defense。

### Decision Gate D

根据预注册规则选择论文路径：

- attack + defense；
- scaling law/measurement + defense；
- negative result + robust admission conditions。

## 8. Phase 6：论文与 artifact（第 17–20 周）

### 论文结构

1. Introduction：低权限 evidence 被提升为 control logic；
2. Related Work：正面对比 SkillJack/MPBench/PoisonedEvolution；
3. System & Threat Model；
4. ResourcePoolBench；
5. Causal Measurement；
6. Defense Design；
7. Confirmatory Evaluation；
8. Adaptive Evaluation & Ablations；
9. Limitations, Ethics, Responsible Release；
10. Artifact Appendix 与完整 license/data statement。

### Artifact

- 离线 mock 环境；
- no-op canary；
- frozen pool manifests 和下载脚本；
- task/verifier；
- skill creators 的 adapters；
- lineage and revocation implementation；
- analysis notebook/script；
- 一键复现小规模结果的 container；
- 不含真实 payload 优化、真实账号、外部 endpoint 或受限数据。

## 9. 建议仓库结构

```text
Skill-Creation/
├── README.md
├── analysis/
├── configs/
│   ├── threat_models/
│   ├── retrievers/
│   ├── creators/
│   └── experiments/
├── data/
│   ├── manifests/
│   ├── synthetic_resources/
│   ├── task_pairs/
│   └── lineage/
├── src/
│   ├── resource_pool/
│   ├── retrieval/
│   ├── agents/
│   ├── skill_compilers/
│   ├── sandbox/
│   ├── canary/
│   ├── defenses/
│   └── evaluation/
├── tests/
├── experiments/
│   ├── pilot/
│   ├── screening/
│   └── confirmatory/
├── artifacts/
└── LICENSES/
```

先不要创建上述代码骨架，直到 Phase 0 的主环境、creator 和 schema 冻结；否则容易在多个不兼容 benchmark 上同时做浅层集成。

## 10. 团队分工建议

- **Literature/positioning：** 每周跟踪 2026 skill safety 新论文，维护 claim matrix；
- **Environment/data：** resource pool、task pairs、origin graph、license；
- **Agent/skill systems：** creator adapters、router、state reset；
- **Security/evaluation：** canary、verifier、threat model、attack baselines；
- **Defense：** lineage、quorum、capability、revocation；
- **Statistics/reproducibility：** randomization、power、mixed model、immutable manifests。

每个模块至少两人交叉审查。特别是 attack success、state reset 和 license audit 不能只由实现者自查。

## 11. 主要风险与缓解

| 风险 | 早期信号 | 缓解 |
|---|---|---|
| 与新预印本继续撞题 | 相同 unknown-pool/natural-retrieval setting 出现 | 将核心转向 Byzantine robustness、lineage closure 与 revocation |
| natural retrieval 几乎不暴露 attacker source | forced 成功、natural miss | 研究 retrieval barrier/scaling law，不提高攻击者权限来“救”结果 |
| artifact 只是复制 IPI 文本 | 删除 imperative language 后 ASR 归零 | 聚焦程序性错误、代码模式、conflicting evidence 和 admission |
| verifier 漏掉副作用 | task pass 但 action log 异常 | 双 verifier：goal completion + unauthorized action/state diff |
| 样本量被 future prompts 虚增 | 同一 skill 上大量 queries | 按 skill-build cluster 设计和 bootstrap |
| API 模型漂移 | 同配置跨日突变 | pin dated version、按 batch/day blocking、保存 raw traces |
| 防御损害 utility | 单一正确来源被大量拒绝 | 风险分级 quorum、quarantine/review、报告 Pareto frontier |
| 上游许可不清 | repo 无 LICENSE 或含 web-collected assets | clean-room reimplementation、只发 IDs/download scripts、作者授权 |
| 双重用途风险 | 需要真实排名优化或外部 endpoint 才能验证 | 保持合成离线 canary，不发布 operational recipe |

## 12. 现实时间判断

- **2–3 周：** 可以得到可信的 feasibility/negative pilot；
- **8–12 周：** 可以完成两个域、两个 creators 的 benchmark 与初版防御；
- **4–5 个月：** 在工程和算力稳定的情况下，可完成 confirmatory study、artifact 和一篇顶会级投稿；
- **顶刊扩展：** 再增加长期 skill evolution、形式化 guarantee、真实但授权的企业环境或跨时间模型漂移研究，通常还需额外一个研究周期。

最省时间的选择不是马上“做攻击”，而是先把 SkillJack/MPBench 无法回答的自然检索与 source-removed 因果链做成一个无法被替代解释推翻的 pilot。
