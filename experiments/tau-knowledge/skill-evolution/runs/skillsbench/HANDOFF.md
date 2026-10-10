# SkillsBench：当前流程与结果

当前方法是 **`skillsbench.skill-evolution.v7`**。唯一保留的最新模型实验为 [input-discovery-five-gpt54-20261008-003](input-discovery-five-gpt54-20261008-003/public-summary.json)，2026-10-08完成，使用 Bedrock `openai.gpt-5.4`、`us-east-1`。它包含五题的 NoSkill、S0、全部实际后续内容版本和 Final，不是完整85题矩阵。

## 1. 最新结果在哪里

| 记录 | 内容 |
|---|---|
| [public-summary.json](input-discovery-five-gpt54-20261008-003/public-summary.json) | 全部逐版本官方成绩、增减、包hash、选择来源和用量 |
| [public-acquisition-review.json](input-discovery-five-gpt54-20261008-003/public-acquisition-review.json) | 实际读取、查询、资料选择、缺口及停止原因；各题S0只有一次创建POST |
| [public-verification-review.json](input-discovery-five-gpt54-20261008-003/public-verification-review.json) | 公开测试、产物与修改过程的事后审查 |
| [public-summary-independent-review.json](input-discovery-five-gpt54-20261008-003/public-summary-independent-review.json) | 最终指标交叉核对 |
| [config.yaml](input-discovery-five-gpt54-20261008-003/config.yaml)、[source-identity.json](input-discovery-five-gpt54-20261008-003/source-identity.json) | 本批实际配置、源码和环境身份 |
| [admission.json](input-discovery-five-gpt54-20261008-003/preflight/admission.json) | 本机这五题启动前的环境及鉴权检查 |

`runs/readiness-skillsbench-input-discovery-20261008-001/` 保存**代码验收证据**，不是另一批Skill结果。[final-status.json](../readiness-skillsbench-input-discovery-20261008-001/final-status.json)记录共享回归1522通过、57跳过、0失败，以及真实Docker配合本地模拟provider的机制检查。模拟provider不产生真实模型成绩；该验收也不代表全部85题环境已就绪。

旧目录已清理；[清理复验](../readiness-skillsbench-input-discovery-20261008-001/cleanup-verification.json)记录本次全量检查、结果完整性和更新后的文档hash。原验收记录及其历史文档hash保持原样。

下表为**官方检查组通过数**，不是Python断言数。Task pass要求官方完整成功，不能把部分检查率当任务成功率。

| 任务 | NoSkill | S0 | 后续内容版本 | Final独评 |
|---|---:|---:|---|---:|
| dialogue-parser | 5/6 | 5/6 | S1：6/6 | S1：6/6 |
| 3d-scan-calc | 2/2 | 2/2 | S1：2/2 | S1：2/2 |
| adaptive-cruise-control | 10/12 | 12/12 | S1：10/12；S2–S8：11/12 | S8：11/12 |
| dapt-intrusion-detection | 7/14 | 11/14 | S1–S6：11、13、12、10、9、10 /14 | S1：11/14 |
| pddl-tpp-planning | 1/2 | 2/2 | S1：2/2 | S1：2/2 |

五题 **Task pass：NoSkill 1/5（20%）→ S0 3/5（60%）→ Final 3/5（60%）**。演化救回Dialogue、退化ACC，没有净Task pass提升。平均官方reward为0.3666→0.7666→0.6000；先按题计算再平均的GT检查组通过率为73.33%→92.38%→94.05%。三种指标分别报告，不互相替代。

本批共22个内容版本、27次独立测量；Final引用被选包已有的独评。ACC、DAPT各在42个有效episode后因上下文门禁停止，均完成作者末端GT分支。ACC为r10、正常GT0次、post-final1次；DAPT为r6、正常GT2次、post-final1次。DAPT的选择阶段reward都为0，作者同分保留较早S1；S2事后独评13/14不会回流选择。全部计数、suite和包hash以机器汇总为准。

仍存在语义限制：ACC的TTC输出精度问题未修复，公开稳态距离检查的前提有争议；DAPT任务说明与背景术语有冲突，后续修改改变了端口统计范围。池中缺少的资料不能通过重复搜索获得；获取控制流还可能让Analyzer在无新增证据时撤销缺口、改判充分。因此信息充分和公开测试通过都不保证官方成功；不从公开证据推断具体隐藏GT失败项。

## 2. 方法、角色与固定参数

每题独立执行：**只读输入发现与背景检索 → 冻结B* → 一次创建S0 → Generator持续执行、修改并提交 → 作者Verifier → fresh官方GT → 全版本独立评估**。冻结的是共享资料池检索能力；SkillsBench终端遵守官方环境的网络配置。

| 角色 | 能收到什么、做什么 |
|---|---|
| Analyzer | 原始instruction、工作目录、授权输入根；通过`list_input_directory`、`read_input_file`发现当前题原始输入，并搜索背景池。维护缺口、证据和相关性评分，选择B*；不自动获得COPY映射、文件清单或环境配置，不执行任务 |
| Generator | 创建时收到冻结B*、公开请求、实际获取的输入观察及工具说明；不继承Analyzer推理或未选文档。S0封存后，在持续官方环境执行、观察公开结果、修改父包并显式提交；仅接收受限反馈，不接收隐藏评分正文或reward |
| Verifier | 独立模型会话，在同一学习MAIN环境读取公开输入、产物和自己的测试；普通修改固定suite，GT失败后按作者顺序升级。会话独立不等于文件系统物理隔离，诊断阶段不能保证完全禁读Skill源码 |

直接调用CoEvoSkills commit `4380d4bff673dd6e1d58e5babeb2aaa0fe527119` 的完整演化控制器和Verifier，Harbor接口固定 `3f28e5ce2acbff36d8b5df431e35e050ac13bef6`。作者原文件及hash见 [VERIFIER_SOURCE.json](../../src/tau_skill_evolution/author/VERIFIER_SOURCE.json)，fresh执行器见 [SOURCE.json](../../src/tau_skill_evolution/author/SOURCE.json)。检索冻结、单次S0、模型传输及独立逐版本评估是实验适配，不能称完整论文复现。

| 参数 | 当前合同 |
|---|---|
| 数据 | 85题、benign；共享池只有背景资料122块。其它题输入、隐藏测试、solution和作者Skill不入池 |
| 检索 | BM25 Top10＋Qwen3-Embedding-4B Top10、RRF60；2048-token块、128重叠；confidence≥0.1，无篇数配额 |
| 获取预算 | 搜索30次、只读10次、澄清0次、Analyzer50轮；B*≤32,768 tokens，不截断原文 |
| 创建 | S0最多一次HTTP POST；只做安全结构封装，不执行、自测或反馈重生成，UNKNOWN不重发 |
| 作者预算 | r15计相应失败干预；正常K5；Generator120个有效episode。分别统计修订、提交、内容版本和请求，不能把r15当15次修改或把episode当POST |
| GT末端 | normal、cap-final、post-final分别记录；实际GT执行总数可能超过5 |
| 时间 | 学习7200秒墙钟上限，恢复不重置；任务执行时限按作者timeout multiplier 5计算，独评另开fresh环境 |
| 上下文 | Generator high，其余medium；保守272K窗口、β=0.7、输出预留32,768。保留完整自身历史和opaque continuation，不通过重开会话绕过限制 |
| 输出／费用 | 不设实验输出token或费用额度；实际模型和上下文仍有边界，累计计费tokens不是上下文占用 |
| 最终选择 | 按作者GT分数严格提高更新best，同分保留较早快照，按原终止分支复验或回滚；独评不挑版本 |

## 3. 怎样另开实验

从仓库根运行。先准备本机Python环境、Docker/Compose访问、固定上游、官方逐题环境锁、Dense服务/索引及native Codex **0.160.1**。本批配置中的Codex二进制和companion路径是本机路径；其它机器需在**新配置**中填写实际路径、GPU和endpoint，并重新preflight，不能修改已完成试验的配置或身份。环境准备脚本为 `scripts/prepare_skillsbench.py`，只准备固定数据和官方环境，不替代正式准入。

本机home Docker engine当前仍运行，本次未改动它或embedding服务。它的旧启动配置含两条已删除的v4交接目录挂载；将来重建engine时应去掉这两条挂载，保留原Docker数据和socket目录。项目目录清理不等于Docker镜像清理，也不能用此推断Docker磁盘余量。

以下命令复用本机最新五题的配置另开trial；不在已完成目录中运行。`key.env`仅本机提供，CLI按字面读取，不能上传。preflight和执行入口会验证凭据，执行会调用付费API。

```bash
set -e
SB_CODE=experiments/tau-knowledge/skill-evolution
SB_CFG="$SB_CODE/runs/skillsbench/input-discovery-five-gpt54-20261008-003/config.yaml"
SB_RUN="$SB_CODE/runs/skillsbench/five-gpt54-$(date +%Y%m%d-%H%M%S)"
test ! -e "$SB_RUN"
SB_TASKS=(--task dialogue-parser --task 3d-scan-calc --task adaptive-cruise-control --task dapt-intrusion-detection --task pddl-tpp-planning)
SB_ARGS=(--experiment skillsbench --runtime docker --config "$SB_CFG" --env-file key.env --arm benign)

.venv/bin/r2sp preflight "${SB_ARGS[@]}" "${SB_TASKS[@]}"
.venv/bin/r2sp evaluate "${SB_ARGS[@]}" "${SB_TASKS[@]}" --no-skill --run-dir "$SB_RUN"
.venv/bin/r2sp run "${SB_ARGS[@]}" "${SB_TASKS[@]}" --run-dir "$SB_RUN"
.venv/bin/r2sp report --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_RUN"
```

`run`依次执行create、evolve、evaluate；**不自动运行NoSkill**。上面是顺序五题，时间和成绩不能照抄本批并发launcher。单题调试把 `SB_TASKS` 缩为一个任务；需观察阶段时，使用相同参数依次执行 `create`、`evolve`、`evaluate`，代替`run`，不要另开S0或回到检索。

完整85题v7矩阵及其它型号兼容性目前为 **`NOT_MEASURED`**。当前配置包含85题，但现有准入只实测上述五题；全部85题须逐题准备并通过本机preflight，不能把五题READY解释成全量READY。`pg-essay-to-audiobook`仍缺官方任务专用OpenAI凭据，Bedrock key不能代替。任务环境或凭据缺失时保留未测状态和85题分母，不填失败0。

## 4. 过程封存、恢复与交回内容

运行产物位于 `RUN/cells/TASK_ID/benign/`：`base`是冻结资料JSON文件，`initial/`是S0，`versions/<hash>/`保存后续包；Journal记录稳定操作ID、请求状态和封存结果。`learning/`绑定持续环境，`private/author-controller/`保存作者提交、测试、日志和私有评分引用。汇总由`report`写入 `report.json`、`REPORT.md`；私有原始评分、模型记录和凭据不得作为公开资料或模型输入。

恢复必须保持源码、提示、配置、数据、环境及trial身份一致。已完成且正常关闭的结果复用；`NOT_SENT`可首次派发，已收到响应仅确定性解析，`UNKNOWN`不重发。**未完成的作者学习循环不能通过重新run恢复**：原作者会重置内部状态，必须停止并另开trial；容器丢失也不能用文件快照冒充恢复服务或安装状态。关闭失败会持久阻止同cell后续模型派发，已有报告仍可读。

交回完整run和配置身份，以及逐题NoSkill/S0/各Si/Final的Task pass、官方reward、实际GT检查率；同suite的surrogate通过率、历史best、末端真实GT和Final独评分别报告。另报r、正常/末端GT、有效episode、修订、提交、内容版本及用量。S编号按内容hash去重，A→B→A不产生第三个内容版本，但保留实际父谱系；invalid/unchanged不是新版本，早停后不补造版本。费用无账单时为`NOT_MEASURED`。
