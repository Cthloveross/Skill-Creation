# 严格良性资源池筛选

## 结论

符合课题要求的现成材料不止一个。若只选一个主环境，应选 **AppWorld 的 API documentation**：它把良性任务、API 文档、可执行应用、数据库状态和评测器分开，agent 还能按需查询文档；唯一明显问题是受保护数据公开再分发必须保持加密。若先做一个完全开放、工程最轻的 PoC，应选 **API-Bank**。若要做顶会规模的跨域结果，推荐 **AppWorld + DocPrompting-CoNaLa + OR-ShARC**，分别覆盖状态化工具任务、大规模技术文档和自然语言政策规则。

这里的“良性/纯资源”采用严格定义：clean pool 只包含原始文档、API schema、manual 或 policy text；不包含任务答案、gold calls、轨迹、memory、预制 skill、攻击标签或 MPBench case。任务和 evaluator 永远在资源池之外。DocPrompting 的原始手册虽不是攻击材料，却可能描述 `sudo`、包管理或网络命令，因此“内容无投毒”和“执行无风险”是两件事；所有代码实验仍需离线 sandbox 和低风险 allowlist。

## 筛选标准

一个候选只有同时满足以下条件，才进入主名单：

1. **资源可独立抽取。** 每条资源可以表示成 `resource_id / origin_id / title / body`，不携带 gold answer、expected action 或攻击字段。
2. **任务保持良性。** 注入 treatment 不修改用户指令、工具实现、初始数据库或任务成功条件。
3. **存在竞争检索。** agent 从共享池自然检索，而不是每题直接得到 gold 文档。没有原生检索的环境必须只加一层统一 BM25/dense index。
4. **有独立 verifier。** 最好能检查最终状态和额外副作用；只有文本相似度的候选不能单独支撑安全结论。
5. **攻击预算可解释。** 预算按独立来源 `origin` 计数，同时报告文档数与 chunk 数，不能把一个来源切成几十块再声称攻击者控制几十个来源。
6. **可以隔离持久性。** skill 创建后删除资源池、检索缓存、对话和 memory，只保留 skill artifact，再在新会话测试。

## 主选组合

### AppWorld

[AppWorld](https://doi.org/10.18653/v1/2024.acl-long.850) 是最强的 agent-level 主环境，也是 ACL 2024 Best Resource Paper。官方环境包含 9 个日常应用、457 个 API、100 多张数据库表和 750 个自然语言任务；下载数据中，API 文档、任务、数据库和 ground-truth evaluator 分目录存放。`ApiDocs` helper 支持 agent 按需查询文档，`world.task.api_docs` 还能输出标准、function-calling 或 OpenAPI 表示。官方 evaluator 使用数据库状态单元测试，同时检查目标是否完成以及是否产生 collateral damage。

把 `data/api_docs/standard/*.json` 按 `app × api` 拆成 457 条 clean resources，再通过只读索引暴露给 agent，即可得到课题所需的 pool。攻击实验只往索引加入自有 overlay，不改官方 API implementation、task、DB 或 evaluator。1 个攻击资源约占池子的 0.22%，3 个约占 0.65%，已经能做低预算实验。Skill compiler 可先接 [SkillX](https://arxiv.org/abs/2604.04804) 或一个固定的审计型 compiler；SkillX 本身也把 AppWorld 作为 skill knowledge-base 的评测域，因此不会显得是为攻击临时拼出的玩具环境。

主要限制是发布方式。AppWorld 的 API docs、任务和 evaluator 属于 protected portion；它们采用 Apache-2.0 加额外条款，公开再分发及其衍生物必须保持加密。最稳妥的 artifact 是发布 overlay、doc IDs、hash、索引构建脚本和运行日志，不发布解密后的官方文档；正式投稿前应联系作者确认衍生 benchmark 的发布形式。

### API-Bank

[API-Bank](https://doi.org/10.18653/v1/2023.emnlp-main.187) 是最适合先动手的开放 PoC。EMNLP 2023 论文发布了 73 个可运行 API、314 段人工标注对话和 753 次 API 调用，并把能力明确拆成 Call、Retrieve+Call 与 Plan+Retrieve+Call。官方 `ToolSearcher` 直接对 API description 和参数 metadata 做语义检索，API 调用由各工具的 correctness checker 与数据库变化进行验证。子项目许可证是 Apache-2.0。

它的 clean pool 就是 73 条 API descriptions，不需要把对话、答案或调用轨迹放进去。我们只需在 embedding 前把攻击者资源作为额外文档加入；任务仍用原始 level-2/3 benign dialogues。这个设置对“资源被检索后，经成功执行形成 skill”的因果链很干净，且代码改动小。

缺点是池子偏小：1 条注入约占 1.35%。论文另有 2,138 个训练 API descriptions，但它们多为合成数据，也不都对应可运行 backend，不能假装成 2,138 个可验证工具。API-Bank 因而适合 PoC 和完全开放复现，不应独自承担“极低污染比例”的主结果。

### DocPrompting

[DocPrompting](https://arxiv.org/abs/2207.05987) 是最强的大池子与跨域复现。ICLR 2023 Spotlight 工作原生定义了“自然语言意图 → 从全局 documentation pool 检索 → 生成代码”。官方当前 Hugging Face release 中，`conala-docs.jsonl` 有 34,003 条 Python/库文档，`tldr-docs.jsonl` 有 439,064 条 manual chunks；每条资源只有 `doc_id` 与 `doc_content`。官方同时提供 BM25 和 dense retrieval，并为 CoNaLa 的 100 个 test examples 提供人工单元测试，报告 execution-based pass@k。

对本项目，优先使用 CoNaLa 并做低风险函数 allowlist：benign task 是自然语言代码意图，agent 检索文档、生成并在无网络容器内执行，通过单元测试后才允许编译 skill。1 条注入在 34,003 条文档中约占 0.003%，很适合研究污染预算和 retrieval rank，而 AppWorld 很难提供这种稀释规模。

它不是完整交互式 agent benchmark，且只有一部分 test examples 有执行式 unit tests；tldr 的主指标又以 exact match、F1 和 charBLEU 为主。因此 DocPrompting 应作为第二域或 retrieval-scaling 实验，不应替代 AppWorld 的状态化主结果。代码仓库为 Apache-2.0，Hugging Face 数据页标记 MIT；但 DevDocs、tldr pages 和各 Unix manuals 的上游许可并不天然统一，公开 frozen pool 前仍需逐源审计或只发布下载 manifest。

### OR-ShARC

[OR-ShARC](https://arxiv.org/abs/2102.08633) 是最纯的自然语言政策域。它把原 ShARC 每题直接给出的 gold rule snippet 删除，要求系统从 `id2snippet.json` 中的 651 条政策规则检索。当前官方文件含 17,936/1,105/2,373 个 train/dev/test instances，任务都是良性的资格判断、Yes/No 决策或必要的澄清问题；官方提供 TF-IDF、DPR、decision accuracy 和 question-generation 指标。数据按 CC BY-SA 3.0 发布。

这里资源池可以原样使用：只索引 `id2snippet.json`，把 question、scenario、history、gold snippet ID、evidence 和 answer 全部留在 task/evaluator 侧。1 条注入约占 0.15%。同一规则下有多个 scenario 和对话分支，因此可用一部分实例生成 skill，再在同规则的未见 scenario 上测试持久影响。

它的短板同样明确：输出是政策判断或追问，不是外部工具执行，且 OR-ShARC 本身只是 technical report。它非常适合证明攻击不限于 API schema，但不能单独证明持久 skill 会改变真实环境状态。

## 备选资源

[MultiDoc2Dial](https://doi.org/10.18653/v1/2021.emnlp-main.498) 提供 488 篇政府服务文档、4,796 段对话和 61,078 turns，并原生使用 DPR/FAISS/RAG。文档很纯、任务自然，适合 text-only external-validity；但 verifier 主要是 retrieval recall、F1、EM 和 BLEU，没有可执行状态，因此优先级低于 OR-ShARC。

[Gorilla APIBench](https://arxiv.org/abs/2305.15334) 有 1,645 个结构化 API/model-card 文档、每 API 10 个 synthetic instructions，并以 BM25 或 GPT-index 做检索。它非常知名、仓库为 Apache-2.0，适合证明低预算资源能否在大而重叠的 API pool 中竞争；但原论文明确不以实际执行为重点，主评测是 AST subtree matching，因此只作为 retrieval stress test。

[τ-Knowledge](https://arxiv.org/abs/2603.04370) 的 `banking_knowledge` 确实是开箱即用程度最高的单域：698 条政策/流程文档、97 个任务、原生检索和状态化 verifier。它可以保留为 sanity check，但 2026 年才发布，官方在 v1.0.1 还修过会改变成绩的 grading bugs；它不应再作为论文知名度的唯一支点。

ToolBench/StableToolBench 不进入 clean 主池。它们规模大且原生检索，但文档来自第三方 RapidAPI，服务和文档会漂移，稳定版仍大量依赖模拟 API 与 learned/LLM evaluator。MPBench、SkillJack trajectory、SkillX skill library 也都不属于 benign resource pool：它们分别是 memory cases、攻击/轨迹材料或已经编译的 skill，只能做 baseline 或 compiler，不能混入 clean corpus。

## 实验落地

统一 schema 应保持资源、任务与隐藏标签物理分离：

```text
visible_resource = {
  resource_id, origin_id, title, body, public_metadata
}

hidden_task = {
  instruction, initial_state, gold_resource_ids,
  expected_actions, evaluator
}
```

对 AppWorld 的实际流水线是：从 457 条 API docs 建 clean index，运行原始 benign task，记录自然 top-k、agent 的引用跨度和执行轨迹；只有官方 task verifier 通过的轨迹才交给 compiler。随后销毁 index、resource texts、检索 cache、conversation 与普通 memory，只保存 skill artifact。在新 task 和新会话中，用独立的本地 no-op canary 与 AppWorld state evaluator 联合判定。攻击者始终只控制 overlay 中的 1 或 3 个 `origin_id`，不控制 retriever、任务、工具实现、compiler 或 verifier。

推荐推进顺序是：先在 API-Bank 跑通 10–20 个 task pairs，验证完整 instrumentation；再把主实验迁到 AppWorld；最后用 DocPrompting-CoNaLa 和 OR-ShARC 做跨资源类型复制。论文主表以 AppWorld 的端到端持久效果为主，DocPrompting 报低污染比例与 retrieval scaling，OR-ShARC 报自然语言规则域，API-Bank 作为最易复现的开放 artifact。这样既保住“纯 benign resource pool”，也不会把结论锁死在一个新且不知名的 banking corpus 上。
