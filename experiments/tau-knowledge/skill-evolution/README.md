# Retrieval 与 Skill Evolution

这里只维护一套实现和两个任务适配器。当前流程：**多轮公开资料收集 → 冻结B* → 一次生成S0 → Skill与公开测试交替演化 → 每个实际内容版本独立评估**。创建不执行、自测或重新生成；默认M15/K5。所有生成及执行模型为Bedrock GPT-5.5、us-east-1，Generator high。

| 实验 | 固定规模 | 配置 | 操作入口 |
|---|---|---|---|
| τ-Knowledge | 97题×benign/5%/10%，291条链 | [experiment.yaml](configs/experiment.yaml) | [τ HANDOFF](runs/tau-full-97-20261004-001/HANDOFF.md) |
| CoEvo/SkillsBench | 85题、benign，85条链 | [skillsbench.yaml](configs/skillsbench.yaml) | [SkillsBench HANDOFF](runs/skillsbench-pooled-85-20261004-001/HANDOFF.md) |

SkillsBench只把全部85题的背景资料合并检索，85篇文档固定分成122块。当前题的任务说明和environment输入直接提供，不进入共享池；执行器只获得当前题原始文件。

阅读顺序只有三个入口：本页定位目录；[PROTOCOL](PROTOCOL.md)定义方法、参数、权限和指标；选择对应HANDOFF准备环境、运行和恢复。提示来源在[来源记录](meta/coevo-authoring/SOURCE.md)。历史方法与结果集中在[runs/HISTORY.md](runs/HISTORY.md)，原run/analysis不改成绩。

## 目录

```text
src/tau_skill_evolution/   共享pipeline、银行和SkillsBench适配器
configs/                  两域配置、固定数据manifest
prompts/                  模型实际使用的独立角色提示
meta/                     提示来源；属于运行身份
runtime/                  依赖hash和真实镜像/rootfs锁
scripts/                  CLI、embedding服务、环境准备入口
tests/                    离线回归和opt-in真实隔离检查
data/                     固定upstream、公开池、embedding与runtime
runs/                     两份交接、smoke/matrix checkpoint、历史记录
```

角色提示的MD是运行输入，不是重复说明；data中的上游文档、依赖资料以及封存run的MD不清理。其余当前说明已合并到PROTOCOL和两份HANDOFF。

## 检查与命令

从仓库根运行，需要宿主Python≥3.11：

```bash
make setup
make check
.venv/bin/r2sp preflight --experiment tau --env-file key.env
.venv/bin/r2sp preflight --experiment skillsbench --env-file key.env
```

统一入口：`preflight / create / evolve / evaluate / report / run`；默认`--experiment tau`。preflight只读检查模型目录，不生成；create/evolve/evaluate/run会调用付费模型。`run`逐链完成各阶段，未知请求不自动重发。report只读封存记录，不执行任务或调用API。

新完整矩阵和两条smoke尚未启动，最新预检记录在两份HANDOFF旁的JSON里。Bubblewrap仅单题benign演示，缺cgroup聚合限制；正式矩阵必须通过Docker、真实digest、依赖和逐题grader检查，不降级宿主执行。上次鉴权为HTTP401，不代表下一次状态，运行前重新preflight。

凭据只在运行者本机提供，使用`AWS_BEARER_TOKEN_BEDROCK`或`--env-file`，不复制到交接目录。新run身份绑定配置、源码、提示、数据manifest和运行锁；修改这些文件后不能接着用旧checkpoint。

## Parallel Terra/Midway runtime (2026-10-05)

- **模型允许列表**:`constants.SUPPORTED_MODELS = ("openai.gpt-5.5", "openai.gpt-5.6-terra")`。`provider.model`必须取其一;默认仍为`openai.gpt-5.5`(`spec.BEDROCK_MODEL`别名保留)。worker私有NL judge、preflight的`/v1/models`目录检查都跟随配置里的模型。换模型即换运行身份,不能接旧checkpoint。
- **Midway/ada凭据**:除静态`AWS_BEARER_TOKEN_BEDROCK`外,新增`AWS_BEARER_TOKEN_BEDROCK_FILE=<path>.json`(优先)。文件为`{"token","expires_at",...}`,每次请求前重新读取;距过期不足60s报`credential_expired`,缺失/损坏报`credential_unavailable`。实现见`src/tau_skill_evolution/credentials.py`;token不进journal、日志或身份hash。路径按绝对路径解析(worker子进程cwd不同)。token在构造任何请求之前解析:`CredentialError`不会被journal记成unknown,而是撤回未发送的记录并中止本次调用(不封`CREATION_FAILED`、不消耗revision attempt),等token刷新后重跑即可;preflight的`credential`检查对缺失/损坏/过期文件fail closed。
- **token守护进程**:`python3 scripts/bedrock_token_daemon.py --accounts ID,ID --out-dir DIR [--interval-seconds 1200] [--once]`(系统python3,需boto3+aws_bedrock_token_generator)。每个账号在子进程内`ada credentials print --provider conduit --role IibsAdminAccess-DO-NOT-DELETE`后调用`provide_token`,原子写`DIR/<account>.json`(0600)及无token的`DIR/status.json`。ada凭据只有1小时,刷新间隔必须远小于60分钟;ada会复用缓存凭据,所以守护进程按`min(interval, 最早expires_at−now−120s)`缩短周期,拒绝发布已在过期边界内的token,并用`--parallel`(默认8)线程池并发铸造,避免单个卡住的ada拖长整个周期。
- **并行启动器**:`.venv/bin/python scripts/launch_matrix.py --experiment tau --config CFG --run-dir DIR --token-dir TOKENS [--max-concurrent 96] [--task T] [--arm A] [--dry-run]`。先跑一次`r2sp report`建立共享身份,再按cell轮转分配账号,每cell一个`r2sp run --task T --arm A --no-interim-report`子进程,日志在`DIR/logs/<task>__<arm>.log`,进度在`DIR/launcher-status.json`,结束后再跑一次`r2sp report`。
- **`--no-interim-report`与逐cell锁**:单个`--task`+`--arm`的调用独占`DIR/locks/<task>__<arm>.lock`并共享持有`DIR/.lock`(LOCK_SH);整矩阵`run`与`report`独占`DIR/.lock`,因此逐cell进程可并行,但与整矩阵/report进程互斥;`--no-interim-report`时`run`不写`report.json`,由启动器最后统一生成。`Workflow`允许run目录预先存在`locks/`、`logs/`、`launcher-*`,以及并发进程尚在创建`identity.json`时只含临时文件的`journal/`;`identity.json`用`os.link`独占创建,先写者胜出。同一benign语料的dense索引构建由`data/dense/<key>.lock`串行化,并容忍并发发布。
- **worker Python**:`constants.WORKER_PYTHON_VERSION = (3, 12, 12)`(uv索引无3.12.14,现装3.12.12),preflight与`official_runtime`均按此精确比较。

## SkillsBench Docker 运行时锁修补(2026-10-05)

- **verifier 解释器**:`prepare_skillsbench.py --docker`构建环境镜像后探测`python3 -c "import sys, pip; assert sys.version_info[:2] == (3, 11)"`。通过则`verifier_python_mode: native`(`images.runtime.verifier_python = "python3"`);否则`standalone`:runtime与grader镜像从`ghcr.io/astral-sh/uv:0.9.26`复制`tau-uv`,`tau-uv python install 3.11 --no-bin --no-registry --install-dir /opt/tau-python`(uv按sha256校验python-build-standalone),再以`tau-uv pip install --require-hashes --target /.tau-verifier`安装验证器依赖;`images.runtime.verifier_python = "/opt/tau-python/python3"`,不进任务PATH。`_docker_command`按锁里的解释器运行verifier;缺少这两个键的旧锁按native处理,无需重建。注意:只要镜像自带的不是3.11(例如3.12),重建后就会切到standalone。
- **grader warm-up**:驱动脚本记录`grader_warmup = {reward, exit_code, missing_deliverable_modules}`。缺失模块仅当镜像不能导入、`/tests/**/*.py`自己`import`它且测试源码调用`sys.path.insert/append`(即从agent工作区导入)时才算agent交付物;此类`ModuleNotFoundError`/collection error在无解答时是预期负结果,warm-up与`grade()`均接受并给出reward 0,其余缺失依赖与`command not found`仍致命。每条`RuntimeError`附带grader输出尾部(约1200字符,已脱控制字符)。
- **astral 安装器env文件**:grader镜像已把`$HOME/.local/bin`放进PATH,安装器因此跳过写`$HOME/.local/bin/env`,而官方test.sh会`source`它。prepare分支在安装器成功后补写等价env文件;replay分支不变(`grader_bootstrap_sha256`不变)。
- **grader输出上限**:`grader=True`的调用使用`_GRADER_OUTPUT_LIMIT = 16 MiB`(终端/verifier仍为64 KiB);验证器只看最后1 MiB。grader输出不会进入模型上下文。
- **preflight**:Docker模式下环境镜像无`python3`不再导致`dependencies`失败(agent在环境镜像里只用bash,verifier在runtime镜像);结果新增`task_python`(版本或`null`)。
- 未修复:`simpo-code-reproduction`的官方测试从任务镜像的`/opt/py310`导入numpy,而该venv无numpy且agent安装无法跨`/root`之外持久化,官方grader在自身镜像里无法运行;`earthquake-phase-association`/`seismic-phase-picking`环境构建需从`hifis-storage.desy.de`下载,本网络超时。

### 模型请求的有界重试（2026-10-05 补充）

在 376 条链同时启动时，Bedrock Mantle 对 GPT-5.6 Terra 请求间歇返回 HTTP 500，以及 HTTP 200 但 `status: failed` 的响应体；原实现把它们一律封存为“结果未知”，首次启动约 20% 的创建和一半的 rollout 因此永久失败。现在 `OpenAICompatibleClient` 只对**证明模型没有产出样本**的失败重试：HTTP 429/500/502/503/504、建连/连接中断类传输错误、以及 `status` 为 `failed/cancelled/queued/in_progress` 或带 `error` 的响应体；最多 6 次、指数退避（2s 起、60s 上限，尊重 `Retry-After`）。**超时仍不重试**（服务端可能已完成生成），其余非法响应形状也不重试，仅把状态/条目类型（不含文本）写到 stderr 便于诊断。被拒绝的请求不是第二次采样，各阶段的一次性语义不变。本地 tokenizer/embedding 查询同样有短重试。journal 中失败的操作另写 `failure.json`（异常类名与短错误码，不含消息文本）。银行 worker 的 stderr 写入 `<run>/logs/workers/`，仅作运行本地诊断。

### 空输出的处理（2026-10-05 补充）

GPT-5.6 Terra 在无话可说时（实测发生在 `transfer_to_human_agents` 之后）会返回 `status: completed` 但 `output` 为空的响应，且对同一请求是确定性的。客户端把它当作内容为空的 assistant 消息；银行官方运行时不接受既无内容也无工具调用的消息，而官方语义中“无话可说”就是停止信号，所以 `official_runtime._complete` 把空输出映射为 `###STOP###`（agent 或 user 模拟器皆然），并在私有 `raw_data.empty_output_as_stop` 记录。这是适配决定，不是原协议规定。

### 超时重试与补跑（2026-10-05 06:50 UTC 决定）

第 8 次正式启动期间（04:10–05:10 UTC，约 270 条链同时运行），Bedrock Mantle 让约 1.3% 的 Terra 请求挂起到 900 秒客户端超时；按原协议超时不重发，198 条 τ 链和 40 条 SkillsBench 链因此至少有一个阶段被封为“结果未知”。运行者决定：`OpenAICompatibleClient` 对超时最多再试 2 次（`timeout_retry_attempts`，仍是每次 900 秒），并把这些受影响的链在新目录 `matrix-retry-001` 中以并发 100 重新采样；`scripts/merge_reports.py` 把主目录与补跑目录合并成带来源标注的报告。这是对“未知请求不自动重发”规则的明确偏离：首次样本从未被观察到，重试得到的是第一个被观察的样本，不构成挑选；代价只是服务端重复推理。原 `matrix/` 报告保留不改。
