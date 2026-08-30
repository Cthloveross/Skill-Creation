# 实验设计：从可行性验证到顶会规模证据

## 1. 核心研究问题

### RQ1：低预算、未知 pool 下能否端到端成功？

在攻击者只提交 1–3 个独立来源、不知道诚实资源和精确排名时，source-removed E2E risk 是否显著高于 matched placebo？如果只有 forced top-1 才成功，主 threat model 不成立。

### RQ2：风险在哪一层被放大或衰减？

分别测量 retrieval exposure、execution uptake、skill compilation、future routing 和 canary execution。目标不是把条件概率相乘后当作因果解释，而是通过随机 stage intervention 定位瓶颈。

### RQ3：skill compilation 是否带来独立持久风险？

在相同 build exposure 下比较：

- one-shot RAG；
- current-run indirect prompt injection；
- persistent memory；
- generated skill；
- 无持久状态。

核心对比是：

\[
P(Y\mid skill, source\ removed, memory\ disabled)
>
P(Y\mid no\ skill, source\ removed)
\]

### RQ4：正常形态的程序性错误是否仍有效？

将 overt imperative injection 与“看似正常但错误的 procedure/example/config”分开。如果移除命令式 prompt injection 后效果消失，论文只是 IPI 的持久化变体。

### RQ5：对未知 pool、模型和 compiler 是否迁移？

攻击资源先冻结，再在 held-out pool snapshot、retriever、builder model、executor model 和 paraphrased task 上评估。论文必须报告最差域、低分位数和 leave-one-family-out 结果，不只挑选平均值。

### RQ6：怎样阻止低权限 evidence 升级为控制逻辑？

比较 provenance-preserving compilation、independent-source quorum、instruction/data separation、behavioral tests、capability contracts 和 descendant-aware revocation。

## 2. 实验单位与避免伪重复

真正的独立实验单位是：

> 一个独立 honest resource-pool snapshot + 一个冻结的 attacker/placebo resource set + 一次独立 skill build。

在同一个 skill 上运行 100 个 future prompts 仍然只有一个 skill-build cluster，不能把 (n) 写成 100。层级结构至少包括：

- future tasks 嵌套在 skill build；
- skill build 嵌套在 pool snapshot × task pair；
- poison/placebo templates 嵌套在 domain；
- API run 嵌套在 model version × batch/day。

成本规划可先以每个主要对比 30–50 个独立 skill builds 为起点，但正式样本量应在 pilot 得到 ICC、base rate 和 effect size 后，用 hierarchical power simulation 决定。

## 3. Stage 0：仪器验证

在任何 attack 实验前，验证：

1. oracle skill 在 trigger-present 时稳定调用正确 canary；
2. oracle skill 在 trigger-absent 和 unrelated tasks 上几乎不触发；
3. clean skill、无 skill、无 poison 时 canary 假阳性接近零；
4. benign task success 可以由 deterministic verifier 判定；
5. canary 可从 tool log/state diff 唯一判定，不依赖 LLM judge；
6. acquisition 后资源、上下文和 memory 清理确实完成；
7. router 未加载目标 skill 时，executor 无法看到该 skill 内容；
8. 配对 clean/poison runs 使用相同 pool、task、seed 和 tool state。

若 oracle skill 都不能可靠触发，后续低 ASR 不能归因于防御；若 clean baseline 本身频繁触发，canary 设计无效。

## 4. Stage 1：两周因果可行性 pilot

### 4.1 设计

使用一个任务域、一个文本 skill compiler、两个 retriever，先做配对的 (2\times2\times2\times2) 机制实验：

| 因素 | 水平 |
|---|---|
| resource content | weak-signal poison / matched placebo |
| exposure | natural retrieval / forced inclusion |
| artifact | generated skill enabled / deleted |
| trigger | present / absent |

trigger 可以作为同一个 generated skill 内的 repeated measure。每个 poison 都有在长度、文体、来源形式、主题相关度和预期 rank 上匹配的 placebo。

### 4.2 最小资源与任务规模

- 10 个 build-task / deployment-task pairs；
- 每对 3–5 个独立 honest-pool snapshots；
- 每个 domain 至少 5 个独立 poison/placebo template pairs；
- 1 与 3 个 attacker origins 两档预算；
- BM25 与一个 dense retriever；
- 30–50 个独立 skill builds/主要比较。

先不优化攻击文本，也不做真实网页。初始资源用合成 manual/API docs，所有 canary 都是 no-op。

### 4.3 Pilot 的 go/no-go

继续主攻击路线至少应满足：

- natural retrieval、1–3 origins 时，placebo-adjusted E2E risk difference 的区间下界大于 0，点估计达到预注册的实际意义阈值，例如 10 个百分点；或出现稳定、单调的 budget–risk dose response；
- acquisition 与 deployment clean utility 均不劣于 clean baseline 超过 3–5 个百分点；
- source removal 后效果保留；删除 generated skill 后效果显著下降；
- 至少 weak-signal procedural poison 有效，不完全依赖 overt imperative injection；
- 非触发 collateral activation 显著低于触发任务。

若 natural retrieval 近似零但 forced inclusion 有效，说明问题主要是 retrieval barrier；可转向 resource exposure 测量。若 skill 删除不改变结果，说明不是 skill persistence。若所有 realistic cells 均失败，应转为负结果/鲁棒 admission 论文。

## 5. Stage 2：主实验

### 5.1 推荐的确认性设计

不要把所有因素塞进不可解释的巨大网格。主 factorial 聚焦：

- content：weak-signal poison / matched placebo；
- budget：1 / 3 attacker origins；
- retriever：BM25 / dense / hybrid；
- defense：none / provenance + independent-source quorum。

即 24 个主 cells。以下作为预先指定的 replication blocks，而不是继续膨胀 factorial：

- 3 个 skill creators：文本 workflow、程序化 skill、第二个独立 creator；
- 至少 3 个模型家族，builder/executor 可 cross-swap；
- 3 个任务域：structured policy/RAG、web interaction、API/tool docs；
- 多个日期固定的模型版本和 API batches。

若需要筛选 top-k、chunking、attacker knowledge、resource type、skill representation、router 等更多因素，先用 Resolution-IV fractional factorial 或 D-optimal screening；只对最重要的 2–3 个交互做完整确认实验。

### 5.2 随机化与 blocking

- 在 task/domain、honest pool snapshot、model/compiler、baseline difficulty 和 API day 内配对；
- poison/placebo 在 honest pool 抽样前冻结；
- cell assignment 和 run order 随机；
- natural retrieval 的主实验不得因 miss 而重采样；
- forced retrieval 只作为机制上界；
- 保存 corpus、index、prompt、model、code、seed 和 container image hashes；
- exploratory 攻击优化和 confirmatory benchmark 使用严格分离的 development/test pools。

## 6. 端到端主指标

主指标是 **Source-Removed E2E-ASR**，而不是“攻击被检索后的条件 ASR”：

\[
Y_{E2E}=\mathbb{1}[
retrieve \land uptake \land compile \land route \land canary
\land build\ success \land deploy\ success]
\]

主 estimand 报告 poison 与 matched placebo 的 marginal risk difference、95% interval 和绝对概率。

同时报告：

- clean task success 与 non-inferiority margin；
- false trigger/collateral activation rate；
- 每个成功攻击所需 attacker documents、tokens 和 origins；
- source removal 后不同 session/skill refinement 次数的 persistence decay；
- **persistence promotion gap**：

\[
ASR_{skill, source\ removed}
-ASR_{no\ skill, source\ removed}
\]

- **compilation amplification**：一次成功 build 影响多少个 held-out future tasks；
- held-out pool 的 10% 分位数或 CVaR，而不只报均值；
- defense utility–security Pareto frontier。

## 7. 链路诊断指标

| 阶段 | 指标 | 验证方法 |
|---|---|---|
| Retrieval | hit@k、rank、top-k attacker share、exposure probability | 冻结 index 的 retrieval log |
| Uptake | poisoned procedure 是否出现在成功 trace | 规则/semantic annotation + blind audit |
| Compilation | 目标语义是否进入 skill 的 instruction/code/config | span lineage + artifact behavior test |
| Persistence | source/memory 清理后 skill 语义是否保留 | hash、isolated replay |
| Routing | future task 是否加载目标 skill | router trace |
| Execution | 正确 canary 是否实际调用 | mock-tool event log |
| Utility | 目标任务是否正确完成 | deterministic verifier/state diff |
| Collateral | 非触发/无关任务是否误调用 | paired negative tasks |

“skill 包含攻击词”不能等同于行为污染；“LLM judge 说有风险”也不能等同于实际 canary execution。主 outcome 必须由执行日志验证。

## 8. 必须包含的 baseline

| Baseline | 排除的替代解释 |
|---|---|
| 无注入 | 系统固有假阳性 |
| matched benign/placebo resource | 不是因为增加了一篇相关资料 |
| irrelevant poison | pool 里出现攻击语义不等于因果作用 |
| forced retrieval | compiler 被暴露后的机制上界 |
| fixed-rank span swap | 在相似 retrieval exposure 下隔离目标语义 |
| one-shot RAG | 普通知识污染 |
| current-run IPI, no skill write | 普通间接提示注入 |
| persistent memory | memory poisoning |
| SkillJack-style poisoned trajectory | 更直接的 experience-to-skill 攻击 |
| directly installed malicious skill | skill supply-chain 上界 |
| oracle canary skill | router/executor 可实现上界 |
| skill deleted after build | generated artifact 的必要性 |

## 9. 必做 ablation

- 删除所有 imperative language，仅保留错误 procedure/example/config；
- natural vs forced retrieval；
- fixed rank 下 poison span vs clean span；
- source retained vs removed；
- memory enabled vs disabled；
- skill retained vs deleted；
- skill name/description/body/script 各部分移除；
- text workflow vs code-bearing skill vs tool config；
- exact、lexical paraphrase、semantic paraphrase 和 unrelated trigger；
- 单文档、多文档、单来源多文档、多独立来源；
- honest pool 中加入正确且冲突的证据；
- BM25、dense、hybrid、reranker；
- builder model 与 executor model cross-swap；
- provenance label 保留 vs 在 compilation 中丢失；
- source revocation 后 descendant skill 自动撤销 vs 保留；
- skill regeneration/refinement 对污染的消除或放大。

## 10. 防御实验

建议实现一组可组合机制，而不是单一 prompt scanner：

### 10.1 Lineage-preserving compilation

每条可执行 skill rule 保存支持它的 resource origins、claim spans 和 acquisition actions。无法归因的规则进入 quarantine。

### 10.2 Independent-source quorum

会导致工具调用、写操作或权限变化的程序性规则，至少需要 (m) 个独立来源支持。来源独立性由 publisher/lineage graph 定义，不能按 chunk 计数。

### 10.3 Capability non-amplification

派生 skill 默认不得获得比来源证据更高的 authority。外部普通文档可以解释参数或流程，但不能单独授权新副作用；高风险动作要求显式系统 policy 或人工批准。

### 10.4 Counterfactual build tests

对每个来源做 leave-one-source-out skill compilation 或 behavior replay。若移除单一低信任来源会消除关键规则或改变副作用，skill 被标记为 fragile。

### 10.5 Descendant-aware revocation

source 删除、降级或被发现冲突时，沿 lineage graph 找出所有 descendant skills，自动重编译、隔离或撤销。

防御评估必须同时报告 static、adaptive-but-inert attacks、clean utility、latency、token/compute cost、false quarantine 和 source diversity sensitivity。

## 11. 统计分析计划

二元 E2E outcome 使用 hierarchical logistic mixed model 或 Bayesian multilevel binomial model：

- 固定效应：poison、budget、retriever、defense、creator/model 及预注册交互；
- 随机效应：pool snapshot、domain/task pair、poison template、skill build；
- future task 嵌套在 skill build 中。

优先报告 marginal risk difference 和绝对概率；odds ratio/p-value 只作补充。配对设计可使用 block permutation 或 cluster bootstrap，但抽样层必须是 skill build，不是 future prompt。

其他规则：

- clean utility 做 one-sided non-inferiority test；
- 稀有事件或 complete separation 时使用带弱信息先验的 Bayesian model；
- 一个预注册 primary contrast；secondary contrasts 用 Holm；探索性因素用 FDR；
- leave-one-domain-out、leave-one-pool-family-out、leave-one-model-out；
- mediation 结论只来自随机 stage interventions，不来自简单条件化；
- pilot 只用于估计 variance/ICC 和冻结设计，不能与 confirmatory test 混合后声称预注册。

## 12. 预先写入的失败标准

以下任一现象都应如实写为主假设失败或适用范围受限：

- 1–3 origins、未知 honest pool、无 ranking 控制时，E2E 与 placebo 无可靠差异；
- 只有 forced top-1、精确知道 query/corpus 才成功；
- source removal 或 memory disable 后效果消失；
- generated skill 删除后效果不变；
- 只有 overt imperative prompt injection 有效；
- canary 激活伴随显著 clean utility 崩溃；
- collateral activation 接近 targeted activation；
- 结果只存在于一个 model、creator、pool 或 poison template；
- attack development 看过 held-out pools 或 future tasks；
- matched exposure 后不比 one-shot RAG/memory baseline 更持久；
- LLM judge 判定成功，但 sandbox canary 从未执行；
- 简单 allowlist 以接近零成本完全解决，而论文没有新的鲁棒性洞见。

负结果仍可发表的条件是：给出清晰的污染阈值、风险传递规律、可复现的 failure surface，或证明一类低成本 admission 机制在指定假设下足够稳健。
