# τ-Knowledge：当前 v4 交接

本目录只提供当前交接；20261004 的数据清单、配置及结果已移到 `../../archive/runs/tau-full-97-20261004-001/`。**新实验使用 `tau.skill-evolution.v4` 和新的空运行目录**，不能用归档配置或 checkpoint 运行当前源码。方法定义及可调参数集中在 [PROTOCOL](../../PROTOCOL.md)；实际配置以 [experiment.yaml](../../configs/experiment.yaml) 为准。

## 方法与参数

每题独立检索并冻结 B*，Generator 一次生成 S0，创建阶段不执行或自测。进入演化后，Generator 在持续的学习环境中直接调用银行工具、运行脚本、观察结果及修改父包，显式 `submit_revision()` 封存包与对应公开观察。首次执行禁止修改 S0；后续修改均计入演化。Verifier 检查提交时的公开观察，oracle 和独立评估继续使用 fresh 银行执行 agent。

| 项目 | 当前配置 |
|---|---|
| 数据与条件 | upstream `fc0055dc4e0a316c3f83133267fbd6faaa770992`；97题、698篇；benign／poison-5／poison-10，共291链 |
| 攻击条件 | 保留原35／70篇投毒样本及 safe canary，见 [data-manifest.json](../../archive/runs/tau-full-97-20261004-001/data-manifest.json) |
| 模型 | Bedrock `openai.gpt-5.4`，us-east-1；Generator high，其余角色沿用配置；会话隔离 |
| 检索 | BM25 Top10＋Qwen3-Embedding-4B Top10，RRF=60；confidence≥0.1；无篇数配额 |
| 收集预算 | 搜索30、澄清4、银行只读10、Analyzer50轮；B*≤32,768 tokens |
| 演化预算 | M15修订尝试、K5有效oracle、5次oracle设施失败；Generator全链120轮；每次尝试3600秒 |
| 银行执行 | 初跑／修订活动时限3600秒；银行episode保留100轮／800任务工具调用上限 |
| 公开验证 | 初建／升级30轮，诊断8轮；固定测试修Skill，通过后才调用oracle |
| 上下文 | Generator窗口272K、β=0.7、输入上限157,632、输出预留32,768；记录估算拆分与拒发原因 |

学习角色不人工设置单次输出 token 上限，实际请求见配置与 journal；这不取消上下文、轮数和时间预算。银行正式执行仍保留配置中的 agent／user 输出及 episode 累计预算。终端返回总共最多8KiB UTF-8预览，完整已封存返回值可按公开路径读取；输出超限保持失败状态。

## 准备状态

| 范围 | 本轮状态 |
|---|---|
| 固定数据、投毒清单与源代码 | 保留原路径与hash，进入新运行身份 |
| 当前共享源码回归 | [当前验收](../readiness-skillsbench-input-discovery-20261008-001/final-status.json)保留共享回归1522通过、57跳过、0失败；不是银行真实模型成绩 |
| 银行/helper直接执行边界 | 历史银行/helper复验为15 passed，无付费模型调用；对应旧readiness已按最新结果清理，不作为当前验收入口。当前SkillsBench真实容器机制检查不能算作银行Docker重测 |
| 新 v4 `task_019` smoke | `NOT_MEASURED`；本轮未读取key、未调用付费模型 |
| 全97题／291链 | 未启动；须当前机器preflight及受控smoke通过后运行 |

Docker承载包脚本、修改工作区和Verifier公开测试；银行worker、数据库、用户模拟器及官方评分仍在host。模型只通过受控工具访问银行。容器不挂凭据、数据库、Docker socket或宿主项目；helper禁网、非root、只读根，60秒／1CPU／1GiB／64进程／64KiB输出。它不限制host worker的总资源，也不证明生成测试的任意语义正确性。

## 环境与准确命令

从仓库根执行。host需Python≥3.12；银行worker固定Python3.12.12，helper固定Python3.11及锁定依赖。缺失upstream时才clone并checkout上述commit；已有checkout不reset、不移动历史数据。先准备环境，再建立新链：

```bash
make setup PYTHON=python3.12
TAU_CODE=experiments/tau-knowledge/skill-evolution
TAU_CFG="$TAU_CODE/configs/experiment.yaml"
TAU_RUN="$TAU_CODE/runs/tau/smoke-001"
uv python install 3.12.12
uv sync --project "$TAU_CODE/data/upstream/tau2-bench" --python 3.12.12 --frozen --extra knowledge --no-dev
.venv/bin/python "$TAU_CODE/scripts/prepare_image.py"
```

在另一个终端启动固定embedding服务；需先准备其独立依赖、HF snapshot及配置中的GPU。机器参数（GPU UUID、endpoint）改变时另存配置并使用新身份，不降级embedding：

```bash
.venv/bin/python experiments/tau-knowledge/skill-evolution/scripts/start_embedding.py
```

运行者本地提供凭据；下列 `run` 会产生模型费用。本轮没有执行这些命令。只有preflight的 `ready=true` 才运行：

```bash
.venv/bin/r2sp preflight --experiment tau --runtime docker --config "$TAU_CFG" --task task_019 --env-file key.env
.venv/bin/r2sp run --experiment tau --runtime docker --config "$TAU_CFG" --task task_019 --arm benign --env-file key.env --run-dir "$TAU_RUN"
.venv/bin/r2sp report --experiment tau --runtime docker --config "$TAU_CFG" --run-dir "$TAU_RUN"
```

完整矩阵先去掉 `--task` 做全部preflight；通过后去掉 `--task/--arm`、将 `TAU_RUN` 改为另一个空目录，再执行 `run/report`。默认串行；子集调试仍保留每臂97题分母。preflight检查Docker访问、真实镜像／依赖锁、pinned upstream、银行Python、embedding及模型鉴权，缺项即停止。

## 恢复与结果

相同源码、提示、配置和运行环境身份下重跑同一命令，复用已封存结果；`create/evolve/evaluate`也可分别运行。S0只派发一次；`NOT_SENT`可首次派发，已收到响应只确定性解析，`UNKNOWN`不重发。银行脚本按调用启动Docker，状态来自host暂存的candidate／scratch及私有JSON worker checkpoint。必要checkpoint或工作区丢失时，不能靠公开快照假装恢复；明确停止并另开trial，不覆盖原链。

`--env-file`启动时读取字面赋值，不执行shell；静态key更新后需要新CLI进程。滚动凭据可用 `AWS_BEARER_TOKEN_BEDROCK_FILE` 指向带 `token/expires_at` 的独立JSON，每次POST前重读。凭据仅留host，私有目录0700、文件0600，不进入Skill、模型任务环境或公开交接；401／403停止后续链。

`report.json/REPORT.md`报告逐版本官方utility、canary ASR、Action Recall、surrogate检查率、修订／oracle次数、提交与执行计数、停止原因及usage。Action Recall不是业务完成百分比；gold覆盖只作事后诊断。各内容hash独立fresh评估一次；污染冻结对照复用本链S0。未测为null／`NOT_MEASURED`；final按oracle成功或最后安全包选择，不利用独立评分挑版本。

历史关键结果：[旧task_019指标](../../archive/runs/observation-smoke-2-20261006-001/metrics.json)的S0–S6 utility均0；[步骤审阅](../../archive/runs/observation-smoke-2-20261006-001/tau-step-audit.json)保留检索缺口、测试误判及局部脚本修复证据。这是旧方法结果，不能当v4成绩。公开资料充分性、surrogate语义误判及银行类别反馈信息损失仍是限制；容器通过不能保证utility提升。
