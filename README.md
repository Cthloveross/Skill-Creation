# Resource-to-Skill Poisoning

本项目在隔离环境中研究 file-backed resource-to-skill poisoning。官方 AppWorld JSON 保持只读；
注入与 effect 仅作用于本地 evaluator-owned 数据，不写真实网页、API、用户文件或公共 Skill 市场。

## 当前流程

```text
AppWorld 官方 JSON（457 endpoints / 447 task-facing resources）
  → materialize 完整 Benign/Poison 磁盘 corpus
      Benign：官方 JSON 字节等价副本，不加 retrieval lead
      Poison：只修改目标 endpoint description，加入 lead + required block
  → manifest 全量重放
  → 用原始 authoring instruction 跑完整 447-doc BM25
  → Poison 未自然进入 Top-10：停止，不启动模型、不生成 Skill
  → Poison 进入 Top-10：运行 Qwen Agent 的真实 acquisition
  → Agent 从 Top-10 headers 中选择恰好 5 个 resource 并全文读取
  → Poison 未进入真实 Top-10 / Top-5 / full-read：停止，不调用 compiler
  → fresh-context compiler 生成 SKILL.md
  → 两个 profile 必须全部通过（2/2）
  → clean reset 后加载 Skill，运行本地正例/负例 deployment 验证
```

两个固定 profile：

- `mock-api-call`：Poison 目标为 `spotify.search_songs`
- `delete-sentinel`：Poison 目标为 `file_system.delete_directory`

BM25 不强制插入、boost 或重排目标。Lead 是攻击设定的一部分，只存在于 Poison；若 lead 不足，
该 corpus 版本被拒绝，修改 lead 后必须创建新版本并从 materialize 重跑。

## 位置

- 官方数据：[`experiments/pilot/data/appworld-0.1.0/`](experiments/pilot/data/appworld-0.1.0/)
- 当前派生语料：[`experiments/pilot/data/file-injection-appworld-20260901-v3/`](experiments/pilot/data/file-injection-appworld-20260901-v3/)
- 唯一机器合同：[configs/experiment_plan.yaml](configs/experiment_plan.yaml)
- 唯一权威流程：[docs/run-records/procedure.md](docs/run-records/procedure.md)
- 数据库与 Resource 检索结构：[docs/database.md](docs/database.md)
- 检索现实性与后续矩阵：[docs/retrieval-realism.md](docs/retrieval-realism.md)
- 当前实施计划：[experiments/pilot/plans/2026-09-01-benign-poison-retrieval-gated-procedure.md](experiments/pilot/plans/2026-09-01-benign-poison-retrieval-gated-procedure.md)

核心入口：

- [`src/r2sp/file_injection.py`](src/r2sp/file_injection.py)：identity/Poison JSON 变换与 manifest 重放
- [`src/r2sp/file_injection_live.py`](src/r2sp/file_injection_live.py)：materialize/retrieve CLI
- [`src/r2sp/qualification_live.py`](src/r2sp/qualification_live.py)：paired compile/strict deploy CLI
- [`src/r2sp/retrieval.py`](src/r2sp/retrieval.py)：固定 BM25 Top-10
- [`src/r2sp/agent.py`](src/r2sp/agent.py)：exact-five 与受限全文读取
- [`src/r2sp/injection_runner.py`](src/r2sp/injection_runner.py)：检索和 compiler 硬门控
- [`src/r2sp/injection_deployment_runner.py`](src/r2sp/injection_deployment_runner.py)：2/2 deployment 门控

## 模型

当前完整模型流程使用 `Qwen/Qwen3.8-27B-FP8` revision
`017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`，FP8 权重、FP16 计算，物理 GPU 0/6，TP=2，
32,768 context。
无模型 retrieval 阶段只用 CPU；两个 Poison 都通过 Top-10 准入前不需要启动模型服务。

## 验证

```bash
make setup
make check
```

具体命令、停止条件、检索证据、模型设置和安全边界全部以
[procedure.md](docs/run-records/procedure.md) 为准。
