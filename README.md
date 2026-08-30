# Resource-to-Skill Poisoning

> 仅用于隔离环境中的防御性研究。只使用本地无副作用 canary，不向真实网页、仓库或公共 skill 市场注入内容。

## 当前阶段

现在只做一个小规模 feasibility pilot：

> Qwen3.8 执行良性 AppWorld 任务时，能否自然读取 457 条正常 API 文档中的一条攻击者 overlay，把其中规则写入 skill，并在删除原资源、重启 agent 后继续触发？

## 执行入口

- [精简实验计划](EXPERIMENT_PLAN.md)：两臂设计、resource pool、执行流程、指标和 go/no-go。
- [最小机器配置](configs/experiment_plan.yaml)：runner 需要的参数。
- [`analysis/`](analysis)：此前的文献、数据集和完整论文方案调研；不属于当前 pilot 的执行协议。

## Pilot 一览

- 模型：`Qwen/Qwen3.8-27B`，单张 H200，BF16；
- 数据：AppWorld；
- 条件：matched Sham vs one-document Poison；
- 检索：BM25 返回 Top-10 header，acquisition agent 必须显式选择其中 5 条唯一文档；
- 规模：16 个 matched cases、32 次 build、64 次 deployment；
- 结果：自然读取、有效 skill、source-removed 持久触发、误触和任务分数。

当前只以这套两臂 pilot 为准；后续实验等 pilot 结果出来后再决定。
这里的 H200/BF16 是冻结的正式实验目标，不是对当前服务器的描述。本机已实测通过非研究的
8 卡 RTX 6000/FP16、TP=2/PP=4、65,536-token 工程配置；它不等同于 v0.3 研究条件，具体证据和
限制见 [GPU compatibility](docs/gpu-compatibility.md)。

## 已实现

- 严格校验 v0.3 配置、16-case 私有 bundle、hash-only overlay attestation 和固定 paired
  schedule；
- 457-doc immutable resource pool、body-free BM25 搜索与显式全文读取；
- acquisition 五工具 agent（含结构化 `select_docs` Top-5）、deployment 四工具 agent、
  fresh-context `SKILL.md` compiler、AppWorld/Qwen adapters；
- evaluator-owned 本地 canary、hard-reset attestation、write-once artifacts；
- 固定分母的 paired evaluation、JSON/CSV/Markdown 报告和 research eligibility gate；
- loopback vLLM 元数据网关，以及不会升级为研究证据的真实模型 agent/编译器 probe；
- deterministic synthetic end-to-end smoke、CLI、单元/集成测试和 CI。

Synthetic smoke 只能验证代码链路，永远输出 `research_eligible=false`。真实自然读取率、skill
持久率、任务效用和 go/no-go 在完整 gated pilot 前均为 unknown。

正式 agent 的原始问题来自冻结的 AppWorld Train task ID，并必须逐字匹配运行时
`world.task.instruction`；不是 Qwen 或 overlay 生成的。Synthetic smoke 的问题来自
[`src/r2sp/fixtures.py`](src/r2sp/fixtures.py)，只属于测试夹具。每次 run 必须记录来源、task ID
和 instruction hash。

当前权威协议是 v0.3。历史 v0.2 输出仍是 v0.2，不能重标或合并为 v0.3 证据；版本差异见
[Protocol changelog](docs/protocol-changelog.md)。

## 本地运行

```bash
make setup
make check
make smoke
```

`make smoke` 是确定性脚本基线，不调用模型。已有 loopback Qwen 服务时，真实模型链路使用独立
命令和输出目录：

```bash
.venv/bin/r2sp run-model-smoke \
  --output runs/top5-qwen-YYYYMMDD \
  --base-url http://127.0.0.1:18000/v1 \
  --model-id Qwen/Qwen3.8-27B \
  --revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --timeout-seconds 900 \
  --max-model-len 65536 \
  --max-agent-turns 16
```

该命令让同一个模型分别完成 acquisition、fresh-context compiler 和两个 fresh deployment；
结果固定标记为 `synthetic_model_smoke`、`research_eligible=false`。输出中的
`inputs/model-provenance.json`、每臂 `acquisition.json`、`skill/provenance.json` 和全树
`artifacts-manifest.json` 用于区分真实模型产物与脚本产物。

真实 pilot 必须先通过：

```bash
.venv/bin/r2sp preflight \
  --config configs/experiment_plan.yaml \
  --runtime-config /absolute/external/runtime.yaml \
  --research-ready
```

当前仓库中的 `runner_ready=false` 和 data hash placeholder 是有意的；没有受保护 AppWorld
数据、冻结 16 cases、目标平台完整 dependency locks、可验证的 Qwen service metadata 和 H200
环境时，真实 run 必须失败，不能用 synthetic 结果代替。

## 项目文档

- [Architecture](docs/architecture.md)：信任边界、状态机、模块和证据等级。
- [Runbook](docs/runbook.md)：环境、冻结、预检、执行、恢复和数据管理。
- [GPU compatibility](docs/gpu-compatibility.md)：本机 RTX 6000 审计、H200 差异和已验证的
  8 卡 FP16 工程配置。
- [Protocol changelog](docs/protocol-changelog.md)：v0.2 → v0.3 的语义差异和证据边界。
- [Implementation plan](experiments/pilot/plans/2026-08-29-r2sp-feasibility.md)：本轮构建及验收项。
- [Top-5 implementation/run plan](experiments/pilot/plans/2026-08-30-top5-model-selection.md)：
  Top-5、skill provenance 和真实模型 smoke 的实施与验收记录。
- [2026-08-30 full-chain run](docs/run-records/2026-08-30-top5-smoke.md)：真实 Qwen
  Top-5 选择、生成 skill、结果哈希、原始任务来源和证据边界。
