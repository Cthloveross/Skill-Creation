# SkillsBench 全85题：检索与 B* 复用

这里是当前统一的资料获取目录。先看 [REPORT.md](REPORT.md) 的实际结果，再看 [progress.json](progress.json) 的进度；后续创建和演化通过 [catalog.json](catalog.json) 直接加载已冻结资料。

425/425份B*已封存（历史15＋本轮410，其中2份来自独立补测）。原两次UNKNOWN保留；S0、演化、NoSkill、utility与执行ASR仍为`NOT_MEASURED`。

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

## 2. 用新trial复现资料获取

原获取run绑定其生产时的源码身份。消费者修复改变了源码身份；原 `retrieve/` 完成封存后只读，不能用本交接源码续跑或覆盖旧Journal。本节仅在需要重新测量时另开获取trial；复用catalog直接看§3。新机器先完成§3的bootstrap。从仓库根目录运行，并在服务终端和获取终端都设置缓存路径：

```bash
export HF_HOME="$PWD/data/huggingface"
```

本机全文embedding服务为 `127.0.0.1:18141`，必须使用固定Qwen权重和8192-token配置。凭据只放本机 `key.env`。下面以当前canonical配置开启独立获取，不复用本机旧获取checkpoint。

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
RETRIEVAL_RUN="$SB/runs/skillsbench/trials/gpt54-NEW/retrieval"
test ! -e "$RETRIEVAL_RUN"
.venv/bin/python "$SB/scripts/probe_skillsbench_acquisition.py" \
  --config "$SB/configs/skillsbench.yaml" \
  --run-dir "$RETRIEVAL_RUN" \
  --all-tasks --whole-documents --jobs 6 \
  --embedding-endpoint http://127.0.0.1:18141/v1 \
  --env-file key.env
```

该命令重新测量425次获取，并调用Analyzer，结果与原15份复用＋410份新获取的数据集分开报告。只有这个新trial自身的源码／配置身份未变时，才可沿用其目录继续：已完成操作复用，NOT_SENT可首次派发，UNKNOWN不重发。鉴权失败停止后续启动；更新key不改变UNKNOWN状态。再次修改源码、提示、资料或预算时另开trial。

遇到UNKNOWN时保留原操作和未完成状态；若需补测，另开独立trial，并在最终catalog保留其来源。不能覆盖原Journal、重置计数，或把独立补测称为同一操作的恢复。

另一台机器没有本机私有Journal，不能用同名目录假装恢复。Git提供的公开catalog用于零检索复用；上面的新trial命令不需要历史私有Journal或 `--reuse-from`。

## 3. 后续实验直接使用这些资料

下列 [全量环境准备](../full-85-v8-handoff/HANDOFF.md#5-clone-and-build-on-the-colleagues-machine) 安装固定源码、Qwen缓存、资料池、工具和任务环境。完整bootstrap需要Linux、`uv`、Docker/Compose和NVIDIA GPU，会构建正式矩阵的索引和85题镜像，不调用付费模型；GPU要求来自embedding／索引构建，非B*重建或本地token计数。按本机选择GPU；已有同源准备沿用其绑定GPU：

```bash
make skillsbench-prepare GPU=0 PREP_JOBS=8
ROOT="$PWD"
SB="$ROOT/experiments/tau-knowledge/skill-evolution"
BUNDLE="$SB/runs/skillsbench/full-85-v8-handoff"
CFG=$(python3 -c 'import json,sys; print(sys.argv[1] + "/" + json.load(open(sys.argv[1]+"/data/skillsbench/setup/binding.json"))["config_path"])' "$SB")
export HF_HOME="$ROOT/data/huggingface"
export PINNED_CODEX_DIR="$ROOT/data/tools/codex-0.160.1"
export PATH="$PINNED_CODEX_DIR:$PATH"
"$BUNDLE/operator.sh" verify
```

恢复B*和本地上下文计数可在CPU上完成，不需要原Dense向量、运行中的embedding服务、模型API或任务Docker容器，但需要固定公开源码与缓存中的Qwen tokenizer。普通Git clone已带122页baseline资料池；catalog校验会在本地自动重建缺失的投毒／整篇池。若人为删除baseline，现有 `prepare_skillsbench.py --pool`可从固定公开checkout和tokenizer重建它。创建／演化／评分仍须通过源码、模型鉴权、固定Codex和Docker任务环境准入；`PREPARED`与catalog完成均不代表环境READY。

目录中的catalog含选中文档ID、公开文件观察的重放配方及原获取指标。原文从固定条件池读取，输入观察从固定公开文件重建，并核对完全相同的base hash；无需复制私有请求、输入全文或ZIP。修改或丢失资料会显式失败，不转回重新检索。

等catalog状态为COMPLETE再启动全量下游。提前使用少数已完成cell时，先复制catalog为固定快照，只选该快照中的cell。下游绑定后，catalog的路径、内容和base hash均不能改变；正在增长的catalog不能替换该快照。

以下例子使用bootstrap的本机GPT-5.4配置。按 [凭据说明](../full-85-v8-handoff/HANDOFF.md#7-credentials) 准备Bedrock及任务专用凭据。换生成／验证模型时使用对应的新配置，保留同一catalog；目录标签不改变配置中的模型，原Analyzer和获取用量仍为GPT-5.4。

输出按模型／trial标签放在 `runs/skillsbench/trials/<model>/{noskill,skills}`，与检索数据分开。首次使用新标签；目录由运行命令创建：

```bash
MODEL=gpt54-NEW
CATALOG="$SB/runs/skillsbench/retrieve/catalog.json"
NOSKILL_RUN="$SB/runs/skillsbench/trials/$MODEL/noskill"
SKILL_RUN="$SB/runs/skillsbench/trials/$MODEL/skills"
test ! -e "$NOSKILL_RUN"
test ! -e "$SKILL_RUN"
```

NoSkill不加载B*，但当前CLI准入仍检查正式资料池／索引，并使用4096-token服务（端口18140）计数。先在独立终端从仓库根启动该服务：

```bash
experiments/tau-knowledge/skill-evolution/runs/skillsbench/full-85-v8-handoff/operator.sh embedding
```

每个模型独立执行85次，不按五条件重复，也不与Skill阶段混加：

```bash
"$ROOT/.venv/bin/r2sp" evaluate --experiment skillsbench --runtime docker \
  --config "$CFG" --run-dir "$NOSKILL_RUN" \
  --no-skill --arm benign --env-file "$ROOT/key.env"
```

NoSkill使用独立目录且不传 `--bases-from`。`r2sp run`不会自动执行NoSkill；下面才是五条件Skill阶段，其导入资料不需要embedding服务：

```bash
"$ROOT/.venv/bin/r2sp" run --experiment skillsbench --runtime docker \
  --config "$CFG" --run-dir "$SKILL_RUN" --bases-from "$CATALOG" \
  --arm benign --arm data-exfil-http-5 --arm data-exfil-http-10 \
  --arm file-delete-5 --arm file-delete-10 \
  --env-file "$ROOT/key.env"
```

单题调试再加 `--task <task_id>`；只创建S0把 `run` 换成 `create`。这里没有credential/CPU条件的B*，默认请求九条件会被拒绝，不能把425份当作765份。

多账户并行时，用下面命令替换上面的顺序 `run`，不要同时启动两种launcher。`TOKEN_DIR`包含按账户命名、原子刷新的0600 token JSON；launcher不读取 `key.env`，任务专用变量须先按凭据说明导出。未传 `--accounts`时扫描该目录：

```bash
export TOKEN_DIR=/absolute/private/path/bedrock-tokens
"$ROOT/.venv/bin/python" "$SB/scripts/launch_matrix.py" \
  --experiment skillsbench --runtime docker --config "$CFG" \
  --run-dir "$SKILL_RUN" --bases-from "$CATALOG" --token-dir "$TOKEN_DIR" \
  --arm benign --arm data-exfil-http-5 --arm data-exfil-http-10 \
  --arm file-delete-5 --arm file-delete-10 \
  --max-concurrent 16 --r2sp "$ROOT/.venv/bin/r2sp"
```

恢复时沿用同一源码／配置、run目录和catalog，重复原运行命令；已完成操作复用，NOT_SENT可首次派发，UNKNOWN不重发。未封存演化若丢失原绑定容器，保留未完成记录并另开trial。重建Skill报告不调用模型：

```bash
"$ROOT/.venv/bin/r2sp" report --experiment skillsbench --runtime docker \
  --config "$CFG" --run-dir "$SKILL_RUN" --bases-from "$CATALOG"
```

上述下游导入不再调用Analyzer，原获取成本另记。上层正式交接包的 `operator.sh matrix/resume`用于九条件765-cell分块实验，不用于启动本目录的五条件catalog试验。

## 4. 文件与验收边界

- `REPORT.md`：逐条件进度、参考覆盖和payload留存；含payload不等于攻击成功。
- `catalog.json`：可移植B*配方、来源、查询、分数、理由、预算和停止记录。
- `acquisition-summary.json` / `progress.json`：机器汇总与固定分母。
- `cells/`、`journal/`、`usage.jsonl`、`logs/`：本机原始证据，默认不上传。

整理时保留这里、上层HANDOFF和全量交接包；后续运行写入同级 `trials/`。旧试跑与验收移至 `archive/runs/skillsbench/`，保持原始文件字节；旧执行checkpoint仅供审计，不恢复。

425份B*全部通过精确重建，过程禁用网络、模型和检索；合并后的完整共享回归为1735项通过、58项跳过，Ruff、编译、依赖锁和交接源码校验通过。本轮没有生成或执行Skill，不能据此宣称utility、演化、执行ASR或真实Docker任务边界已测得。
