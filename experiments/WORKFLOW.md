# 当前实验流程

当前主线为 **τ-Knowledge r8 / v2：良性 Skill 批量创建 + 独立普通任务评估**。新入口只接受 `corpus: benign`，不物化投毒文档、不挂载 canary 工具、不调度攻击部署。历史 ASR 仅登记既有 artifact 和历史重放证据；复核须使用原 run 对应的工具与源码身份。旧研究协议及原始结果保留，不能把它们标成新 v2 结果。

本次只交付代码、文档和离线验证；镜像构建、模型资格检查及真实批次均已暂停。以下命令说明软件接口，当前资产状态见 [RESULTS.md](RESULTS.md)。

## 1. 文档与版本

本文件是当前操作说明；[RESULTS.md](RESULTS.md) 登记证据；根 [README](../README.md) 只作导航。精确 v2 合同见 [BATCH_PROTOCOL_R8.md](tau-knowledge/preliminary/configs/BATCH_PROTOCOL_R8.md)。

| 版本 | 定位 |
| --- | --- |
| r8 / v2 | 当前良性批处理，创建和评估独立 |
| [r7](tau-knowledge/preliminary/configs/OPEN_WEIGHT_PROTOCOL.md) | 历史 open-weight 两阶段设计，只读归档；本次不提供其执行入口 |
| [r5](tau-knowledge/preliminary/configs/CODEX_GPT55_PROTOCOL.md) | 历史 Codex 复制协议，只读归档 |
| [r3](tau-knowledge/preliminary/configs/FROZEN_PROTOCOL.md) | 历史 Qwen exploratory 协议，只读归档 |
| AppWorld v0.4 | 历史 qualification，现入口仅离线回归 |

`tau-knowledge/preliminary/configs/preliminary.yaml`、旧模型/compiler/runtime 及其默认值保持原有历史基线，不是 v2 的 batch 配置。v2 使用独立 spec 与 `batch_*` 模块。归档协议中的“当前”“下一轮”和命令均对应其历史时期，不保证与本次保留的旧基线一致；尤其 r7 中同名提交 wrapper 的旧参数不适用于 v2。带日期的 `plans/`、旧 `prompts/` 和冻结合同保留历史来源。

## 2. 目录与数据

```text
experiments/
  WORKFLOW.md / RESULTS.md
  tau-knowledge/preliminary/
    configs/                   v2 示例、冻结旧协议、快照承诺
    scripts/run_batch.py       create / evaluate / validate / replay
    scripts/submit_*.sh        默认 dry-run 的独立提交入口
    slurm/tau_batch.sbatch     从封存源码启动 v2
    plans/ prompts/ schemas/ tests/
    data/ runs/                ignored 输入与结果
  appworld/preliminary/        独立历史实现与离线入口
```

τ 使用 `src/r2sp_tau_knowledge`，AppWorld 使用 `src/r2sp`；只共享 `src/r2sp_common` 的无数据集分支原语。任务工具、DB 生命周期、prompt、compiler、runtime 和 evaluator 分别实现。τ 的 v2 常量、模型客户端、compiler、阶段结果、服务及官方 runtime/worker 位于独立 `batch_*` 模块，不通过更改历史模块默认值实现新合同。

τ 固定到 tau2-bench `v1.0.1` commit `fc0055dc4e0a316c3f83133267fbd6faaa770992`，完整 banking-knowledge 为 698 documents / 97 tasks。checkout 与 Python 3.12 环境在 `tau-knowledge/preliminary/data/upstream/tau2-bench/`，清单在 `configs/upstream-*.json`。项目 core 环境为根 `.venv`。

## 3. 创建 batch

复制 [generation-benign-10.example.yaml](tau-knowledge/preliminary/configs/generation-benign-10.example.yaml)，设置新 `batch_id`。每项给出唯一 `skill_id`、官方 `acquisition_task_id`、`corpus: benign`、`seed`。十项只是示例，runner 按列表执行，不固定四格矩阵。

`dataset` 声明快照；`model` 独立声明 ID、revision、localhost endpoint 与 65,536-token context。运行时验证实际模型并拒绝静默替换。候选主模型为固定 Flash-Next，须通过独立资格检查后才能用于正式批次；固定 27B 仅作明确标识的独立诊断。

流程为：验证原始良性语料 → 每项 fresh acquisition → 选择十篇已展示文档 → fresh compiler → 校验 Skill → 封存创建 batch。检索只索引正文：每次 query 分别取得 BM25 Top-10 与 embedding Top-10，按 RRF `k=60` 融合并按文档 ID 去重，同分按 ID 排序。Agent 每次最多看到 20 篇，只显示 ID、标题和完整正文；最多两次 query，整个 session 最多展示 40 篇唯一文档。通道重合或此前已展示的文档不重复、不补位。`select_docs` 从历次实际展示的并集中恰选十个唯一 ID，只允许一次成功选择，原子返回十篇全文后关闭检索。通道身份、分数与原始排名只保存在 evaluator 侧。Compiler 只接收首个用户问题、按顺序的十篇文档和脱敏 acquisition trace，不接收任务奖励或 evaluator 真值。

创建不包含 deployment。成功、失败、耗时及来源逐项记录；批次完成不表示每个 Skill 都有效。

```bash
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py validate \
  --phase create --spec experiments/tau-knowledge/preliminary/configs/generation-benign-10.example.yaml

# 合成数据 harness，无真实模型指标
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py create \
  --spec experiments/tau-knowledge/preliminary/configs/generation-benign-10.example.yaml \
  --runs-root /tmp/tau-benign-v2-scripted --scripted
```

## 4. 独立评估 batch

[evaluation-benign.example.yaml](tau-knowledge/preliminary/configs/evaluation-benign.example.yaml) 是模板，先把 `sources[].root` 与 `complete_sha256` 换成已封存的 v2 创建结果。相对 root 按 spec 所在目录解析。每个 trial 显式绑定 `source_id`、`skill_id`、`task_id`、`category`、`seed`；可引用多个创建 batch，可挑选其中部分 Skill，也可为一个 Skill 配置多个任务。

评估有自己的 model，可与创建模型不同。先验证来源 seal 和 Skill hash，再逐个启动 fresh official runtime。Deployment 只有当前任务、已校验 Skill 和普通任务工具，没有原始语料、检索、acquisition memory 或 canary 工具。评估不调用 acquisition 或 compiler。

`positive` / `negative` 是任务分组标签。这里只报告普通 utility、失败和缺失项，不将分组解释成 canary 误激活率或 ASR。示例配对尚不代表已验证的任务迁移设计。

```bash
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py validate \
  --phase evaluate --spec /absolute/path/evaluation.yaml
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py evaluate \
  --spec /absolute/path/evaluation.yaml --runs-root /tmp/tau-utility-v2-scripted --scripted
```

### 最小真实端到端验收

[generation-benign-acceptance-2.yaml](tau-knowledge/preliminary/configs/generation-benign-acceptance-2.yaml) 固定 Flash-Next 与上述检索合同，从官方 97 个任务中选两项普通信用卡咨询/申请任务，各学习一次：`task_001` 为日常返现需求，`task_006` 为已明确约束的产品选择。两者均有用户侧正常申请工具，不以长轮次转人工作为验收前提。任务选择仅用于缩小工程验收范围，不向 Agent 提供 evaluator 参考文档或答案，也不保证模型成功。Acquisition 的 `select_docs` 仍须从实际展示并集中自主选满十篇。

[evaluation-benign-acceptance.template.yaml](tau-knowledge/preliminary/configs/evaluation-benign-acceptance.template.yaml) 包含四项：两个 Skill 各评估原学习任务和另一个任务。四项均为 `positive` 普通 utility；同一任务使用配对 seed，交叉任务不自动成为 negative。它只检验同任务和有限迁移链路，不是完整 benchmark。`task_002` 可另设留出正向评估；`task_034` 可另设用户模拟器/转人工诊断，因历史 evaluator 与终止差异，不纳入本次四项验收分母。

独立旧模型基线使用 [generation-benign-acceptance-2-27b-diagnostic.yaml](tau-knowledge/preliminary/configs/generation-benign-acceptance-2-27b-diagnostic.yaml) 和 [evaluation-benign-acceptance-27b-diagnostic.template.yaml](tau-knowledge/preliminary/configs/evaluation-benign-acceptance-27b-diagnostic.template.yaml)。仅模型 ID/revision 与 `batch_id` 改为固定 `Qwen/Qwen3.8-27B-FP8` / `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`；items、任务、seed、检索与四项评估完全相同。它有独立创建来源和结果，不能因 Flash 排队而将 27B 结果标作 Flash 实测。提交时显式选择对应 spec，并传入该模型已经验证的 SIF 路径；其资产和服务同样须通过资格检查。

创建和评估分开提交，各自保留完整失败证据，不因未达 reward 或缺少有效 Skill 而换题、补跑或删除 trial。重复实验应换 `batch_id`；已记录的阶段失败不靠 resume 隐式重试。先严格验证配置，再检查创建提交请求：

```bash
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py validate \
  --phase create --spec experiments/tau-knowledge/preliminary/configs/generation-benign-acceptance-2.yaml
bash experiments/tau-knowledge/preliminary/scripts/submit_generation.sh \
  --spec experiments/tau-knowledge/preliminary/configs/generation-benign-acceptance-2.yaml
```

上条提交命令默认 dry-run；资产及模型资格确认后显式加 `--submit`。创建完成后，从作业 CLI 输出记录其 root 和 `complete_sha256`，用下面的离线命令绑定评估来源。前三个位置参数依次为实际创建目录、外部记录的完成 hash、新评估配置路径；输出必须尚不存在。默认选择 Flash 配置；诊断旧模型须在输出路径后再加第四个参数 `27b`，同时选择对应的创建配置和评估模板。

```bash
PYTHONPATH=src .venv/bin/python - \
  /absolute/path/sealed-creation RECORDED_COMPLETE_SHA256 \
  /absolute/path/new-acceptance-evaluation.yaml <<'PY'
import sys
from pathlib import Path

import yaml

from r2sp_tau_knowledge.batch import EvaluationSpec, load_spec, replay_batch

source = Path(sys.argv[1]).resolve()
report = replay_batch(source, complete_sha256=sys.argv[2])
if report["phase"] != "creation" or report["execution_mode"] != "live":
    raise ValueError("acceptance requires a sealed live creation source")
configs = Path("experiments/tau-knowledge/preliminary/configs")
variants = {
    "flash": ("generation-benign-acceptance-2.yaml", "evaluation-benign-acceptance.template.yaml"),
    "27b": ("generation-benign-acceptance-2-27b-diagnostic.yaml",
            "evaluation-benign-acceptance-27b-diagnostic.template.yaml"),
}
creation_name, evaluation_name = variants[sys.argv[4] if len(sys.argv) > 4 else "flash"]
expected = load_spec(configs / creation_name, "creation").to_dict()
actual = load_spec(source / "spec.json", "creation").to_dict()
for field in ("dataset", "model", "retrieval", "items"):
    if actual[field] != expected[field]:
        raise ValueError(f"unexpected acceptance source {field}")
value = yaml.safe_load((configs / evaluation_name).read_text())
if any(value[field] != actual[field] for field in ("dataset", "model")):
    raise ValueError("acceptance evaluation model/dataset mismatch")
value["sources"][0].update(root=str(source), complete_sha256=sys.argv[2])
bound = EvaluationSpec.from_dict(value)
with Path(sys.argv[3]).open("x") as output:
    yaml.safe_dump(bound.to_dict(), output, sort_keys=False)
print(sys.argv[3])
PY

.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py validate \
  --phase evaluate --spec /absolute/path/new-acceptance-evaluation.yaml
bash experiments/tau-knowledge/preliminary/scripts/submit_evaluation.sh \
  --spec /absolute/path/new-acceptance-evaluation.yaml
```

确认绑定来源后，最后一条命令显式加 `--submit` 才提交独立评估。创建目录封存失败项也可绑定；缺失 Skill 由评估记录为未运行，不能丢出结果清单。两阶段分别以外部记录 hash 做 CLI replay，登记 acquisition/compile 有效项、四个 trial 的 reward/失败/未运行及分母。配置已准备或 seal 完整都不等于模型 utility 验收成功。

## 5. Checkpoint 与重放

每个 batch 固定 `spec.json`、`provenance.json`、`source/source-bundle.tar`；阶段 artifact 不覆盖，`checkpoint-index.json` 保存已完成阶段 hash。中断批次用同一 spec 加 `--resume <unfinished-batch-root>`。只有 hash 验证通过的完成阶段可跳过，已记录失败不隐式重试。spec、模型或源码身份改变需新建 batch。

创建用 `generation-complete.json` 封存，评估有独立 completion seal。CLI 输出完成 hash；引用 source 时必须使用外部记录的 hash，不能只相信目录自称完成。发布前验证当前执行源码与封存 bundle 一致。重放不连接模型：

```bash
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py replay \
  /absolute/path/completed-batch --complete-sha256 RECORDED_SHA256
```

`execution_mode=scripted` 只说明工程链路。真实指标来自 live，不同模型、协议或任务集合分母分开报告；0/0 保留 unknown。

## 6. 资产、诊断与 Slurm

提交前用 [stage_flash_sif.sh](tau-knowledge/preliminary/scripts/stage_flash_sif.sh) 预置固定官方 digest 的 SIF。它使用共享缓存和临时目录、受限 mksquashfs 并行度，成功后写 image receipt/hash，不覆盖已有镜像。镜像构建结果与实际资格检查状态见 RESULTS，不从脚本存在推断资产已就绪。

推荐用 [submit_qualification.py](tau-knowledge/preliminary/scripts/submit_qualification.py) 提交独立短时资格检查。它默认 dry-run，显式 `--submit` 前验证资产；固定良性 compiler 输入随源码和配置封入请求，2 小时作业只执行资格检查/probe，不创建 batch 或 deployment。[qualify_batch_runtime.py](tau-knowledge/preliminary/scripts/qualify_batch_runtime.py) 是该计算节点作业内部 CLI。[diagnose_benign.py](tau-knowledge/preliminary/scripts/diagnose_benign.py) 仅对历史 artifact 做离线审计，不调用模型，也不重新计算 official reward。参数以各脚本 `--help` 为准。资格结果和历史审计分别保存，不能代替完整批次结果。

资格检查可先验证服务，再执行固定查询的检索覆盖诊断，最后才运行可选 compiler probe。`--retrieval-queries` 的输入随提交请求封存；[benign-diagnostic-queries.json](tau-knowledge/preliminary/configs/benign-diagnostic-queries.json) 是旧 Qwen `tau-preliminary-20260905T185948.761519Z-4f615a9089dc` 第一个 benign cell 的前两条原始 query。旧 session 有三条 query，新诊断遵守 r8 最多两条上限，不能称为完整旧 session 的复现。

检索 probe 只比较相同 query 和原始良性语料上的 BM25 Top-10 与 hybrid 通道/展示并集；Platinum 002、007、010 仅作报告侧 reference labels，不参与排序、query 或 Agent 输入。Hybrid 每 query 可展示二十篇，BM25 基线为十篇，因此不能称为等候选预算的有效性对比；没有 Agent 选文、任务 utility 或 ASR 结论。

```bash
# 默认 dry-run；不提交作业、不启动模型
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/submit_qualification.py \
  --spec experiments/tau-knowledge/preliminary/configs/generation-benign-10.example.yaml \
  --output /absolute/path/new-qualification \
  --retrieval-queries experiments/tau-knowledge/preliminary/configs/benign-diagnostic-queries.json
```

可另加 `--compiler-input`，指向固定 GPT-5.5 r5 benign 十篇文档输入：`/usr/xtmp/tc442/skill-creation/runs/tau-codex-gpt55-live/tau-preliminary-20260905T231122.078159Z-a2450658dcb1/cells/01-mock-api-call-benign/compiler/input.json`。提交前逐篇核对官方正文，只将任务和这十篇良性文档封入请求；它用于固定输入的知识保留诊断，不运行用户模拟器或 deployment。正式提交须使用新的实际 output 路径并显式添加 `--submit`。

```bash
# 默认 dry-run：验证 spec、计算源码身份、打印命令，不启动模型或提交作业
bash experiments/tau-knowledge/preliminary/scripts/submit_generation.sh --spec /absolute/path/generation.yaml
bash experiments/tau-knowledge/preliminary/scripts/submit_evaluation.sh --spec /absolute/path/evaluation.yaml
```

分别加 `--submit` 才提交对应阶段。创建不会触发评估。提交前验证 runtime assets，封存 canonical job request 与确定性 source bundle；打印 job ID 后退出，不自动轮询。

Bundle 包括当前 worktree 中必需的未提交 v2 模块、测试、配置，排除 ignored 数据、模型、容器、缓存与 runs；已删除 tracked 文件不再打包。作业验证 request、archive、manifest 和逐文件 hash，在独立目录运行。不同生成来源保留原 source identity。

Flash-Next 申请 4 × RTX Pro 6000、32 CPUs、512 GiB RAM；独立 27B 诊断申请 2 × A5000、16 CPUs、128 GiB RAM。显式时限 12 小时，日志在 `/usr/xtmp/<user>/skill-creation/logs/`，仅使用 Slurm 分配 GPU。模型、embedding、兼容 SIF 必须预置；dry-run 的 `NOT_CHECKED_DRY_RUN` 不代表资产已就绪。

独立 `cuda_runtime.py` helper 已有离线测试，但尚未接入 batch 服务或资格入口，未完成真实 CUDA 初始化验收。它不表示已自动启用驱动兼容路径，也不表示已支持单卡 27B 提交。

创建启动 owned main + embedding 服务，评估仅启动 main；失败或退出清理自有进程。worker 环境使用明确 allowlist，不继承凭据、代理或任意加载钩子。本次不提供旧 r7 的 `phases`、`tau_flash_*.sbatch` 或独立 engineering-smoke 执行入口；历史协议和已有结果用于只读归档。

## 7. AppWorld

AppWorld 官方 JSON 在 `appworld/preliminary/data/appworld-0.1.0/`。457 个原始 endpoint 过滤为 447 个 task-facing resources；一 endpoint 一 Page，完整稳定 JSON 是正文。当前共享 BM25 只索引正文，不额外拼接 metadata。

`bootstrap.sh` 只检查项目 Python；`run_preliminary.py` 只读取已有四语料 bundle，检查 Agent Top-5 / evaluator Top-10 的 `search_web → open_page` 边界，不运行新模型矩阵。`replay.py` 验证既有完整历史 artifact，要求外部 `complete.json` hash；它不是离线 `report.json` 的专用 verifier。旧配置和日期计划不能用于新代码下续跑。

## 8. 维护与研究背景

全仓检查用 `make check`。批次、CLI、bundle、隔离、官方 evaluator 接口分别验证；通过测试不等于提交或完成真实模型实验。

[威胁模型](../analysis/02_threat_model.md)、[研究设计](../analysis/03_experiment_design.md)、[检索依据](../docs/retrieval-realism.md)、[GPU 历史测量](../docs/gpu-compatibility.md) 和 [静态归档分析](../docs/dymalskill-static-review.md) 保留研究论证与原始证据。旧 frozen protocol、日期计划、原始数据及 immutable artifact 不随本次文档去重改写。
