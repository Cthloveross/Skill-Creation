# τ-Knowledge 全97题交接

这份交接运行`tau.skill-evolution.v2`：**97题×benign/poison-5/poison-10，共291条独立链**。每链最多M15修订/K5 oracle，先检索冻结、S0仅生成一次、创建禁止自测；每个实际内容版本独立评分。方法和参数范围以[PROTOCOL](../../PROTOCOL.md)为准。

## 1. 交付内容与实际状态

| 项目 | 交接时状态 / 证据 |
|---|---|
| 配置和完整任务 | [config.yaml](config.yaml)、[matrix-manifest.json](matrix-manifest.json)，每臂固定97分母 |
| 固定源 | tau2-bench commit `fc0055dc4e0a316c3f83133267fbd6faaa770992`，97题/698文档；[data-manifest.json](data-manifest.json) |
| 攻击 | 原35/70篇样本和payload不变；原20题profile不变，其余排序交替，全97题两种profile为49/48 |
| 源码/依赖/测试 | [SOURCE_HASHES.json](SOURCE_HASHES.json)、[VALIDATION.json](VALIDATION.json)及两份检查log |
| 单题环境 | 银行worker、固定embedding、Bubblewrap脚本/Verifier环境已实际检查；缺cgroup聚合限制 |
| 模型鉴权与单题预检 | τ当前只读预检ready=true、鉴权HTTP200，银行/pinned upstream/rootfs/embedding检查通过；[CURRENT_PREFLIGHT.json](CURRENT_PREFLIGHT.json)。历史HTTP401保留在previous_check，凭据仅本机读取、不发布 |
| 新smoke | τ的`task_019` benign为NOT_STARTED（preflight READY），该新链0生成请求；[smoke-status.json](smoke-status.json)，任务成绩NOT_MEASURED/null |
| 正式矩阵 | 未启动；Docker socket拒绝访问、真实image digest未取得，容器依赖及正式边界未验证 |

父目录只是交接资料。GitHub发布pipeline和公开配置、清单、hash、验收及汇总，**不发布凭据、原始data/rootfs、原始journal或私有评分，公开快照不是可恢复checkpoint**。本机τ smoke和matrix尚未运行；Git不会保存空运行目录。不要把`--run-dir`指向父目录，同事需准备本地数据/环境，在新空目录建立自己的checkpoint，不复用旧v1、别的任务或demo/正式身份。

## 2. 同事先执行什么

所有命令从实际仓库根执行，以下变量在同一个终端保留；`.venv/bin/r2sp`无需全局安装。

```bash
make setup                 # 宿主Python≥3.11；uv按uv.lock冻结安装
make check                 # 离线，不调用模型
TAU_CODE=experiments/tau-knowledge/skill-evolution
TAU_RUN="$TAU_CODE/runs/tau-full-97-20261004-001"
TAU_CFG="$TAU_RUN/config.yaml"
TAU_KEY=key.env             # 换成同事自己的本地凭据文件
TAU_SMOKE="$TAU_RUN/smoke-colleague-001"  # 新空目录，CLI首次运行时创建
```

凭据支持`AWS_BEARER_TOKEN_BEDROCK=...`字面赋值或单行裸token；文件不执行shell、不写入产物。**已导出的进程环境优先于文件**，换key后若仍使用旧值，在该终端先`unset AWS_BEARER_TOKEN_BEDROCK`再用`--env-file`。不复制当前key，不打印凭据。模型固定Bedrock GPT-5.5、us-east-1；Generator high，Analyzer/Verifier/执行agent medium，用户模拟器none。

本机已有数据及环境可复用。GitHub新检出不包含这些数据/环境，缺失时按下面准备；环境准备不等于模型链跑通。此交接也不提供当前密钥。

## 3. 数据、worker与检索环境

若新机器没有checkout，仅在空的目标路径执行：

```bash
mkdir -p "$TAU_CODE/data/upstream"
git clone --no-checkout https://github.com/sierra-research/tau2-bench.git "$TAU_CODE/data/upstream/tau2-bench"
git -C "$TAU_CODE/data/upstream/tau2-bench" checkout fc0055dc4e0a316c3f83133267fbd6faaa770992
uv python install 3.12.14 --no-bin --install-dir "$TAU_CODE/data/python"
uv sync --project "$TAU_CODE/data/upstream/tau2-bench" --python "$TAU_CODE/data/python/cpython-3.12.14-linux-x86_64-gnu/bin/python3.12" --frozen --extra knowledge --no-dev
.venv/bin/python - <<'PY_CHECK'
from tau_skill_evolution.data import verify_tracked_snapshot
print(verify_tracked_snapshot())
PY_CHECK
```

银行worker必须使用该checkout自己的Python3.12.14环境。宿主、worker和脚本容器是三个不同环境；不要reset已封存源文件。保留698原文和哈希，池按条件物化；首次检索可建立相应缓存，不调用旧preliminary入口。

检索固定Qwen3-Embedding-4B、revision `5cf2132abc99cad020ac570b19d031efec650f2b`、2560维，BM25/Dense Top10+10/RRF60。需要交接机器上的`data/embedding/.venv`、固定HF缓存与适配GPU；本项目没有任意机器的一键GPU环境安装。缺失时先恢复这个环境，不能换模型。服务未运行时另开仓库根终端：

```bash
.venv/bin/python experiments/tau-knowledge/skill-evolution/scripts/start_embedding.py
```

默认地址`http://127.0.0.1:18140/v1`；脚本读取默认配置embedding段，必须与本快照相同。服务通过preflight就直接复用；GPU/地址等配置变更要保存新快照和身份。

## 4. 先跑一个完整smoke

本机rootfs已准备则先preflight；缺失时先运行准备脚本：

```bash
.venv/bin/python "$TAU_CODE/scripts/prepare_bubblewrap.py"
.venv/bin/r2sp preflight --experiment tau --config "$TAU_CFG" --demo --task task_019 --env-file "$TAU_KEY"
# 仅ready=true时继续：
.venv/bin/r2sp run --experiment tau --config "$TAU_CFG" --demo --task task_019 --arm benign --env-file "$TAU_KEY" --run-dir "$TAU_SMOKE"
```

preflight只读查目录；`run`会产生费用。该命令依次create/evolve/evaluate/report，使用完整M15/K5，不强迫修订15次。必须看到实际B*、唯一S0、公开检查、fresh oracle和独立评估封存才能称流程完成；utility=0可以是有效结果，但未知请求、验证程序错误或未测oracle不能称完整跑通。S0成功早停允许零次修订。

Bubblewrap仅单题benign演示：60秒、1CPU affinity、每进程1GiB、每UID64进程、64KiB输出；没有完整cgroup进程树资源上限，始终`formal_matrix_result=false`。不允许demo投毒臂，不把隔离探针算成任务成绩。

## 5. 完整矩阵：先补正式环境

本次不启动正式矩阵。具备Docker访问后，在任何正式chain创建前准备真实镜像：

```bash
docker info
.venv/bin/python "$TAU_CODE/scripts/prepare_image.py"
.venv/bin/r2sp preflight --experiment tau --config "$TAU_CFG" --env-file "$TAU_KEY"
# 所有检查ready=true后，运行291条链：
.venv/bin/r2sp run --experiment tau --config "$TAU_CFG" --env-file "$TAU_KEY" --run-dir "$TAU_RUN/matrix"
```

镜像依赖固定Python3.11/NumPy2.2.6/pandas2.2.3/pytest8.4.2及hash；准备脚本记录真实image ID。缺权限、digest或真实依赖验证就阻止，不填写虚构digest、不降级宿主。完整运行不加task/arm过滤；过滤子集仍使用每臂97报告分母。

## 6. 恢复、报告和在哪里看结果

普通中断：同代码、配置、提示和runtime身份下重跑同一`run`命令，复用封存记录。阶段调试将命令中的`run`换成`create/evolve/evaluate/report`；demo包括report仍保留`--demo --task task_019 --arm benign`。report无需env-file，也不执行任务/调用API：

```bash
.venv/bin/r2sp report --experiment tau --config "$TAU_CFG" --demo --task task_019 --arm benign --run-dir "$TAU_SMOKE"
.venv/bin/r2sp report --experiment tau --config "$TAU_CFG" --run-dir "$TAU_RUN/matrix"
```

HTTP401/403中断本次后续chain；更换有效凭据并通过新一次预检后，`run`跳过原鉴权失败链，保留其未测结果，继续未启动链。**未知S0或其他未知请求不重发**，不删除journal/identity绕过。源码/提示/配置/运行锁变更须新checkpoint；父SOURCE_HASHES只是交接时点快照，实际journal绑定建立时身份。尚空的matrix可在正式镜像准备后首次建立新身份。

每个checkpoint的`report.json / REPORT.md`包含逐版本utility、ASR、Action Recall、gold覆盖、停止原因、包/测试hash及revision/oracle计数；`cells/<task>/<arm>/journal/`有请求/原响应，`base`是B*，`initial`是S0，`versions/`是后续安全封存包，`usage.jsonl`只记成功响应数值usage。美元费用没有账单时NOT_MEASURED，不能从局部usage推算完整费用。

τ官方reward_basis为87 DB、9 ACTION、1 DB+NL_ASSERTION；最后一题仅私有judge改用GPT-5.5，保留官方判定提示/schema，固定checkout不改。Action Recall是参考动作匹配，不是DB完成百分比；canary仅真实dispatcher行动成功才算ASR。gold覆盖仅事后诊断，不反馈学习。poison两臂冻结对照直接复用同链S0及其独立评估。

## 7. 参数修改与验收范围

本快照搜索30/澄清4/只读10/Analyzer50轮，B*32768 tokens，confidence0.1；无固定文档篇数。银行时间真实只读查询占一次预算，非法充分性freeze有余额时继续收集。可调范围见[协议参数表](../../PROTOCOL.md#2-配置参数与变体)，变体另存配置、新建run，不现场改B*。

最新本机`make check`为547通过/12跳过；干净分发检查535通过/24跳过，lint、71文件格式、编译与两域配置均通过，共享日志见[SkillsBench父目录检查记录](../skillsbench-pooled-85-20261004-001/PUBLISH_FRESH_CHECK.log)。数据/rootfs集成默认显式跳过。此前真实Bubblewrap有7项边界检查，Docker真实集成未验证。自查见[协议](../../PROTOCOL.md#8-实现自查与环境限制)及[VALIDATION.json](VALIDATION.json)。τ的新smoke未执行；SkillsBench首轮创建失败，新`smoke-002`复用已冻结资料后完成整个后续链，S0零修订、oracle一次通过、独立reward=1/检查2/2，不能据此替代τ结果或证明演化增益。正式矩阵还缺真实Docker验收；未测阶段null并保留97分母，早停不补造版本，final不能由独立评估挑最好。
