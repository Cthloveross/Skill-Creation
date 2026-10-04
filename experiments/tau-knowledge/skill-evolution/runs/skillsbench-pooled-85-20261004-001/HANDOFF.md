# SkillsBench 85题共享资料池交接

这份交接运行`skillsbench.skill-evolution.v1`：**作者发布的85题，benign，共85条独立Skill链**。仅将全部85题的`background_docs`合并检索；当前题的instruction和environment作为提供的任务输入。每题分别收集B*、一次生成S0，再M15/K5演化和逐版本独立评分。不是共享一个跨任务Skill，也不是原CoEvo完整复现。方法和参数见[PROTOCOL](../../PROTOCOL.md)。

## 1. 交付内容与实际状态

| 项目 | 交接时状态 / 证据 |
|---|---|
| 配置/计划分母 | [config.yaml](config.yaml)、[matrix-manifest.json](matrix-manifest.json)，85题、仅benign |
| 固定源 | CoEvoSkills commit `4380d4bff673dd6e1d58e5babeb2aaa0fe527119`；85题/1314源文件，[data-manifest.json](data-manifest.json) |
| 共享检索池 | 85篇`background_docs`/122块；instruction与environment不入池，准备后本地生成`data/skillsbench/corpus/manifest.json` |
| 本题提供输入 | 85题共869个公开文件的执行清单，32个environment文件排除；这是公开范围，不是检索池；公开清单见[data-manifest.json](data-manifest.json) |
| Dense索引 | 122×2560维、1,249,280字节；背景块与旧封存向量逐项核对后建立新索引，固定tokenizer重载通过，0次embedding/生成请求；[DENSE_VALIDATION.json](DENSE_VALIDATION.json) |
| 3D演示环境 | 本机真实Bubblewrap隔离/生命周期/官方负例检查通过；原始probe和环境保留本地，不是模型成绩 |
| 首次`smoke/` | 24次Analyzer调用、18次搜索，B*为1块/293 tokens、`budget_exhausted_incomplete`；一次Generator已完成响应带多余JSON结尾，`CREATION_FAILED`，之后全部NOT_MEASURED |
| 格式能力探针 | 真实GPT-5.5 strict JSON schema请求HTTP200，`ready=true`、52 tokens；[STRUCTURED_OUTPUT_PROBE.json](STRUCTURED_OUTPUT_PROBE.json)，不是S0/任务成绩 |
| 当前`smoke-002/` | 完成，进程退出0；Surrogate2/2、oracle一次通过、独立reward=1/utility=true/官方检查2/2；[BASE_REUSE.json](BASE_REUSE.json)、[SMOKE_REPORT.json](SMOKE_REPORT.json) |
| 可查看的公开产物 | [冻结B*](SMOKE_BASE.json)、[S0的SKILL.md](example-skill/SKILL.md)及`example-skill/scripts/`，package manifest保留原完整hash；不是恢复用journal |
| 正式85题 | 未启动、0正式镜像就绪；Docker socket拒绝访问，真实逐题grader和资源边界未验证 |
| 实现/测试hash | [SOURCE_HASHES.json](SOURCE_HASHES.json)、[VALIDATION.json](VALIDATION.json)、两份检查log |

父目录不作为checkpoint。本机首轮`smoke/`保留失败记录，当前新演示在`smoke-002/`，`matrix/`未启动。GitHub仅交付pipeline和两个父目录的公开配置、清单、hash、验收、probe与汇总；不含密钥、原始data/rootfs、原始checkpoint/journal或私有评分。**公开快照不可直接恢复**，同事须准备本地环境，在新空目录开始；CLI会创建运行目录。3D探针不证明其他84题可运行，85题配置不等于环境就绪。

首轮资料停止是**Analyzer输入上下文上限**：已发送24轮，最后输入估计113592 tokens；下一轮预计116849超过114688，因此没有发送。仍有12次搜索/26轮决策余量，B*293远低于32768容量；18次成功搜索共返回283块、74个唯一ID，本题背景18次均排第1。4次文档评分遗漏和2次非法充分性freeze被控制器拒绝，最后合法选择保留1块。`budget_exhausted_incomplete`没有证明搜索找不到或30次搜索用完；当前Collector累积完整候选导致上下文先耗尽，资料充分性仍未成立。

首轮Generator仅一次已完成响应，JSON多余结尾导致解析失败；没有生成可封存包，也没有执行、自测或重发。新`smoke-002`是显式方法修复后的新身份，仅复用相同hash的FrozenBase和公开输入/检索契约，provenance见[BASE_REUSE.json](BASE_REUSE.json)；未迁移旧Analyzer推理、Generator响应、journal或评分。新一次S0为`SKILL.md`加3个scripts，hash `0bf7580c4c565a1cad6890fa31450fe27b0d40c6c7b198097a20ae31faa911b7`，已完成整个后续链。

| 实际测量 | `smoke-002`结果 |
|---|---|
| 公开验证 | 2/2通过；Verifier测试程序修复1次，修正密度单位换算 |
| Skill内容演化 | 0次修订，仅S0；测试修复不算Skill进化 |
| Fresh oracle | 1次/pass，停止`oracle_success` |
| Fresh独立评价 | 官方reward=1、utility=true、官方检查2/2、grader退出0 |
| 模型用量 | 18个已完成响应：Generator1/Verifier3/execution14；input249760/output33621，cached input108100 |
| 首轮与探针用量 | 首次收集/失败创建另记25个响应，input1853035/output125177；格式探针另记52 tokens |
| 费用/适用范围 | 美元费用NOT_MEASURED/null；Bubblewrap demo，不是正式矩阵，也不证明演化改善 |

该成功链只复用首轮B*，没有第二次独立资料收集；原`budget_exhausted_incomplete`仍如实保留。真实结果证明已有冻结资料后的包创建、执行、公开验证、fresh oracle和独立评分路径可用，不证明全部85题环境或资料充分性判断已解决。

## 2. 同事先执行什么

以下从实际仓库根、同一个终端执行：

```bash
make setup                 # 宿主Python≥3.11；uv.lock冻结安装
make check                 # 离线，不调用模型
SB_CODE=experiments/tau-knowledge/skill-evolution
SB_RUN="$SB_CODE/runs/skillsbench-pooled-85-20261004-001"
SB_CFG="$SB_RUN/config.yaml"
SB_KEY=key.env             # 同事本机自己的凭据文件
SB_SMOKE="$SB_RUN/smoke-colleague-001"  # 新空目录，CLI首次运行时创建
```

使用Bedrock GPT-5.5/us-east-1，Generator high，其余生成/执行角色medium。key文件支持字面赋值或单行裸token，仅host读取，不复制当前key、不写入run。**进程已导出的值优先于env-file**：换key后必要时先`unset AWS_BEARER_TOKEN_BEDROCK`再加载文件。preflight只读模型目录，不生成；run会付费。本次真实请求HTTP200，后续运行仍需自行preflight。当前只有Generator使用strict外层包schema；公开轨迹已改为状态/产物，不转发executor自由文本。

## 3. 数据与检索环境

固定源和当前题公开输入保留原位置；共享池已改为只包含背景资料，旧全公开文件Dense索引不再适用。不要为重跑而改固定源。缺失时准备入口如下：

```bash
.venv/bin/python "$SB_CODE/scripts/prepare_skillsbench.py" --source
"$SB_CODE/data/embedding/.venv/bin/python" "$SB_CODE/scripts/prepare_skillsbench.py" --pool
```

采集阶段直接给Analyzer当前题instruction全文、environment公开文件manifest与运行说明。Analyzer只搜索85题的85篇`background_docs`：按固定Qwen tokenizer 2048/overlap128分成122块，ID含任务/源路径/offset；B*选择完整返回块，**不保证整个背景文件都入选**。当前题instruction、Dockerfile、数据、代码和其他environment文件不进入BM25/Dense索引，不产生二进制摘要检索块。

environment公开范围按原Dockerfile COPY/ADD和dockerignore确定，不自动暴露整个目录。公开项目测试、baseline和待填模板仍作为当前题输入保留，隐藏tests/grader/答案/solution/作者旧Skill排除。执行时提供当前题原始公开文件及原依赖，不挂其他题或完整仓库；原始输入没有因退出检索池而删除。

源文件hash、公开/排除原因和目的路径在本地public/source manifests；共享池来源及块offset在准备后生成的`data/skillsbench/corpus/manifest.json`。这些原始数据路径不随GitHub公开快照下载。pool scope、public/corpus hash和Dense文档顺序都须与当前快照一致，不能手动改hash复用旧索引或旧checkpoint。

当前池为`skillsbench.pool.v2 / background_docs_only`，corpus hash为`03e78db74ba3b820e3d925b89870486d9e2f4c74064585f6629bf2eaf2d72fc7`。校验器拒绝旧池及instruction/environment来源，要求全部背景文件都有检索块。旧索引与准备记录保留在原hash目录；新索引只复用逐块内容、tokenization和模型契约一致的背景向量。公开输入清单与原始文件保留，数据值在执行时读取，不要求它们进入B*。

**2026-10-04真实检索检查：**生产检索器先运行5题的10个公开短查询，再运行全部85题公开instruction原文查询；没有使用隐藏答案或grader来组织查询。95次返回均与背景原文/hash一致，记录见[RETRIEVAL_PROBE.json](RETRIEVAL_PROBE.json)。

| 85题公开instruction查询 | 对应背景首块第1 | 对应背景首块前10 | 返回对应背景块 |
|---|---:|---:|---:|
| BM25单路 | 59/85 | 76/85 | 112/122 |
| Qwen Dense单路 | 79/85 | 85/85 | 122/122 |
| 实际RRF融合返回 | 70/85 | 85/85 | 122/122 |

85次全文查询均正常返回，每题背景全部块均被返回；融合首块前3为77/85、前5为82/85，5题的10个短查询对应背景首块均第1。此处统计公开来源映射覆盖，不是隐藏gold或utility。

同10个短查询在旧42,498块池中背景也全部命中，但首块第1仅3/10，新池10/10。旧候选大量混入environment/instruction，新池仅背景。该对照证明排名和候选集中度变化，不证明任务成功率提高，详见[OLD_POOL_RETRIEVAL_PROBE.json](OLD_POOL_RETRIEVAL_PROBE.json)。

检索探针没有运行付费Analyzer、冻结、S0或演化；此后的真实smoke单独记录。查到全部现有背景不代表资料足够或Analyzer最终筛选正确，也不能把τ漏检归因于4B模型。当前题原始输入仍在执行时提供。

检索固定Qwen3-Embedding-4B revision `5cf2132abc99cad020ac570b19d031efec650f2b`、2560维，Top10+10/RRF60。需要本机`data/embedding/.venv`、固定HF缓存和适配GPU；本仓库没有任意新机器的一键GPU安装。缺环境先恢复，不能换模型。服务未启动时另开仓库根终端：

```bash
.venv/bin/python experiments/tau-knowledge/skill-evolution/scripts/start_embedding.py
```

默认`http://127.0.0.1:18140/v1`，脚本读默认embedding设置，必须与快照一致。仅复用通过当前背景资料池hash校验的索引；使用已准备的embedding环境按本快照重建：

```bash
.venv/bin/python - "$SB_CFG" "$SB_CODE/scripts/prepare_skillsbench.py" <<'PY_INDEX'
import json, subprocess, sys
from pathlib import Path
from tau_skill_evolution.spec import load_spec
spec = load_spec(Path(sys.argv[1]))
embedding_python = spec.root / "data/embedding/.venv/bin/python"
subprocess.run([str(embedding_python), sys.argv[2], "--index-settings", json.dumps(spec.values["embedding"])], check=True)
PY_INDEX
```

上述检索准备是本地推理，不调用Bedrock生成；最终readiness/hash校验必须通过。

## 4. 先跑一个完整smoke

本机3D rootfs已准备则先preflight；缺失时先准备：

```bash
.venv/bin/python "$SB_CODE/scripts/prepare_bubblewrap.py"
.venv/bin/python "$SB_CODE/scripts/prepare_skillsbench.py" --demo --task 3d-scan-calc
.venv/bin/r2sp preflight --experiment skillsbench --config "$SB_CFG" --demo --task 3d-scan-calc --env-file "$SB_KEY"
# 仅ready=true时继续：
.venv/bin/r2sp run --experiment skillsbench --config "$SB_CFG" --demo --task 3d-scan-calc --arm benign --env-file "$SB_KEY" --run-dir "$SB_SMOKE"
```

使用完整M15/K5，依次create/evolve/evaluate/report。必须实际封存检索、B*、唯一S0、公开验证、fresh oracle和独立评分；utility0可算有效测量，未知请求/验证程序错误/缺oracle不能标完整跑通。S0成功早停可以0修订。官方负例环境探针exit0但reward0，只证明评分不取shell退出码，不是该smoke成绩。

上面的命令用于同事的新链。本机当前进度在`$SB_RUN/smoke-002`；只有原机相同源码/配置/运行锁才能恢复它，不可复制GitHub公开汇总作为checkpoint。当前只读查看本机记录：

```bash
.venv/bin/r2sp report --experiment skillsbench --config "$SB_CFG" --demo --task 3d-scan-calc --arm benign --run-dir "$SB_RUN/smoke-002"
```

3D demo独立rootfs：Python3.11.14、NumPy2.2.6、pandas2.2.3、pytest8.4.1、pytest-json-ctrf0.3.5；[runtime锁](../../runtime/skillsbench-bubblewrap-lock.json)、[依赖hash锁](../../runtime/skillsbench-requirements.lock)。1CPU affinity、每进程4GiB、每UID64进程、60秒/64KiB；grader按官方900秒。没有完整cgroup聚合资源限制，始终`formal_matrix_result=false`；不把银行脚本rootfs用于SB，不能用此环境宣称85题已验证。

## 5. 正式85题：准备条件与当前缺口

**当前不能直接交给同事启动完整矩阵。**先开放Docker访问，再逐题完成官方环境、Verifier和私有grader准备及真实预检：

```bash
docker info
.venv/bin/python "$SB_CODE/scripts/prepare_skillsbench.py" --docker --task 3d-scan-calc
```

有Docker权限后的批量准备入口是下面的循环，它不是已执行记录，也不保证每题都能构建：

```bash
.venv/bin/python - "$SB_CFG" "$SB_CODE/scripts/prepare_skillsbench.py" <<'PY_ENV'
import subprocess, sys
from pathlib import Path
from tau_skill_evolution.spec import load_spec
for task in load_spec(Path(sys.argv[1])).tasks:
    subprocess.run([sys.executable, sys.argv[2], "--docker", "--task", task], check=True)
PY_ENV
```

需处理的实际限制：

- 原题环境不统一；当前准备脚本需要原镜像的Python3/pip。`lean4-proof`、`fix-build-google-auto`等原Dockerfile未准备这条工具链，尚需完善正式工具运行环境，现实现会明确失败，不填假digest。不能把银行统一依赖装进全部任务就称准备完毕。
- 正式运行保留原题依赖；当前题文件在fresh可写副本，源码/config可以修改，宿主源/Skill包/镜像根/Verifier产物保持隔离。Verifier依赖独立`/.tau-verifier`；grader缓存仅私有`/opt/tau-grader`。预热只复用实际成功的精确安装命令，官方测试字节不变。
- 45题原配置允许联网、40题禁网；正式execution遵从该声明。Verifier和grader禁网。每终端调用统一60秒/64KiB，可能额外限制长编译；Docker调用不保留跨调用后台服务，storage_mb尚无聚合磁盘配额。这些是适配限制，需在相关题真实验证后决定新方法是否调整。
- 单题锁`runtime/skillsbench-docker-<task>-lock.json`必须含真实三套镜像ID、源/公开池/依赖/recipe hash；缺锁、依赖或实际grader探针通过都不得ready。`trend-anomaly-causal-inference`缺失作者Skills COPY只在独立build recipe删除并记录hash，pinned checkout保持不改。

85题都通过后才执行：

```bash
.venv/bin/r2sp preflight --experiment skillsbench --config "$SB_CFG" --env-file "$SB_KEY"
# 全部ready=true后：
.venv/bin/r2sp run --experiment skillsbench --config "$SB_CFG" --env-file "$SB_KEY" --run-dir "$SB_RUN/matrix"
```

不带demo/task/arm过滤才是完整85链。正式矩阵本次未启动，不降级宿主，不把mock或3D探针标为实际Docker验证。

## 6. 恢复、报告和产物

普通中断在同身份下重跑同一`run`命令。调试单阶段将`run`换成`create/evolve/evaluate/report`，demo包括report都保留`--demo --task 3d-scan-calc --arm benign`。report无需凭据：

```bash
.venv/bin/r2sp report --experiment skillsbench --config "$SB_CFG" --demo --task 3d-scan-calc --arm benign --run-dir "$SB_SMOKE"
.venv/bin/r2sp report --experiment skillsbench --config "$SB_CFG" --run-dir "$SB_RUN/matrix"
```

HTTP401/403停止本次后续chain；换有效凭据并通过下一次预检后，`run`保留原失败链的未测记录，继续未启动链。未知S0或其他未知操作不重发、不删除journal绕过。源码/配置/提示/锁变化须新checkpoint；父SOURCE_HASHES是交接时点，journal绑定首次建立时身份。正式准备改变runtime锁后，在尚空的matrix建立新正式身份，不能复制demo进去。

checkpoint的`report.json / REPORT.md`给出每版utility、官方reward、可取得的official_checks通过率、停止原因、包/测试hash、revision/oracle次数；原始阶段记录在`cells/<task>/benign/journal/`，包在`initial/versions`，公开产物在`artifacts/<task>/`。`usage.jsonl`只含成功响应数值usage，缺美元账单时费用NOT_MEASURED。

评分必须读取官方`/logs/verifier/reward.txt`；有限[0,1]reward原样保存，完整utility仅`reward==1`。正常0分exit0/1可有效评分，缺reward、依赖/收集/超时等错误为NOT_MEASURED/null；官方检查缺失也未测。这里没有银行Action Recall或canary，ASR为null/NOT_APPLICABLE。独立评分不回流学习，final取oracle成功包，否则最后安全包，不能按独立reward挑最好。

## 7. 参数与验收

搜索30/Analyzer50轮，B*32768、confidence0.1；澄清/银行只读固定0。搜索仅在85篇背景资料/122块中进行，instruction与environment是本题提供输入。相关性筛选没有块数配额，完整块不截断，但背景源文件可能只选部分块。M15/K5、Generator high/272K窗口/β0.7是当前设置；admission使用固定Qwen序列化文本估算，不是GPT原生token。可调范围见[协议](../../PROTOCOL.md#2-配置参数与变体)。

最新本机`make check`为547通过/12跳过；干净分发检查为535通过/24跳过，Ruff、71文件格式、编译和两域配置全部通过，日志见[PUBLISH_FRESH_CHECK.log](PUBLISH_FRESH_CHECK.log)。数据/rootfs相关集成默认显式跳过，不要求fresh clone带本机数据。此前真实Bubblewrap有7项边界检查，Docker真实集成未验证。首轮创建失败；新`smoke-002`在复用B*后完成真实后续链，原失败不改写成成功。未测项保留85固定分母/null，版本只展开实际安全封存内容。
