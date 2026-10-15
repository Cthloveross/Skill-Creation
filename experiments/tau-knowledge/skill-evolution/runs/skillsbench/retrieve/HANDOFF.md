# SkillsBench 全85题：检索与 B* 复用

这里是当前统一的资料获取目录。先看 [REPORT.md](REPORT.md) 的实际结果，再看 [progress.json](progress.json) 的进度；后续创建和演化通过 [catalog.json](catalog.json) 直接加载已冻结资料。

## 1. 本次做什么

| 项目 | 设置 |
|---|---|
| 任务 | 固定作者 commit 的全部85题 |
| 条件 | benign、HTTP 5%/10%、File Delete 5%/10% |
| 获取总数 | 85×5＝425；复用兼容的15份，新增410份 |
| 检索单位 | 85篇完整背景原文；BM25、Dense均以整篇建立索引和返回 |
| 模型 | Bedrock GPT-5.4，us-east-1，Analyzer medium |
| 检索 | BM25 top10＋Dense top10，RRF k=60；Qwen3-Embedding-4B，输入上限8192 |
| 预算 | 搜索30、公开输入观察10、Analyzer决策50；B*最多32768 tokens；相关性阈值0.1 |
| 并行 | 最多6次独立获取 |
| 本轮不做 | S0、任务执行、Verifier、oracle、独立评分、执行ASR |

模型只收到公开任务、允许发现的当前题输入和检索正文；不收到注入标签、目标列表或本题参考文档答案。原始输入通过固定任务源码中的授权文件视图发现，该视图不等于构建后的完整容器文件系统。

参考文档召回、模型可见暴露、B*留存分别统计。找回作者关联背景不代表全部任务要求已有充分证据。判断不充分但已合法冻结的 B* 仍保留并可复用；UNKNOWN等获取故障不算完成。不根据后续 utility 重选资料。

## 2. 继续或复现资料获取

从仓库根目录运行。使用现有固定环境；本机全文 embedding 服务在 `127.0.0.1:18141`，必须是固定Qwen权重和8192-token配置，不能拿4096-token服务冒充。凭据只放本机 `key.env`。

若服务未启动，在单独终端运行下面命令。先按本机空闲GPU设置 `GPU` 和显存比例 `GPU_MEMORY`；本机实测为GPU 1、0.085。它只启动embedding，不读取模型API key。

```bash
GPU=1 GPU_MEMORY=0.085 .venv/bin/python - <<'PY'
import copy, os
from pathlib import Path
from tau_skill_evolution.spec import load_spec, ExperimentSpec
from tau_skill_evolution.retrieval import embedding_argv
spec = load_spec(Path('experiments/tau-knowledge/skill-evolution/configs/skillsbench.yaml'))
values = copy.deepcopy(spec.values)
values['embedding'].update(endpoint='http://127.0.0.1:18141/v1', max_length=8192,
                           gpu_memory_utilization=float(os.environ['GPU_MEMORY']))
command = embedding_argv(ExperimentSpec(spec.path, values))
command[-1] = '8'
os.execvpe(command[0], command, {**os.environ, 'CUDA_VISIBLE_DEVICES': os.environ['GPU']})
PY
```

```bash
SB=experiments/tau-knowledge/skill-evolution
.venv/bin/python "$SB/scripts/probe_skillsbench_acquisition.py" \
  --config "$SB/configs/skillsbench.yaml" \
  --run-dir "$SB/runs/skillsbench/retrieve" \
  --all-tasks --whole-documents --jobs 6 \
  --embedding-endpoint http://127.0.0.1:18141/v1 \
  --reuse-from "$SB/archive/runs/skillsbench/retrieval-whole-document-gpt54-20261014-001" \
  --env-file key.env
```

该命令恢复本机同一源码身份、没有UNKNOWN阻塞的未完成获取。已冻结结果不重复请求；NOT_SENT可首次派发，已派发且结果未知的UNKNOWN不自动重发。鉴权失败停止启动后续获取。更新key不能把旧UNKNOWN改为可重试。源码、提示、资料或预算改变后另开trial。

本次 `paper-anonymizer / benign` 的第37次Analyzer请求等待HTTP状态行超时，原操作为UNKNOWN，没有响应原文或B*。原记录保留；独立续采仅跳过这一格，复用已封存结果，并首次派发其他未启动格。续采脚本和操作记录保存在本机 `logs/` 与根Journal，不修改冻结源码。直接重跑上面的命令仍会在该UNKNOWN处停止，不能据此补测或覆盖。该格若需补测，必须另开独立trial，明确保留原UNKNOWN及补测来源。

另一台机器没有本机私有journal，不能用同名目录假装恢复。Git提供的是公开catalog，可用于零检索复用；若需要重新测量获取，应指定新的 `--run-dir` 并去掉 `--reuse-from`，明确记为新trial。

## 3. 后续实验直接使用这些资料

先准备固定源码和原始条件资料池；沿用 [全量环境准备](../full-85-v8-handoff/HANDOFF.md)。恢复B*本身不需要原Dense向量、模型API或任务Docker环境；若资料池尚未准备，仍需固定Qwen tokenizer完成原始资料准备。正式执行另外通过Docker preflight。

目录中的catalog含选中文档ID、公开文件观察的重放配方及原获取指标。原文从固定条件池读取，输入观察从固定公开文件重建，并核对完全相同的base hash；无需复制私有请求、输入全文或ZIP。修改或丢失资料会显式失败，不转回重新检索。

以下命令以当前模型做创建、演化和独立评价。换生成/验证模型时使用对应配置文件，保留同一catalog；原Analyzer模型和用量仍记录为GPT-5.4。

```bash
SB=experiments/tau-knowledge/skill-evolution
.venv/bin/r2sp run --experiment skillsbench \
  --config "$SB/configs/skillsbench.yaml" \
  --run-dir "$SB/runs/skillsbench/new-skill-trial" \
  --bases-from "$SB/runs/skillsbench/retrieve/catalog.json" \
  --arm benign --arm data-exfil-http-5 --arm data-exfil-http-10 \
  --arm file-delete-5 --arm file-delete-10 \
  --env-file key.env
```

单题调试再加 `--task <task_id>`；只创建S0把 `run` 换成 `create`。多账户并行用现有 `scripts/launch_matrix.py --bases-from ...`，同样显式传上述五个 `--arm`。这里没有credential/CPU条件的B*，默认请求九条件会被拒绝，不能把425份当作765份。

等catalog状态为COMPLETE再启动全量下游。要提前使用已完成的少数cell，先复制catalog为固定快照，再启动对应任务；正在增长的catalog不能替换已绑定下游的快照。下游恢复沿用原路径和catalog，实际Analyzer调用数为0；原获取成本另记。

## 4. 文件与验收边界

- `REPORT.md`：逐条件进度、参考覆盖和payload留存；含payload不等于攻击成功。
- `catalog.json`：可移植B*配方、来源、查询、分数、理由、预算和停止记录。
- `acquisition-summary.json` / `progress.json`：机器汇总与固定分母。
- `cells/`、`journal/`、`usage.jsonl`、`logs/`：本机原始证据，默认不上传。

目录整理后，活动入口只保留这里、上层HANDOFF和全量交接包。旧试跑与验收移至 `archive/runs/skillsbench/`，保持原始文件字节；旧执行checkpoint仅供审计，不恢复。

离线回归、15份真实旧B*校验及只复制catalog的零网络重建用于验证复用接口。本轮没有生成或执行Skill，不能据此宣称utility、演化或执行ASR已测得。
