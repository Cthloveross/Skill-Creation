# 新颖性、论文定位与防御方向

## 1. 坦率判断

原始 framing：

> 攻击者污染 agent 查到的外部资料，agent 在良性任务中使用这些资料并生成 skill，skill 因而被攻击。

截至 2026-08-29，这个表述的新颖性大约只有 **4/10**。主要原因不是想法不可行，而是 [SkillJack](https://arxiv.org/abs/2608.03509)、[MPBench](https://arxiv.org/abs/2606.04329)、[PoisonedEvolution](https://arxiv.org/abs/2608.05563)、[Practice Makes Unsafe](https://arxiv.org/abs/2608.12851) 已分别覆盖 experience/document-to-skill、procedure write、bounded evidence-to-skill 与 full-lifecycle carryover。[SkillAlchemy](https://arxiv.org/abs/2608.23417) 又把开放世界资料到 source-grounded skill creation 正式化，使这个问题非常及时，也让审稿人更容易看出与近期工作的重合。

简单串联 PoisonedRAG 与 SkillJack 不足以构成顶会贡献。可守的核心必须变成一个更弱、更现实、可证伪的攻击者和一个该链路特有的系统问题。

## 2. 最可守的 novelty wedge

建议冻结成下面一句：

> 攻击者只控制未知混合 resource pool 中极少量、受独立来源预算约束的普通资料，不控制任务、轨迹、skill 或 ranking；这些资料必须在自然竞争检索中胜出，被良性执行实际采纳，再由良性 compiler 提升为持久 control logic，并在所有原资源和相关 memory 被移除后，于新会话造成执行级、无害、可验证的目标行为。

这条 wedge 有六个不可缺少的限定：

1. **unknown honest pool**：不是攻击者看过全部语料后精确拟合；
2. **origin-bounded low budget**：不是高污染比例或大量 sybil chunks；
3. **natural retrieval**：不保证进入上下文；
4. **benign tasks throughout**：构建和后续任务都不是恶意学习任务；
5. **source-removed persistence**：不是 RAG/memory replay；
6. **execution-level verification**：不是只在 artifact 中找到关键词或测 routing proxy。

去掉其中任意两三项，都会明显靠近已有论文。

## 3. 三种论文 framing

### A. Control-Plane Compilation Poisoning

候选题目：

> **From Search Results to Control Policy: Poisoning Source-Grounded Agent Skill Compilation**

视角：skill creator 是 compiler。不可信 data-plane evidence 被错误提升为 persistent control-plane policy。

适合：USENIX Security、CCS、NDSS 的攻击 + 系统防御叙事。

风险：如果防御只是扫描 prompt，审稿人会认为是普通 IPI；必须做 lineage、authority 和 source removal。

### B. Byzantine Source-to-Skill Synthesis（推荐主线）

候选题目：

> **Byzantine Skill Synthesis under Partial and Unknown Resource Control**

视角：resource pool 中至多 (ho) 个 sources 是 Byzantine，研究 retrieval + synthesis 在什么条件下稳健，污染阈值如何随 top-k、source diversity、冲突证据、compiler 和 router 改变。

适合：NeurIPS/ICLR 的鲁棒学习 + benchmark，也能投安全会议。

优势：即使攻击在现实低预算下失败，也能产出 failure surface、鲁棒 admission 条件或近似保证；科学问题不依赖“必须打出高 ASR”。

### C. Skill Bill of Materials 与 descendant-aware revocation

候选题目：

> **Generated Skills Need a Bill of Materials: Lineage-Preserving Compilation and Descendant Revocation**

视角：resource → extracted claim → skill instruction/code → runtime action 全链路保留 lineage。来源被删除、降级或发现冲突时，所有 descendant skills 自动重审或撤销。

适合：系统安全论文。攻击是揭示 lifecycle gap 的工具，主要贡献是 provenance closure 和 revocation。

风险：generic provenance、capability contracts 和 origin-bound authority 已有相邻工作；必须证明为 generated skill lifecycle 定制后的独特机制和效果。

### 推荐组合

论文主 framing 用 **B**，系统贡献用 **C**，攻击叙事用 **A**。这样不会把成败压在某个 payload 上：

```text
科学问题：Byzantine sources 下 skill synthesis 是否稳健？
测量工具：control-plane compilation poisoning
系统答案：lineage-preserving compilation + descendant revocation
```

## 4. 可以主张与不能主张的贡献

### 可以主张，但需实验支持

- 首次系统测量 bounded unknown resource control 经 natural retrieval 到 generated skill 的完整风险传递函数；
- 第一个同时隔离 retrieval、uptake、compilation、routing 和 execution 的 source-removed benchmark；
- 第一个按 independent origins 而非只按 chunks 约束 resource-to-skill attacker 的评测；
- 第一个为 generated skills 实现 span-level lineage closure 与 descendant-aware revocation 的系统；
- 在多个 retriever、creator、model family 和 task domain 上发现稳定的污染阈值或 scaling law。

“首次”只在最终投稿前再次检索确认，并严格限定到完整属性组合。

### 不能主张

- 首个 skill poisoning；
- 首个 experience/document-to-skill backdoor；
- 首个 persistent agent attack；
- 首个 memory poisoning 或 indirect prompt injection；
- 首个 malicious skill/supply-chain attack；
- 首个 provenance 或 capability control；
- 任意少量资源都足以控制任何 agent。

## 5. 顶会级贡献包

一个完整论文最好包含四项：

### C1：形式化与 taxonomy

定义 attacker budget、unknown pool、natural exposure、source-removed persistence 和联合 E2E success。严格区分 RAG、IPI、memory、trajectory 和 final-skill attacks。

### C2：ResourcePoolBench

至少三个域、两种 skill representation、三类 retriever、多个 model/creator block；发布 paired placebo、origin metadata、lineage 和 deterministic canary verifier。

### C3：端到端测量与规律

不仅报 ASR，还给出 exposure→uptake→compile→route→execute 的 transfer function、污染阈值、最差域、held-out pool 风险和 clean-utility frontier。

### C4：Authority-Preserving Skill Compilation

至少包含：

- executable rule 的 source lineage；
- independent-origin quorum；
- capability non-amplification；
- leave-one-source-out counterfactual checks；
- source revocation 对 descendants 的自动传播。

防御需在 static 和 adaptive-but-inert attack 下显著降低 E2E risk，同时 clean utility 损失控制在约 5 个百分点以内。

## 6. 防御的核心不变量

可以把系统原则写成：

> 由不可信 evidence 派生的 skill，不应仅因“被模型总结过”就获得更高 authority。

对于每条 skill rule (r)，定义支持来源集合 (O(r))、来源信任 (a(o)) 和所需能力 (cap(r))。一个简化的 admission 条件是：

\[
allow(r) =
independent(O(r)) \land |O(r)|\ge m
\land cap(r) \preceq \bigvee_{o\in O(r)} a(o)
\land test(r)=pass
\]

这里不是让外部文档“授权”真实权限，而是防止单一低信任来源独自引入新的 side-effect class。系统 policy/人工批准仍是高风险能力的唯一 authority source。

source (o) 被 revoke 后：

\[
Affected(o)=\{s:\exists r\in s, o\in O(r)\}
\]

所有 (Affected(o)) 进入 quarantine、recompile 或 revoke，直到剩余独立证据和 tests 重新满足 admission。

## 7. 审稿人最可能的拒稿理由与预防

| 拒稿理由 | 预防证据 |
|---|---|
| “这就是 SkillJack” | unknown pool、natural retrieval、origin budget、source-removed execution、matched causal interventions |
| “这就是 PoisonedRAG + persistence” | 与 one-shot RAG/memory 同 exposure 对照，证明 generated skill artifact 的必要性和 amplification |
| “只是 indirect prompt injection” | weak-signal procedural misinformation 单列；移除 imperative language 的 ablation |
| “攻击设置不现实” | 1–3 origins、不见 honest pool、无 rank feedback、held-out pools 和自然 miss 全部计入主结果 |
| “指标夸大” | 联合 E2E outcome、placebo-adjusted risk difference、skill-build cluster、deterministic verifier |
| “只对一个 prompt/model 有效” | 多 template、creator、model family、domain，leave-one-family-out |
| “防御是老套 provenance” | rule/span-level closure、authority non-amplification、descendant revocation 与自适应评测 |
| “artifact 不可复现” | frozen manifests/hashes、mock tools、container、lineage、许可清楚的 release |
| “双重用途风险过高” | 仅本地 no-op canary、不发布真实 ranking optimization/payload recipe、禁网和完全可逆环境 |

## 8. 预期结果的三条论文路径

### 路径 1：现实低预算下攻击成立

若 1–3 origins 在 natural retrieval 下产生稳定、跨系统的 source-removed E2E risk，主线是攻击 + amplification + defense。这是最直接的安全会议论文。

### 路径 2：只在某些边界条件成立

若结果主要由 pool size、source diversity、retriever 或 compiler 决定，主线改为 empirical scaling law 和 risk surface。重点是哪些系统条件导致低权限 evidence 被提升。

### 路径 3：现实设置下攻击基本失败

若 forced inclusion 成功而 natural retrieval 失败，或 multi-source conflict 很容易阻断，主线转为 negative measurement / robust admission：近期直接 trajectory studies 可能高估自然资源池风险，并给出足够条件和可复现边界。

三条路径都能产出论文；前提是 pilot 前写好失败标准，不在结果出来后移动 threat model。

## 9. 会议定位

- **USENIX Security / CCS / NDSS：** 需要清晰 threat model、真实系统、攻击链、执行级危害 proxy、强 defense 和 artifact；最匹配 A+C。
- **NeurIPS Datasets & Benchmarks：** 需要 benchmark 规模、数据治理、可重复 verifier、广泛模型/系统测量；最匹配 B。
- **NeurIPS/ICLR main：** 仅攻击通常不够；需要 Byzantine synthesis 的一般方法、理论或强 empirical law。
- **ACL/EMNLP：** 若重点是 instruction/data distinction、procedural knowledge uptake 和跨语言/文本条件，可以作为较窄版本，但仍须正面对比 MPBench/IPI。
- **TMLR：** 适合完整、严谨但周期较灵活的系统测量。

“顶刊级”更现实的路线是先做高质量 conference artifact，再扩展长期评测、形式化保证或真实系统部署研究，而不是一次性把范围铺到所有 agent。

## 10. 候选摘要骨架

> Agents increasingly compile retrieved documents and successful trajectories into reusable skills. This creates a promotion boundary: low-authority external evidence may become persistent control logic. We study skill synthesis when an adversary controls only a bounded number of sources in an otherwise unknown resource pool, while the agent, build task, future tasks, retriever, and compiler remain benign. Our benchmark isolates five gates—retrieval, uptake, compilation, routing, and execution—and evaluates source-removed carryover using harmless, deterministic canaries. Across [systems/domains], we characterize when competitive retrieval attenuates or amplifies poisoning and compare generated skills with one-shot RAG, persistent memory, poisoned trajectories, and directly supplied skills. We then introduce [defense], which preserves rule-level provenance, requires independent-source support for side-effecting procedures, and revokes descendant skills when evidence changes. The results establish [supported finding] while retaining [utility result].

方括号必须由 confirmatory results 填写，不能在 pilot 前预写胜利性结论。
