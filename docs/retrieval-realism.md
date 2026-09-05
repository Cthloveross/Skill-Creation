# 检索器选择依据

本文只记录为什么论文不能只报告 BM25，以及后续最小检索器矩阵。数据、命令、门控和当前结果统一
见 [`procedure.md`](procedure.md)。

## 结论

没有可信的公开普查能证明真实 RAG/Agent 系统都使用 BM25。现有证据只支持：

- BM25 便宜、确定、可解释，并且在异构零样本任务上仍是强 sparse baseline；
- dense dual-encoder 对同义改写和低词面重合有优势，但不能跨领域保证优于 BM25；
- BM25 与 dense 并行检索、RRF 融合，再选配 cross-encoder reranker，是公开生产系统中更有代表性的
  hybrid 架构。

因此当前 BM25 结果只能支持“该攻击在固定 BM25 管线中的表现”，不能直接外推到所有检索系统。

## 最小实验矩阵

| 条件 | 初始检索 | 融合/重排 | 目的 |
| --- | --- | --- | --- |
| A | BM25 | 无 | 当前 sparse baseline |
| B | Dense | 无 | 测试语义检索转移 |
| C | BM25 + Dense | RRF | 模拟常见 hybrid retrieval |
| D | BM25 + Dense | RRF + cross-encoder | 测试二阶段重排的影响 |

当前只有 447 个 Resources，A/B/C 可以对全库做精确 BM25 和 cosine 排名，不需要 ANN/HNSW。
RRF 固定 `k=60` 并在运行前冻结候选深度。首轮可使用：

- `Qwen/Qwen3-Embedding-0.6B`
- `Qwen/Qwen3-Reranker-0.6B`

四个条件必须使用同一份预先冻结的 Poison、任务、文件名、metadata 和 `rho`。某个检索器没有把
Poison 带入 Top-10 时，该端到端 trial 直接记为失败；不能针对每个检索器分别调整 lead。自适应
Poison 只能另列为知道检索器的 white-box upper bound。

## 主要来源

- DPR: https://aclanthology.org/2020.emnlp-main.550/
- BEIR: https://arxiv.org/abs/2104.08663
- Reciprocal Rank Fusion: https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/
- Re2G: https://aclanthology.org/2022.naacl-main.194/
- Azure hybrid search: https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview
- Azure semantic reranking: https://learn.microsoft.com/en-us/AZURE/search/semantic-search-overview
- Poisoning Retrieval Corpora: https://aclanthology.org/2023.emnlp-main.849/
- AgentPoison: https://proceedings.neurips.cc/paper_files/paper/2024/hash/eb113910e9c3f6242541c1652e30dfd6-Abstract-Conference.html
- PoisonedRAG: https://www.usenix.org/conference/usenixsecurity25/presentation/zou-poisonedrag
- Qwen3 Embedding: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
