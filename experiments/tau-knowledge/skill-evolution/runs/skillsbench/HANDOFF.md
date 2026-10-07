# SkillsBench：GPT-5.6 Terra 与 Opus 4.8 全85题交接

## 1. 交给同事做什么

各运行一套作者发布的 **85题、benign、逐题独立 Skill** 实验，方法为 `skillsbench.skill-evolution.v4`。两套采用同一数据、源码、检索、执行器与演化预算，模型分别为 GPT-5.6 Terra 和 Claude Opus 4.8。先测 NoSkill，再创建 S0、完整执行允许的演化，最后独立评价每个实际内容版本。不得只测最终包。

目标是分别回答：初始 Skill 相比无 Skill 有无帮助；演化相对本链同一个 S0 能否救回任务、增加部分得分，或发生退化；失败集中在资料、公开验证、修改还是 fresh 重建。比较模型时，以任务配对并报告实际覆盖，不把不同覆盖率直接相减。不保证演化提升，也不是等计算量的模型能力排名。

| 实验 | 配置与逐题清单 | 正式结果目录 |
|---|---|---|
| GPT-5.6 Terra | [config.yaml](full-85-gpt56-v4/config.yaml)、[manifest.json](full-85-gpt56-v4/manifest.json) | `full-85-gpt56-v4/matrix/` |
| Claude Opus 4.8 | [config.yaml](full-85-opus48-v4/config.yaml)、[manifest.json](full-85-opus48-v4/manifest.json) | `full-85-opus48-v4/matrix/` |

本交接不启动付费矩阵。**准备目录与验收记录不是模型成绩，也不代表85题已全部 READY。** 两套共用本目录的 [源码包](skillsbench-v4-source.tar.gz) 与 [文件/hash清单](transfer-manifest.json)，不各复制一套 pipeline。Git checkout 或源码包二选一；源码包解压后保留仓库相对目录。机器准备完成后冻结新身份，再开始收费运行。

## 2. 模型、方法与固定参数

| 项目 | GPT-5.6实验 | Opus实验 |
|---|---|---|
| 精确 model ID | `openai.gpt-5.6-terra` | `anthropic.claude-opus-4-8` |
| 传输 | `bedrock-responses`；Mantle `/openai/v1/responses` | `bedrock-messages`；Mantle `/anthropic/v1/messages` |
| Region | `us-east-1` | `us-east-1`；不能用 us-east-2 替代 |
| 学习角色 | Analyzer、Generator、Verifier，各自独立会话 | 同左，各角色均使用 Opus，不能混入 GPT |
| 正式 fresh 执行 | 作者 CodexSkillOnly + native Codex 0.160.1 | 相同 CLI，host 将 Responses 工具协议转换为 Messages |
| 输出 | `max_output_tokens: null`，无实验费用或输出配额 | 配置同左；Messages API必须发送 `max_tokens`，省略实验上限时使用模型卡的128,000服务上限 |

精确型号与接口依据 [GPT-5.6 Terra 模型卡](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-terra.html)、[Opus 4.8 模型卡](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-4-8.html)及 [AWS Messages API](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-messages-api.html)。GPT-5.6这里明确选 **Terra**，不是 Sol 或 Luna。要换变体须新增配置/身份，不能继续同一 checkpoint。账户还需具有对应模型访问权限；目录可见不等于一次真实 inference 已通过。Opus 的工具、签名 thinking 与终止原因经过协议转换；本地 mock 不证明真实模型兼容性。

同一个CLI会按模型选择工具协议：GPT-5.6使用原生code mode（`functions.exec/wait`），Opus使用普通终端工具。因此这是整套同型号pipeline的比较，不是工具目录完全一致的纯模型能力对照。固定CLI及其同release的 `codex-code-mode-host` companion，关闭两代multi-agent与`agents.enabled`；不得临时换成另一个模型的工具配置。真实Docker模拟provider已验证exec/wait、Opus终端/图片及拒绝子agent，真实模型兼容性仍须后面的付费smoke。

Opus转换支持文本与规范 `input_image`（PNG/JPEG/GIF/WebP的base64或HTTP(S) URL），不在host获取图片；未支持的PDF/file ID、server工具及未知内容显式拒绝。JSON与custom-tool grammar依靠提示和host校验，不称服务端Structured Outputs。Codex上下文admission将文本与图像分开估算：文本用固定tokenizer，内联图像读取尺寸、按未缩放patch数加1.2安全系数，URL每张预留36,000。图片原字节完整发送；不把base64当文本，不缩图或修改任务。估算、实际usage及拒发原因分别记录；它不是厂商原生精确计费计数，极大图片仍可能超过114,688输入上限。

两个实验共同遵守：

- 固定 CoEvoSkills `4380d4bff673dd6e1d58e5babeb2aaa0fe527119`、Harbor `3f28e5ce2acbff36d8b5df431e35e050ac13bef6`。原85篇背景合并成122个检索块；仅 background docs 入池。当前题 instruction/environment 直接提供。隐藏测试、solution、作者 Skill、其它题 environment 不进入学习。
- BM25 Top10 + Qwen3-Embedding-4B Top10，RRF60；2048-token块、128重叠，confidence≥0.1；搜索30次、Analyzer50轮、B*≤32,768 tokens，无篇数配额；澄清/银行只读均0。
- 冻结B*后只有一次 S0 HTTP POST，创建不执行、自测或补救。后续继承父包，Generator 在同一持续任务容器/Compose中直接执行、观察、修改并显式提交；Verifier独立检查提交快照。
- 固定测试修 Skill；全部通过才 fresh oracle。Oracle失败升级测试，复验同一快照；成功即停。最终取成功包，否则取最后安全包，不用独立评价择优。
- M15修订尝试、K5有效oracle、5次oracle设施错误；Generator全链120轮、每次活动3600秒；Verifier初建/升级30轮、诊断8轮、每测试版本一次正式程序修复。
- Generator high，其余 medium。保守统一272K上下文、β0.7、输入157,632、输出预留32,768；不删自身历史绕过容量。相同 effort 名称不保证两厂商思考计算量一致。终端合并输出64KiB，模型仅收8KiB预览及原始证据引用。
- Fresh Codex oracle最多3000秒、独立评价7200秒，100请求/800任务工具边界；各题资源、网络、依赖与服务采用官方任务配置。冻结检索池不能宣称终端禁止联网。

机制、威胁模型、指标定义见 [PROTOCOL](../../PROTOCOL.md)；作者来源与适配见 [SOURCE](../../meta/coevo-authoring/SOURCE.md)。这是迁移作者交互演化机制的一次创建/固定资料变体，不称完整论文复现。

## 3. 准备状态与启动门槛

逐题真实环境证据集中在 [readiness](../readiness-skillsbench-full85-20261007-001/final-status.json)，两份 manifest 保存交接时快照。READY要求 fresh环境、公开终端、native Codex 和官方grader探针通过，不能仅以镜像build成功代替。本机证据不能替代同事运行机器上的 preflight。最新测试与hash见 [acceptance.json](../readiness-skillsbench-full85-20261007-001/acceptance.json)。

截至2026-10-07，本机 **41题当前源码Docker准入通过，44题未就绪**。未就绪的44题为43题尚未启动准备及Druid慢下载被本轮交接冻结取消；均为`DEFERRED_BY_HANDOFF_FREEZE`、准入未测，不是模型任务失败。Docker磁盘12GiB保护线未触发；原任务的构建/评分时限未改。所有85题状态已封存，两个准备调度器已退出，本轮容器无残留；97份历史锁字节未变。摘要见 [summary](../readiness-skillsbench-full85-20261007-001/summary.json)，逐题锁/结果校验见 [validation](../readiness-skillsbench-full85-20261007-001/validation.json)。

代码验收为 **1158 passed／54显式跳过**；25项真实Docker用例通过（银行/helper14、SkillsBench11），另有两型号native CLI模拟provider场景及512原图反例。跳过项不算通过，模拟用量和reward不算模型成绩。CLI图片fixture的文本计数为字符代理；另用固定Qwen tokenizer核验同尺寸图像，原base64全文约778K tokens，改为文本＋视觉预留后399/541；这些仍是输入估算验证，不是模型实际usage。第二名独立审查代理已复核接口、恢复和准确命令。

| 尚需运行者确认 | 处理方式 |
|---|---|
| 模型凭据及两型号权限 | 本机提供 Bedrock token；分别做模型 preflight 和付费单题 smoke。本次未读取实验key，真实新模型均 `NOT_MEASURED` |
| pg-essay-to-audiobook | 官方 grader 必需独立 OpenAI key，当前没有，明确 `NOT_READY`；Bedrock key不能替代 |
| 85题Docker环境 | 按逐题 manifest 构建/验收；失败、未建及磁盘受阻均不能标 READY |
| 多服务 | fix-visual-stability、hvac-control必须保留官方sidecar、健康检查及内部域名 |
| Dense | CUDA GPU、固定HF revision、vLLM依赖及索引；另一机器需实际重建和封存 |
| native Codex | 固定Linux ELF 0.160.1及同release的code-mode companion，分别校验hash、MAIN ABI及pinned Harbor；npm JS launcher不合格 |

**缺少 pg 的任务key时，不能宣布完整85题可启动。** 可以明确以单题或预先声明的子集调试，但总报告仍保留85题分母、未测null。不要静默删题、修改grader或借用模型凭据。全85收费运行只在全部任务和对应模型的 preflight `ready=true` 后开始。

Docker保留官方 USER/WORKDIR/ENTRYPOINT、网络和依赖。原MAIN没有Python时，只从固定runtime复制独立 `/.tau-python` 作为公开relay解释器，不复制Verifier依赖或测试；原镜像与衍生MAIN分别锁定并核对配置。精确优先 `docker-compose.yaml`，否则Dockerfile；不猜 `.yml`。评分在fresh执行episode中先永久关闭模型/公开工具，再注入规定的 verifier.env 并运行官方测试。这种阶段切换不等同独立评分容器对后台进程的隔离强度。sidecar聚合资源和磁盘quota仍按实际验收范围报告。

## 4. 第一步：取代码，选一套配置

以下从仓库根执行。需Linux x86_64、Python3.12、uv、git、curl、Docker CLI/daemon权限、Compose plugin，以及可运行固定embedding的CUDA GPU。先选GPT套；跑完后将 `SB_VARIANT` 改为 `full-85-opus48-v4`，所有阶段重新使用另一套目录。两个实验不共用模型会话、base、Skill或checkpoint。

```bash
make setup PYTHON=python3.12
SB_CODE=experiments/tau-knowledge/skill-evolution
SB_VARIANT=full-85-gpt56-v4
SB_PACK="$SB_CODE/runs/skillsbench/$SB_VARIANT"
SB_CFG="$SB_PACK/config.yaml"
SB_RUN="$SB_PACK/matrix"
export AWS_REGION=us-east-1
docker version
docker compose version
.venv/bin/python - "$SB_CFG" <<'CHECK'
import sys
from pathlib import Path
from tau_skill_evolution.spec import load_spec
s = load_spec(Path(sys.argv[1]))
assert len(s.tasks) == len(s.cells) == 85
assert s.arms == ("benign",)
print(s.provider_settings["model"], s.provider_settings["transport"], len(s.cells))
CHECK
.venv/bin/python "$SB_CODE/scripts/prepare_skillsbench.py" --source
```

`--source`获取固定上游和官方任务；正式学习挂载不包含私有 grader。不要reset已有上游或修改任务recipe来掩盖失败。源码压缩包不包含凭据、官方测试/solution正文、虚拟环境、模型权重、native binary或Docker镜像。

## 5. 第二步：准备 Codex、Dense 与逐题环境

native Codex可从官方固定release取得；先验证ELF binary hash，再加入PATH。以下安装到项目外，不把二进制混入源码包：

```bash
SB_BIN="$HOME/.local/skillsbench-codex-0.160.1"
mkdir -p "$SB_BIN"
curl --fail --location https://github.com/openai/codex/releases/download/rust-v0.160.1/codex-x86_64-unknown-linux-musl.tar.gz --output "$SB_BIN/codex.tar.gz"
tar -xzf "$SB_BIN/codex.tar.gz" -C "$SB_BIN"
echo 'f34a4d2301892ae96c90097786bfe5dc269f187b6f69faf42a7b357b8c081e35  '"$SB_BIN/codex-x86_64-unknown-linux-musl" | sha256sum --check
ln -sfn "$SB_BIN/codex-x86_64-unknown-linux-musl" "$SB_BIN/codex"
curl --fail --location https://github.com/openai/codex/releases/download/rust-v0.160.1/codex-code-mode-host-x86_64-unknown-linux-musl.tar.gz --output "$SB_BIN/code-mode-host.tar.gz"
tar -xzf "$SB_BIN/code-mode-host.tar.gz" -C "$SB_BIN"
echo 'b33e8a5283f3c65c2a0aca6d43a59cfe850f624d8fa16992e3cad4fcc27c14e1  '"$SB_BIN/codex-code-mode-host-x86_64-unknown-linux-musl" | sha256sum --check
ln -sfn "$SB_BIN/codex-code-mode-host-x86_64-unknown-linux-musl" "$SB_BIN/codex-code-mode-host"
export PATH="$SB_BIN:$PATH"
.venv/bin/python - "$SB_CFG" <<'CHECK'
import sys
from pathlib import Path
from tau_skill_evolution.codex_runtime import codex_identity
from tau_skill_evolution.spec import load_spec
print(codex_identity(load_spec(Path(sys.argv[1])).values["runtime"]["codex"]))
CHECK
uv venv --python python3.12 "$SB_CODE/data/embedding/.venv"
uv pip install --python "$SB_CODE/data/embedding/.venv/bin/python" -e . -r "$SB_CODE/runtime/embedding-requirements.txt"
"$SB_CODE/data/embedding/.venv/bin/python" -c 'from huggingface_hub import snapshot_download; snapshot_download("Qwen/Qwen3-Embedding-4B", revision="5cf2132abc99cad020ac570b19d031efec650f2b")'
"$SB_CODE/data/embedding/.venv/bin/python" "$SB_CODE/scripts/prepare_skillsbench.py" --pool
```

先将**两份配置**的GPU UUID、embedding endpoint/vllm路径改成同事机器实际值，再保存配置。配置内其它方法参数不随意修改。embedding依赖固定vLLM/Transformers范围，尚非完整依赖hash锁，新机器仍需封存实际依赖版本。两模型可共用一个Dense服务和确定性索引。

在另一终端以所选配置启动Dense，避免默认读取τ配置：

```bash
.venv/bin/python - "$SB_CFG" <<'EMBEDDING'
import os, sys
from pathlib import Path
from tau_skill_evolution.retrieval import embedding_argv
from tau_skill_evolution.spec import load_spec
s = load_spec(Path(sys.argv[1]))
a = embedding_argv(s)
os.execvpe(a[0], a, {**os.environ, "CUDA_VISIBLE_DEVICES": s.values["embedding"]["gpu_uuid"]})
EMBEDDING
```

服务就绪后回到原终端：

```bash
SB_EMBEDDING=$(.venv/bin/python - "$SB_CFG" <<'SETTINGS'
import json, sys
from pathlib import Path
from tau_skill_evolution.spec import load_spec
print(json.dumps(load_spec(Path(sys.argv[1])).values["embedding"]))
SETTINGS
)
"$SB_CODE/data/embedding/.venv/bin/python" "$SB_CODE/scripts/prepare_skillsbench.py" --index-settings "$SB_EMBEDDING"
SB_LOCK_TEMPLATE='runtime/skillsbench-docker-{task_id}-v4-lock.json'
.venv/bin/python "$SB_CODE/scripts/prepare_skillsbench.py" --docker --all-tasks --runtime-lock "$SB_LOCK_TEMPLATE"
```

镜像准备会生成逐题真实image ID/digest的锁，仍须fresh preflight。`--all-tasks`遇构建错误即停；按manifest使用 `--task TASK_ID --docker --runtime-lock "$SB_LOCK_TEMPLATE"` 补齐。不要填虚构digest或降级host。Docker卷要有充足空间，重型PyTorch/CUDA及服务题可能大量占盘；先由管理员准备足够存储，不全局prune其它实验镜像。

**所有SkillsBench runtime锁都进入运行身份。** 两套共用环境锁，必须先完成全部准备再开始模型实验；实验运行中不能增改锁、源码、提示或配置。旧锁保留原字节，新配置只选择 `skillsbench-docker-{task_id}-v4-lock.json`。

## 6. 第三步：本机凭据与 preflight

模型token保存在项目外私有目录，0700/0600。长矩阵用外部更新的JSON token文件，内容为 `{"token":"本机真实token","expires_at":"实际UTC到期时间"}`；原子替换，每次POST重读，提前60秒拒过期。不能把签名URL表面期限当底层AWS会话期限。pipeline不会自行生成key。以下占位路径/账号必须换成本机实际值，不提交到Git。

```bash
SB_TOKEN_DIR=/path/to/private/bedrock-tokens
SB_ACCOUNT=123456789012
export AWS_BEARER_TOKEN_BEDROCK_FILE="$SB_TOKEN_DIR/$SB_ACCOUNT.json"
unset AWS_BEARER_TOKEN_BEDROCK
```

任务API key独立于模型key，仅从 `SKILLSBENCH_TASK_<大写任务ID，连字符换下划线>_<原变量>` 读取。由本机受保护凭据加载器在启动进程前加入环境；不要在命令历史粘贴真实值。必需项是 `SKILLSBENCH_TASK_PG_ESSAY_TO_AUDIOBOOK_OPENAI_API_KEY`。pedestrian声明可选OpenAI/Gemini/Anthropic，pg公开阶段可选OpenAI/ElevenLabs，trend可选OpenAI/Anthropic；缺可选项如实报告，不能从宿主全局同名变量回退。值仅按声明传给该任务阶段，不复制全部宿主环境，不写Compose/配置/argv。

```bash
.venv/bin/r2sp preflight --experiment skillsbench --runtime docker --config "$SB_CFG" > "$SB_PACK/preflight.json"
```

检查命令exit0且JSON `ready=true`。该命令验证模型目录鉴权、Dense、upstream、所有选定任务锁、fresh环境/grader/native Codex；目录鉴权**不是**真实生成调用。失败看具体checks：401/403先修模型凭据/权限；任务key缺失单独解决；镜像、依赖和评分环境失败先修准备。不得忽略preflight继续完整运行。

## 7. 第四步：每个模型先做单题 smoke

先以 dialogue-parser 跑baseline及完整链；这里开始收费。smoke和matrix隔离，不拿smoke checkpoint续正式矩阵，不用smoke结果挑任务或改方法。

```bash
SB_SMOKE="$SB_PACK/smoke/trial-001"
set -e
mkdir -p "$SB_PACK/smoke"
.venv/bin/r2sp preflight --experiment skillsbench --runtime docker --config "$SB_CFG" --task dialogue-parser > "$SB_PACK/smoke/preflight.json"
.venv/bin/r2sp evaluate --experiment skillsbench --runtime docker --config "$SB_CFG" --task dialogue-parser --arm benign --no-skill --run-dir "$SB_SMOKE"
.venv/bin/r2sp run --experiment skillsbench --runtime docker --config "$SB_CFG" --task dialogue-parser --arm benign --run-dir "$SB_SMOKE"
.venv/bin/r2sp report --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_SMOKE"
```

确认检索、FrozenBase、S0单次封存、Generator实际提交、公开检查、fresh oracle和独评都有机器记录。utility0也可以符合机制验收；S0成功早停允许零修订。若未达到oracle、UNKNOWN或程序故障，不能说整个流程跑通。每套模型都要做；Opus mock验收不能替代这一步。smoke报告使用85题配置，覆盖为1/85，不称85题成绩。

## 8. 第五步：NoSkill 与85条完整链

全部85题preflight通过且smoke机制确认后，在空 `matrix/` 中按以下顺序运行。建议先只跑一套模型，避免互相争用资源；两套用各自的 `SB_CFG/SB_RUN` 重复全部步骤。NoSkill可能耗时，完整矩阵不保证一小时key完成，需持续有效凭据。

```bash
set -e
.venv/bin/r2sp evaluate --experiment skillsbench --runtime docker --config "$SB_CFG" --no-skill --run-dir "$SB_RUN"
.venv/bin/python "$SB_CODE/scripts/launch_matrix.py" --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_RUN" --token-dir "$SB_TOKEN_DIR" --accounts "$SB_ACCOUNT" --max-concurrent 2 --stagger-seconds 3 --r2sp "$PWD/.venv/bin/r2sp"
.venv/bin/r2sp report --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_RUN"
```

NoSkill以同型号、同native执行器fresh完成任务，不创建Skill，不回流结果。launcher每题依次 create/evolve/evaluate，自动独评所有实际封存内容；没有NoSkill阶段，不能省第一条。明确并发2，机器资源或provider限流不足改1；默认96不能照搬，并发不改变M/K。NoSkill命令为串行；希望完全串行演化可用 `r2sp run ... --run-dir "$SB_RUN"` 代替launcher。

出门前在 `tmux new -s skillsbench-gpt56`（另套名 `skillsbench-opus48`）中执行上述命令；Ctrl-B、D脱离，`tmux attach -t NAME`重连。这是保持前台命令的终端，不是自动恢复或凭据续期服务。只有前一阶段成功且状态符合验收才启动后续阶段；不要用忽略退出码的shell脚本串起来。可先给launcher加 `--dry-run` 检查85条命令，dry-run不验环境、不调用模型。

## 9. 运行中怎么看、断了怎么恢复

| 位置 | 用途 |
|---|---|
| `matrix/launcher-status.json`、`matrix/logs/` | 每题进程/退出/鉴权停止与运行日志；exit0不等于utility1 |
| `matrix/report.json`、`matrix/REPORT.md` | 正式任务/版本/配对汇总；运行中避免和cell锁冲突，最好结束后统一report |
| `matrix/journal/identity.json` | 源码、配置、提示、数据、环境身份；不手动改hash |
| cell中的FrozenBase、sealed包、submission、tests、evolution、evaluation | 逐步封存、父版本/快照/测试/评分依据，实际路径以report和journal引用为准 |
| `data/skillsbench/private-models/.../official-grader/` | 私有逐项CTRF、reward、stdout/stderr/hash，审计用，不给模型或公开交接包 |

同一身份重新运行原阶段命令，会复用已封存结果。保留完整run-dir、候选/工作区、私有journal及持续container/Compose，不能只复制REPORT。`NOT_SENT`可首次派发；原响应已收到只解析；`UNKNOWN`禁止重发，尤其S0最多一次POST。持续容器丢失/重启不能用文件快照假装恢复服务与进程。鉴权失败停止启动后续题；更新token不会清除已封存401/403或UNKNOWN，结束的演化不自动继续。

要整链重采样，另开新trial并单列，与primary分开，不能覆盖旧链或算演化收益。仅补测已封存安全包，可使用**原配置与原源码身份**导入另一个空评价run：

```bash
.venv/bin/r2sp evaluate --experiment skillsbench --runtime docker --config ORIGINAL_CONFIG --task TASK_ID --arm benign --bundles-from ORIGINAL_RUN --run-dir NEW_EMPTY_RUN
```

这产生新的fresh评价样本，不继续学习、不重发S0，原缺测保留。旧GPT5.4十题与旧源码checkpoint不能用新配置续接。新机器准备/模型访问变化也要按身份规则核验，不放宽检查。

## 10. 最后交回什么，如何判断进步

每套交回 config/manifest、preflight、identity、完整run机器产物、REPORT.md/report.json、launcher状态及token用量；私有原始评分证据单独受限保存，不上传模型聊天、凭据或隐藏答案。随后按两模型共同实测任务配对比较，完整分母仍各85。

| 要报告的量 | 计算与要求 |
|---|---|
| NoSkill / S0 / Final Task pass rate | official reward==1的题数÷85，同时报实测n、覆盖率与未测原因 |
| 每题 S0、S1、S2… | 全部实际内容hash的utility、reward、GT passed/total/rate及计数单位，不补造早停版本 |
| 相邻版本 Δ | 对每个实际相邻内容版本算Δutility、Δreward、ΔGT；同题双方均实测，GT单位/总数/来源一致，否则null及原因 |
| NoSkill→S0、S0→Final | 同样配对；各指标分别报paired_n、均值、救回/退化数量；Final=S0注明共享一次测量 |
| Surrogate | 实际pytest用例通过数/收集数，不是assert数量；只在同suite比较，升级后的分母不能当连续进步 |
| 演化成本与停止 | 修订尝试、unique内容、提交、learning execution、terminal、suite、oracle有效/错误次数、停止原因、provider usage；金额无账单/报价则未测 |

本pipeline原生报告已支持相邻版本和两端增量，不需手工补S1–S5。S编号是去重后的内容版本，**不是**执行次数或修订尝试；invalid/unchanged仍耗M，A→B→A最终父版本指B，但内容仅两个。缺测写null/`NOT_MEASURED`，不能当实测0；公开通过不能替代官方成绩。SkillsBench不报告银行ASR/Action Recall。

历史GPT5.4十题见 [REPORT](gpt54-direct-10-20261007-001/REPORT.md)：NoSkill10题4成功，S0实测7题3成功，Final实测6题4成功；coverage不同不能直接做3/7→4/6结论。DAPT某次修订损坏了公开端口统计；另有检查范围歧义，历史原始CTRF缺失不能补造具体官方失败项。新版已加强公开义务引用/范围、逐项原始证据封存、上下文输入和反馈隔离，但不保证单调提高。这两套新模型全部成绩目前 `NOT_MEASURED`。
