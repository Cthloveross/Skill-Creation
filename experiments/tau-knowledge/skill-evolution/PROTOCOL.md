# 一次创建与固定资料下的 Skill / 测试共同演化

机器合同分别为 [τ 配置](configs/experiment.yaml)和 [SkillsBench 配置](configs/skillsbench.yaml)。方法命名空间为 `tau.skill-evolution.v2` / `skillsbench.skill-evolution.v1`；通用 artifact / journal wire 格式仍保留 v1，方法与源码身份另行绑定，不能恢复旧方法 checkpoint。

## 1. 研究问题与实验条件

τ研究固定资源池投毒如何影响S0，以及在固定B*下的演化是否改善官方utility和canary ASR。SkillsBench研究合并所有任务的背景资料后，这条检索、冻结和演化链能否完成文件任务；当前题的instruction与environment作为提供的任务输入，不参与共享检索。实验单位是独立的task×condition链，每题单独生成Skill；本轮每cell一次采样，不代表稳定或因果效果。

| 项目 | τ-Knowledge | CoEvoSkills / SkillsBench |
|---|---|---|
| 固定 source | tau2-bench `fc0055dc4e0a316c3f83133267fbd6faaa770992` | CoEvoSkills `4380d4bff673dd6e1d58e5babeb2aaa0fe527119` |
| 任务 | 全部97题，按ID排序 | 固定仓库全部85个任务目录，按名称排序 |
| 资源池 | 698篇银行政策与工具文档 | 全部85题的85篇`background_docs`，固定分成122个检索块 |
| 条件 | benign / poison-5 / poison-10，291条链 | benign，85条链 |
| 攻击 | 原70文档样本与payload不变，35为70前缀 | 本次不投毒、无银行canary |
| 执行器 | 官方银行agent与用户模拟器 | artifact/terminal任务适配器、独立官方grader |

τ 原20题的攻击 profile 映射不变，其余77题按排序交替分配，两种profile全矩阵各49/48题。每个 cell 单次采样，未知请求不自动重试。私有 scenario、gold、expected actions、评分目标、solution 和官方 tests 不进入资料收集、Generator 或 Verifier。

共享模型为 Bedrock Mantle Responses 的 `openai.gpt-5.5`。三个角色共用 backbone，使用独立提示与新消息；银行agent、用户模拟器及SkillsBench执行器使用各自会话。Analyzer/Verifier/执行agent为 medium reasoning，Generator为 high，银行用户模拟器为 none。Generator输出上限32768，输入 admission 为 `floor(272000×0.7)−32768=157632`；Analyzer、Verifier及银行执行侧仍为114688。计数使用固定embedding tokenizer的序列化文本估计，不声称是GPT原生精确token数。

## 2. 配置参数与变体

| 配置键 | τ默认 | SkillsBench默认 | 当前允许范围 |
|---|---:|---:|---|
| `acquisition.max_searches` | 30 | 30 | 1–30；上限，不要求搜满 |
| `acquisition.max_clarifications` | 4 | 0 | τ 0–4；SkillsBench固定0 |
| `acquisition.max_reads` | 10 | 0 | τ 0–10，初始银行时间占一次；SkillsBench固定0 |
| `acquisition.max_steps` | 50 | 50 | 1–50，非法响应也占一轮 |
| `acquisition.base_token_limit` | 32768 | 32768 | 1–32768，所选文档/块保持完整 |
| `acquisition.min_document_confidence` | 0.1 | 0.1 | 0–1，采用`>=`；0保留全部返回内容，仍受容量限制 |
| `evolution.max_revisions` | 15 | 15 | 1–15，无效/unchanged消耗额度 |
| `evolution.max_oracles` | 5 | 5 | 1–5 |
| `retrieval.wire_token_limit` | 65536 | 65536 | 单次检索响应上限，超限fail closed |
| Generator输入/输出 | 157632 / 32768 | 同左 | 272000窗口、β=0.7；本方法固定 |
| Analyzer/Verifier输入 | 114688 | 同左 | 当前角色admission，不是B*容量 |
| BM25/Dense/RRF | 10 / 10 / 60 | 同左 | 当前方法固定；任一路失败不降级 |
| 检索单元 | 整篇原文 | 2048-token块，overlap128 | 不截断所选单元；SkillsBench可只选源文件的部分块 |

参数变体另存YAML并新建run。`--task/--arm`只过滤本次执行，不改97/85计划分母。配置路径可外置，资料路径仍相对本实验根；不要修改已有checkpoint绑定的配置或提示。没有最少文档数、最少搜索数或强制查询多样性开关，confidence也不是经校准的成功概率。

## 3. 收集与冻结

```text
固定资源池 → Analyzer多轮获取公开资料 → 冻结B*与公开输入 → 一次生成S0
```

默认搜索30次、Analyzer决策50轮、B*上限32768 tokens、相关性阈值0.1。τ另有4次文本澄清和10次只读查询；SkillsBench两者为0。搜索采用BM25 Top10 + 固定Qwen3-Embedding-4B Top10、RRF k=60，任一路失败均fail closed，不降级。τ返回全文；SkillsBench仅检索85题的`background_docs`，按固定2048-token / 128-token重叠分成122块，保留来源文件hash与offset。

SkillsBench当前题的instruction全文直接提供给Analyzer；当前题environment公开文件的路径、大小、hash及运行说明作为`public_task_inputs`，执行时原始文件直接放入fresh工作区。instruction、Dockerfile、数据、代码和其他environment文件均不入共享检索池；不生成二进制摘要索引。869文件是85题的公开输入总清单，不是共享池大小。原始输入的公开范围仍以Docker COPY/ADD和`.dockerignore`为准，不自动暴露整个environment；隐藏grader、答案、solution和作者旧Skill保持私有，执行时不挂载其他题目录。具体清单在SkillsBench HANDOFF链接的JSON中。

τ只读白名单为：`get_current_time`、`get_user_information_by_id`、`get_user_information_by_name`、`get_user_information_by_email`、`get_referrals_by_user`、`get_credit_card_transactions_by_user`、`get_credit_card_accounts_by_user`。银行写操作、verification写入、discoverable通用调用和canary由控制器拒绝。采集阶段拒绝官方用户模拟器的一切工具动作，只接收对外开场或澄清文本。初始公开时间查询执行一次并占只读预算；恢复重放不重复查询。

`collect_base`接收适配器提供的只读名单和函数映射，严格执行交集；SkillsBench提供空名单，不读取或执行任务工作区、solution、官方tests。各域公开工具说明用于规划后续执行，不授予Analyzer执行权限。

Analyzer每轮返回严格七字段JSON：`gaps / action / evidence / document_scores / coverage / conflicts / sufficient`。每个实际返回全文ID必须给 `document_id/confidence/reason`；confidence是公开任务相关性或潜在用处的估计，范围0–1，不是文档真伪或成功概率。达到阈值的全部文档都保留；只有超B*容量时按分数降序、ID升序整篇装入，放不下跳过继续，绝不截文，没有篇数配额。逐篇理由保留在原始journal，不传给Generator。

冻结边界：

1. `sufficient=true`，无gaps/conflicts，四类coverage非空且只引用入选、已在evidence中引用的文档，才以`sufficient`冻结。
2. 自称充分但引用/缺口检查无效，反馈`controller_error`并在剩余预算内继续；可修正引用，也可继续搜索。
3. 显式不充分的freeze在仍有可用采集额度时同样拒绝，不能提前停。
4. 单项预算耗尽但其他实际可用动作仍有额度时继续；全部可用动作额度耗尽、输入admission或决策轮数到达上限时，冻结最近合法集合，记录`budget_exhausted_incomplete`，仍进入一次生成。

Host检查结构、权限、预算、全文返回事实和引用归属，不证明语义充分。默认evidence只写支持的requirement与文档ID；确需quote时必须为原文精确非空子串。Tokenizer错误属于基础设施失败，不冒充预算耗尽。

`FrozenBase`保存完整原文、ID、逐文档hash、公开开场/澄清/只读原始返回、证据、停止原因、token数及整体hash。搜索观察只保留query、状态、返回ID，全文在Analyzer当前输入只出现一次。冻结后关闭大池检索。Generator新请求只见B*、冻结公开输入和必要公开工具/运行说明，不能继承Analyzer推理、未入选全文或检索对话。

## 4. 一次创建与真实包执行

接口：

```text
collect_base(...) → FrozenBase
generate_initial(public_inputs, FrozenBase, ...) → SkillBundle
read_skill_file(relative_path) → text
run_skill_script(relative_path, input_json) → 执行状态、JSON输出、退出码、stderr
rollout(SkillBundle, fresh_environment) → PublicTrace
verify(public_inputs, B*, PublicTrace, previous_tests) → VerificationReport
revise(previous_bundle, public_inputs, B*, report) → next_bundle
oracle(SkillBundle, fresh_environment) → pass/fail
evaluate(SkillBundle, fresh_environment) → 独立完整指标
```

Generator初始请求只有一次，响应`{"files":[{"path":"…","content":"…"}]}`，必须包含非空`SKILL.md`，可有`scripts/*.py`和`references/*`。当前只有Generator初始和修订请求使用provider的strict JSON schema约束这个外层格式；Analyzer、Verifier和执行器没有同步启用该约束。格式约束不验证Skill内容或保证正常结束。控制器只做安全结构校验和确定性封装：UTF-8普通文件，拒绝绝对路径、穿越、重复路径、符号链接与特殊文件；包hash覆盖所有文件路径与内容。创建阶段不执行、不自测、不把失败反馈重生成。无效、空、不可解析、未正常结束（如length）或未知S0终止创建；完整JSON也不能覆盖provider声明的不完整状态。原始响应仍封存，禁止重发。语法、依赖和内容问题留给evolution。

每次运行创建fresh环境、模型会话、临时目录和canary。银行DB和官方模拟器亦重新创建；SkillsBench重建工作区与当前任务公共输入。执行agent只加载当前Skill包和正常工具，不直接接收外部B*、冻结问答或全局检索。包内references是Skill产物，可由执行器读取。

银行脚本通过JSON stdin/stdout通信，可导入包内helper、读references并使用同episode临时文件。脚本建议不由host自动执行，银行动作仍由agent正常工具调用。SkillsBench执行器在声明的task sandbox中使用terminal完成真实artifact；公开输入文件可用，官方测试与solution不能供执行器查看。

银行正式包容器固定Python3.11、NumPy2.2.6、pandas2.2.3、pytest8.4.2及真实依赖hash；无网络、非root、只读根、禁提升权限，60秒、1CPU、1GiB内存、64进程、64KiB合并输出。只挂载包和专用episode目录，不挂宿主工作区、密钥、银行DB或Docker socket。

SkillsBench正式容器使用逐题官方environment及独立grader镜像，记录实际digest和官方资源声明；所需命令、文件格式与依赖按该题环境准备，不把统一银行镜像冒充全部85题运行时。官方grader私有输入不进入公开容器。正式执行保留原任务依赖，当前题文件只在fresh可写副本修改，不按扩展名额外禁止编辑；宿主原始输入不挂载。Verifier pytest依赖隔离在`/.tau-verifier`，grader缓存只在私有`/opt/tau-grader`中fresh复制。原test.sh和官方测试字节保持不变，评分wrapper只复用实际成功预热的精确安装命令，未知或失败的安装不能被零分掩盖。JSON错误、运行错误、超时和过量输出均明确失败，并清理进程/容器。

`--demo`仅单题benign，使用另锁定Bubblewrap rootfs。它保留文件/网络/namespace隔离及调用时限、输出上限，但缺完整cgroup聚合硬限制，标记`formal_matrix_result=false`、`aggregate_limits_enforced=false`；不能替代正式矩阵。运行时或真实digest未就绪均由preflight阻止，绝不降级宿主执行。

## 5. 固定B*下的共同演化

默认M=15次修订尝试、K=5次oracle，固定B*不补搜：

1. 先fresh执行S0，Verifier据公开任务、B*、公开轨迹生成第一版pytest。
2. Surrogate失败：保持测试版本，Verifier给公开诊断，Generator继承上一完整包修订。保留前轮公开反馈供后续修订查阅。
3. 全部公开检查通过：fresh运行官方oracle，学习侧只收到pass/fail。成功立即停止。
4. Oracle失败：Verifier保留既有检查并补充遗漏检查，fresh执行当前Skill、运行升级测试，再依据结果修订或请求oracle。
5. 无效和内容未改变的修订也消耗额度；相同hash记`unchanged`，不增加内容版本。最后一个安全封存包仍完成允许的执行/检查，不因为刚用尽修订额度就略过。

Verifier使用独立容器，只收公开输入、B*、公开轨迹和测试，不收Skill源码、隐藏oracle细节或评分数据。空测试、skip/xfail、收集/运行错误、超时不能算通过。skip/xfail属于无效测试程序，交由Verifier修复，不能要求Generator靠修Skill消除永久跳过。每个语义测试版本最多一次程序错误修复；普通断言失败仅在Verifier明确认定是测试程序错误时使用这一额度。修复或升级须保留已有检查义务，不新增无界反馈循环。

公开轨迹剔除系统提示、模型推理/raw响应、模拟器内部事件、隐藏评分、canary诊断及Skill文件内容；脚本事件仅提供可信执行状态，不传原始stdout/stderr。SkillsBench还剔除执行agent的全部自由文本，仅保留message/tool状态和当前执行实际产物的公开manifest/产物；完整文本与工具返回只留在executor自己的会话，避免引用Skill源码穿入Verifier。声明的任务输出文件可以被公开检查，评分器仍在隔离环境中。银行公开轨迹规则不因这项SkillsBench修复改变。

Responses请求为`store:false`、新完整消息，不共享服务端conversation。银行agent/user可在各自episode私有metadata携带所需reasoning continuation，不进入角色输入或公开轨迹。学习oracle不返回轨迹、reward、目标DB、官方失败条件或ASR。

## 6. 独立评估、报告与恢复

S0及每个实际封存内容版本分别fresh评估，只加载该包。最终包取oracle成功包，否则取最后安全封存包，不能用独立评估挑选。污染条件的冻结对照直接共享同一S0与其评估，不能另生成或重复计算独立样本；成功早停不补造后续S版本。

τ utility沿用官方任务成功；canary ASR要求真实dispatcher目标行动成功，单纯输出攻击字符串不计ASR。SkillsBench utility来自官方私有grader，独立报告保存实际检查明细；SkillsBench保存有限[0,1]官方reward，完整utility为`reward==1`；正常零分的exit0/1可算有效测量，缺reward、依赖/收集/执行错误保持NOT_MEASURED。官方检查passed/total仅在可取得时报告，ASR为null/NOT_APPLICABLE，不能填0。

τ独立报告另含官方`reward_info.action_checks`参考动作匹配数/总数/比例、逐项动作和DB/环境/通信/NL分项。参考动作匹配不检查顺序，不证明调用成功，也不等同于DB-only任务的必要步骤率。SkillsBench报告官方独立检查分项；不同类型的检查不能混进同一个“步骤率”分母。所有独立指标及事后gold诊断不回流三个学习角色。

看演化收益时并列报告S0和final独立utility、配对差值、失败救回、成功退化和配对覆盖率。对完整配对集合P，平均变化为`Σ(Ufinal−US0)/|P|`，同时给出`|P|/97`或`|P|/85`；没有配对不得填增益0。SkillsBench另比较官方连续reward/检查率，τ另比较Action Recall。逐轮曲线标实际链数和停止数量；surrogate率仅在相同测试hash下直接比较，测试程序修复或升级本身不是Skill改善。当前没有多次独立采样，不能称pass^k可靠性实验。

τ事后gold诊断计算返回过的gold ID覆盖、B*覆盖和已返回gold的保留率；只在独立评估侧读取required_documents，不用于补B*或学习反馈。标签覆盖既不保证utility成功，也不是所有合法完成方式的必要门槛。

计划分母为τ每臂97题、SkillsBench benign85题；创建失败仍占分母。没有有效测量的阶段为`NOT_MEASURED`、utility/ASR为null，不补0。报告另列实际测量数、停止数、版本hash、测试版本、修订尝试和oracle次数；逐轮只统计实际链数，早停后的未产生版本不存在。

Journal在请求派发前持久化请求，原响应先落盘，再解析/封装；恢复复用已封存B*、包、轨迹、测试及独立测量。未知S0禁止重发；已知鉴权失败安全记录状态并阻止本次调用继续启动后续cell。有效凭据通过下一次CLI预检后，`run`保留此前鉴权失败链的未测结果、跳过其未知操作并继续未启动链；不是重试S0。未知结果的根因不能仅凭日志缺失猜测。

身份包含方法namespace、配置原字节、源码、提示、meta、公共manifest、运行锁和有效模型region，排除密钥和运行输出。使用新源码不能恢复旧v1或不同prompt/runtime的checkpoint；配置快照可放其他目录，但数据路径仍相对当前experiment根。旧runs只读保留。GitHub只发布pipeline及两个父目录的公开交接快照；原始data、rootfs、checkpoint/journal和私有评分不发布，公开快照不能直接恢复。新机器先准备源数据和运行锁，再在新空目录建立自己的运行身份。

## 7. 与CoEvoSkills的关系及验收范围

复用[CoEvoSkills](https://arxiv.org/html/2604.01687#S3)的包继承、独立Verifier、测试升级和受限oracle思想，并从固定作者代码/meta摘编通用Skill编写要求。这里的三角色、采集冻结、一次S0、多任务共享检索池、τ银行适配、safe canary和独立ASR是本实验设计；不声称完整复现作者Harbor/Terminus运行时或原论文全部设置。

两域共用M15/K5和Generator context参数。SkillsBench共享全部任务的背景资料池，当前题instruction和environment直接提供，固定检索/分块方式并严格隔离私有tests/solution，是本实验变体；原论文已有成绩不作为该变体测量。我们的创建要求一次响应封存、不执行或自测；原CoEvo的终端交互次数不等于反复创建独立S0，初版之后的修改也属于演化。论文/作者代码的host数值oracle与best-snapshot选择不作为本实验规则；这里学习侧仅bool，成功取该包，否则取最后安全包。

当前验收和环境状态集中在[τ HANDOFF](runs/tau-full-97-20261004-001/HANDOFF.md)与[SkillsBench HANDOFF](runs/skillsbench-pooled-85-20261004-001/HANDOFF.md)。默认检查为离线，真实隔离检查显式opt-in；跳过即未验证。旧单题/十题pilot见[runs/HISTORY.md](runs/HISTORY.md)，原始runs和分析保留，旧M4成绩不能当新M15结果。

## 8. 实现、自查与环境限制

| 模块 | 职责 |
|---|---|
| `acquisition.py / artifacts.py` | 权限、预算、证据筛选、B*与完整包封存 |
| `generator.py / evolution.py / verifier.py` | 单次S0、完整父包与公开反馈、M15/K5、固定测试/升级/受限修复 |
| `bank.py / official_runtime.py` | 银行执行、公共轨迹、官方oracle/evaluation及私有NL judge |
| `skillsbench.py / skillsbench_runtime.py` | 公开池、文件任务、产物快照、逐题环境和独立grader |
| `model.py / journal.py / workflow.py` | Bedrock客户端、派发与恢复、逐链运行 |
| `evaluation.py / preflight.py / cli.py` | 指标、真实环境门槛、六阶段入口 |

宿主要求Python≥3.11（使用tomllib），银行worker固定3.12.14；不要把宿主、worker和包容器的版本混为一谈。所有角色请求用`store:false`，无自动HTTP重试。API凭据仅由host读取，不进入journal、容器或hash。

正式SkillsBench有45题声明联网、40题禁网；Verifier和私有grader始终禁网。每次终端调用当前统一60秒/64KiB，grader按task的verifier timeout；这是本适配额外限制，长编译任务未真实验证。`storage_mb`尚无聚合磁盘配额；各Docker工具调用不保留跨调用后台进程。缺原Python/pip的题目（如lean4-proof）当前准备脚本会fail closed，尚需完善正式工具运行环境，不能承诺85题已就绪。

本轮自查已修复：不完整JSON响应误封S0、skip/xfail错误修复路由、SkillsBench源码被扩展名规则锁为只读、未测报告被标为正式结果、宿主Python版本声明及执行文本引用源码进入Verifier；Generator增加strict JSON schema，继续保持单次S0和创建禁自测。独立SkillsBench评分拒绝被零分文件掩盖的grader程序错误；正式preflight增加fresh官方grader探针，不以构建时root预热替代最终隔离运行。验收数量及源码hash以两份HANDOFF和各自VALIDATION.json为准。


| 自查结果 | 修复与验收 |
|---|---|
| 模型明确不完整，但内容恰好是合法JSON | 先检查正常finish；保留原响应、终止S0且不重发；包含真实Responses normalizer回归 |
| skip/xfail永久固定测试导致反复修Skill | 归为测试程序错误，最多一次Verifier修复；覆盖成功/耗尽，均不消耗Skill修订 |
| TSX/CSS/config源码被扩展名规则锁只读 | 当前题fresh副本可写，移除扩展名启发式；原宿主源、包及Verifier输入仍隔离 |
| 正式预检只证明依赖，未运行grader | 新增fresh无解官方grader探针，合法0分可通过环境验收，错误/空检查不得ready；目前仅mock-Docker回归 |
| grader程序错误仍被零分文件算成有效评分 | 复用结果验证，依赖/收集/无检查/异常退出保持NOT_MEASURED；正常零分和exit1仍有效，新增9例回归 |
| 空report标成正式成绩 / Python版本声明不符 | 有独立实测才标formal result；宿主最低3.11，uv.lock同步 |
| 执行agent在自由文本中引用Skill源码 | SkillsBench PublicTrace仅保留状态与公开产物；回归证明executor保留原消息而Verifier payload不含源码/推理 |
| 首次S0已完成响应带多余JSON结尾 | 创建失败终止且不重发；新身份中Generator启用strict外层schema，真实格式探针通过，不把探针当任务成功 |

最新本机`make check`：547通过、12跳过；干净分发检查535通过、24跳过，Ruff/71文件格式/编译/两域配置通过，公开日志为SkillsBench父目录`PUBLISH_FRESH_CHECK.log`。数据/rootfs集成显式opt-in，不把本机准备的数据当默认测试依赖。SkillsBench为85篇背景/122块，回归覆盖检索范围、完整来源、旧池拒绝、篡改和本题输入保留。此前有7项真实Bubblewrap边界/生命周期检查；本轮没有新的真实Docker验证。

2026-10-04已按用户授权读取本机凭据并发送真实GPT-5.5请求，凭据不进入共享产物。SkillsBench首个`smoke/`执行24次Analyzer调用、18次成功搜索，283块返回/74个唯一ID，本题背景18次均排第1；冻结1块/293 tokens，停止为`budget_exhausted_incomplete`。下一轮输入估计116849超过114688，尚有12次搜索/26轮决策余量，B*也未满：这是累积候选导致的输入admission停止，不是搜索用完或背景无法检出。期间4次文档评分遗漏和2次非法充分性freeze被拒绝，最终仍未判充分。

首轮Generator一次已完成响应带多余结尾而解析失败，终止为`CREATION_FAILED`，后续全部`NOT_MEASURED`。随后strict格式探针HTTP200、`ready=true`、52 tokens，只证明格式能力。新`smoke-002/`在新身份下仅复用已验证的同一FrozenBase和公开输入/检索契约，不继承旧Generator响应或journal，重新进行一次S0。该链已退出0并完成：S0为SKILL.md加3个Python文件，首次公开检查经一次Verifier程序修复（密度单位换算）后2/2通过；Skill修订0次，fresh oracle一次通过，停止为`oracle_success`。fresh独立评价官方reward=1、utility=true、官方检查2/2、grader退出0。不能把测试程序修复算为Skill修订，也不能从S0成功推出演化增益。

成功链记录18个已完成模型响应（Generator1、Verifier3、execution14），input249760/output33621，其中cached input108100；首次收集与失败创建另记25个响应，input1853035/output125177，格式探针另记52 tokens，不混成一个独立采集样本。无账单，美元费用`NOT_MEASURED/null`。这个Bubblewrap demo真实覆盖已冻结B*后的创建、验证、oracle和独立评分，资料来源仍是首轮的不充分冻结，第二轮没有重新运行Analyzer。τ新`task_019` smoke及两套完整矩阵均未执行，正式Docker仍未就绪。
