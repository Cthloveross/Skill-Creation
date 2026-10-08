# SkillsBench v6：直接作者控制器的实验交接

当前入口直接调用 CoEvoSkills 固定 commit `4380d4b…` 的完整演化控制器，作者源码和 skill-creator 保存在 `src/tau_skill_evolution/author/coevo/`，文件与 hash 见 `author/VERIFIER_SOURCE.json`。本地不再复制 SkillsBench 状态机。只适配模型/Journal、持续任务环境、fresh Codex 评分、公开输入和完整封包。

当前同质五题真实补测 [codex-author-fix-20261008-004](codex-author-fix-20261008-004/public-summary.json) 已 **COMPLETED**，身份 `0f39848a…`。五题的 NoSkill、S0、全部实际内容版本及 Final 均有独立 fresh 官方评分：Task pass 为 **20% → 40% → 80%**。实际型号是本机 Codex 订阅可用的 **`gpt-6.1-sol`**，不是 GPT-5.4 或论文模型，也不是下方 GPT-5.6／Opus 两套85题矩阵的成绩。底层 HTTP 次数及 Codex 内部重试不可观察。五题重新测量，不复用旧试验分数；本次结果仅支持这五题的配对观察，不能外推全部85题。

004的五题环境与本机Codex型号目录预检已 `READY`，最终源码通过 **1478 passed／57 skipped／0 failed**、真实Docker和第二名审查，见 [004 readiness](../readiness-skillsbench-native-controller-20261008-004/final-status.json)。五题机器数据已由第二名审查者完成 [97项核对](codex-author-fix-20261008-004/public-summary-independent-review.json)，全部通过并保留方法限制。模型实测与源码验收分别封存；它们不代表85题环境全部就绪。

此前 `codex-author-fix-20261008-003` 为 **STOPPED_PARTIAL_TRANSPORT_GATE**、身份 `ce9c36a1…`：四题完整完成，DAPT 的 Generator 操作因 Codex 原生能力或 compaction 门禁中止，事件具体类型未能从留存证据确证。Journal 保留 `UNKNOWN`，不能重发或补造 Final；DAPT未执行的独评保持 null。已有四题只作该历史试验结果，停机与逐题容器清理见 [terminal-transport-stop.json](codex-author-fix-20261008-003/evidence/terminal-transport-stop.json)。

前两次补测均只读保留，不续 checkpoint、不并入本次：`codex-author-fix-20261008-001` 的封包接口误拒合法 `evals/` 附件并丢失导出文件；`codex-author-fix-20261008-002` 在原作者 async 循环调用同步 oracle，导致 `asyncio.run()` 嵌套，fresh Codex 尚未请求模型即失败。001 的16次 invalid 和002的该次未测 GT 属于接口错误，不是官方任务失败；UNKNOWN 不重发。更早的 `codex-quota-five-20261007-003` 是另一历史试验。

真实Docker检查覆盖完整封包、持续环境、context停止、原作者末端GT及唯一清理责任。端到端fixture实际贯通原作者控制器→真实oracle→pinned Codex CLI→本机脚本Responses→官方grader→fresh独评；官方检查真实运行，模型为 `MODEL_SCRIPTED`，初始包为显式fixture。封包／回滚分支fixture的评分为 `MOCK_ONLY`。这些检查验证执行机制，不能充当真实模型成绩、85题准入或utility提升证据。003身份的1423项历史回归另保留在 [003 readiness](../readiness-skillsbench-native-controller-20261008-003/final-status.json)。

## 1. 交给同事运行什么

分别运行 GPT-5.6 Terra、Claude Opus 4.8 两套实验，每套为作者发布的全部85题、benign、每题独立创建和演化一个 Skill。每题测 **NoSkill、S0、所有实际后续内容版本及 Final**，不能只交最终成功率。两套使用相同任务、资料池、源码和执行器，各自保留模型会话、Skill、运行身份及结果。

| 实验 | 固定配置 | 任务清单 | 新结果目录 |
|---|---|---|---|
| GPT-5.6 Terra | [config.yaml](full-85-gpt56-v6/config.yaml) | [manifest.json](full-85-gpt56-v6/manifest.json) | `full-85-gpt56-v6/matrix-author-v6-001/` |
| Claude Opus 4.8 | [config.yaml](full-85-opus48-v6/config.yaml) | [manifest.json](full-85-opus48-v6/manifest.json) | `full-85-opus48-v6/matrix-author-v6-001/` |

当前源码交付包为 `skillsbench-v6-final-20261008-004-source.tar.gz`，文件、来源及外置校验信息由 [transfer-manifest.json](transfer-manifest.json)绑定；只在五题数据二审、公开隐私检查及包校验全部通过后发布。验收与公开结果的机器证据放在Git仓库，由 descriptor 引用；源码包只提供代码、公开资料和配置，不包含运行日志。旧 `skillsbench-v6-source.tar.gz` 是修复前快照，保持原字节，不用于新运行。使用交付 commit 或校验后的源码包，不混用另一分支的源码。包中不带凭据、模型权重、虚拟环境、Docker镜像或私有原始评分。`full-85-*-v4`、旧源码包和旧结果是历史记录，不能续接到 v6。

交付的两套模型配置仍为原有型号。源码变更后需要新运行身份和新目录；旧 v4/v5 结果与源码包只读保留。尚无该新源码的全85题 fresh 准入或两套 Bedrock 模型 smoke，均为 `NOT_MEASURED`。PG 仍缺任务专用 OpenAI 凭据，不能称全部85题已就绪。

## 2. 方法、预算及作者来源

方法为 `skillsbench.skill-evolution.v6`：检索背景资料 → 冻结 B* → 一次生成 S0 → Generator 在持续任务环境执行、修改父包并提交 → 作者 Verifier → fresh 官方 oracle → 独立逐版本评估。

完整包覆盖 `SKILL.md` 与所有安全 UTF8 文本附件，支持 `scripts/`、`references/`、`evals/`、`assets/`及其他合法相对路径，脚本不限定 Python 扩展名。保留路径穿越、特殊文件、非 UTF8、元数据保留名及内容 hash 校验；运行生成缓存只从候选包采集中排除，封存包校验不忽略篡改。作者普通导出经过薄适配补齐全部已提交文件，使 GT、best、回滚和独评使用同一完整内容；不把未提交草稿当版本。银行的 Python 脚本执行接口不随此修改放开。

固定 CoEvoSkills commit `4380d4bff673dd6e1d58e5babeb2aaa0fe527119`，Harbor commit `3f28e5ce2acbff36d8b5df431e35e050ac13bef6`。完整演化控制器、Verifier、支持实现与提示按原字节封存，见 [VERIFIER_SOURCE.json](../../src/tau_skill_evolution/author/VERIFIER_SOURCE.json)；执行器使用固定作者 CodexSkillOnly，见 [SOURCE.json](../../src/tau_skill_evolution/author/SOURCE.json)。直接调用作者 `HarborTerminus2Evolution.setup/run`，由本项目 Journal、容器和包接口承接，不引入 Harbor 整套调度。

本次仅改 SkillsBench。τ-Knowledge及历史 v4 的方法、预算和结果保持原合同。

| 项目 | v6 固定设置及准确含义 |
|---|---|
| 数据/检索 | 85题背景资料合池，仅 background 入池；当前题 instruction/environment 直接提供。隐藏测试、solution、作者 Skill 与其它题 environment 不入池 |
| 检索参数 | BM25 Top10 + Qwen3-Embedding-4B Top10、RRF60；2048-token块、128重叠；confidence≥0.1；30次搜索、50轮Analyzer、B*≤32,768 tokens；不设文档篇数配额 |
| S0 | 最多一次创建 HTTP POST，只做安全结构封装，不执行、自测或修复；未知结果不重发 |
| 学习 | 同题 Generator 持续会话/MAIN环境；执行、观察、修改候选包、显式提交。终端每次新 shell；文件、安装和服务持续，单条命令的 cwd/export 不自动继承 |
| Verifier | 作者独立会话在学习 MAIN 读取真实公开文件、生成/运行测试；普通修订固定 suite，官方拒绝后回到 Generator，下一次提交再升级测试 |
| r15 | 最多15次 surrogate 失败/不可用等相应 host 干预；首个 checklist 未完成也计一次。**不是15次 Skill 修改上限** |
| K5 | 最多5次正常 GT 干预；设施故障退款，连续5次设施故障停止。cap-final/post-final 单独记录；4次正常GT后触发r15时，实际GT可以到第6次 |
| Generator | 120个有效 episode；解析成功进入执行/完成分支即计一次，即使命令列表为空；纯Skill工具及解析失败不算。物理POST数单独记录，没有额外120 POST或每次3600秒修订限制 |
| 时间 | 学习外层7200秒绝对截止，恢复不重置；任务agent时限×5用于fresh oracle，命令受作者900秒边界及剩余时间约束。独评每次另开7200秒时限 |
| Context | Generator high，其余medium；有效窗口 min(配置272,000, 已观测provider窗口)，β0.7、输入配置上限157,632、预留32,768；保留自己的历史与opaque continuation |
| 输出/费用 | 不设实验输出token或费用额度；仍保留API必需字段、上下文/时限、终端64KiB捕获及8KiB模型预览。省略额度不意味着服务没有上限 |
| Schema/checklist | 检查门禁后使用作者schema；目录固定为`/app/environment/skills/evo-current`，`SKILL.md`的`name: evo-current`须一致。创建不做该质量检查；`/root/progress.md`按作者规则检查/重置 |
| 最终选择 | 正常/cap GT中官方reward严格提高才更新best，平分保留较早快照；按作者终止分支回滚。**不用独评结果挑版本** |

上下文记录完整可见历史估算、最近provider input/output（含reasoning）及后续增量；累计计费tokens不是上下文占用。占用进入原作者的token_budget门禁。仅Generator派发前明确的InputTokenBudgetExceeded允许停止新的Generator请求、继续原schema/best/reuse/post-final收尾，并须有原日志token_budget证明；不能伪造响应或把已派发UNKNOWN改称预算停止。订阅传输的原生工具与compaction分别封存事件流并停止，003的具体事件类型仍未确证。

GT先采用有限数值的官方 reward；缺失/非法 reward 在实际已完成且可验证的官方测试计数存在时回退 passed/total。明确的0/0按作者解析为0，GT检查率仍未测；缺少评分证据、损坏报告或真实驱动故障为 `NOT_MEASURED`。有限reward优先于检查率，不能把部分通过率冒充官方Task pass。

有限值优先规则仅用于v6私有oracle；独立评估仍采用现有官方reward在[0,1]内的准入合同。作者数据的正常reward均按官方值记录；若出现越界值，保留原文与两个阶段各自的解析状态，不将oracle展示分数伪装成独评成绩。

报告分开 **历史 best oracle分数、实际post-final fresh分数、作者终态展示分数、独立评估分数**。历史best较高不代表新fresh执行也取得该分数。独立评估不回流Analyzer/Generator/Verifier。Generator只得到允许的失败类别、公开schema/checklist信息和oracle布尔结果；不提供GT原始断言、具体值或reward。

`best_snapshot.record_available`表示历史评分记录存在，`author_record`保存作者快照记录，`rollback.status`记录实际回滚结果；封存包须另外通过 hash 校验。快照丢失时保留历史分数，不能声称已回滚；hash损坏与真实IO故障不伪装成可用快照。

这是迁移作者交互修改、验证和终止机制的检索冻结/一次创建变体，非完整论文复现。初次创建禁止自测、B*冻结及独立逐版本测量仍是本实验适配。Verifier会话独立，但在学习MAIN执行：不等同旧版独立Verifier容器的文件系统隔离；host不注入Generator推理或官方评分。作者诊断路径未重复初建的Skill禁读提示及日志审查，历史`codex-quota-five-20261007-003`真实试跑已读到共享`SKILL.md`，所以不能宣称全阶段都不读取Skill源码；证据见该批`evidence/3d-author-diagnosis-access.json`。Generator终端直接使用作者的受保护评分路径命令检查，拒绝直接访问Verifier及隐藏答案路径；这是命令启发式检查，不能保证任意shell命令无法绕过。fresh评分时先关闭公开工具，再挂官方测试。后台进程同容器阶段切换的隔离局限保留。详细定义见 [PROTOCOL.md](../../PROTOCOL.md)。

模型使用作者的 `task_complete` 提交；保留作者3个idle/30个stale episode的强制门禁，记录 `host_forced_submission`，与模型主动提交分开。只有进入门禁且能安全封装的完整包才形成版本，非法草稿保留失败证据并交给作者schema修复；不能补造评分。

## 3. 从新机器准备环境

以下命令从仓库根运行，要求Linux x86_64、Python3.12、uv、git、curl、Docker CLI/daemon访问、Compose和CUDA GPU。先运行GPT套，再将 `SB_VARIANT` 改为 `full-85-opus48-v6` 重复付费阶段。两套共用环境和Dense，但不共用学习checkpoint。

```bash
set -e
make setup PYTHON=python3.12
SB_CODE=experiments/tau-knowledge/skill-evolution
SB_VARIANT=full-85-gpt56-v6
SB_PACK="$SB_CODE/runs/skillsbench/$SB_VARIANT"
SB_CFG="$SB_PACK/config.yaml"
SB_RUN="$SB_PACK/matrix-author-v6-001"
export AWS_REGION=us-east-1
docker version
docker compose version
.venv/bin/python "$SB_CODE/scripts/prepare_skillsbench.py" --source
```

`--source`获取固定作者任务、recipe、输入及官方grader；正式学习不挂grader/其他题。已有固定数据必须校验复用，不reset或改上游来掩盖失败。

新机器先为两套建立 `config.local.yaml`，使用独立本地环境锁目录。配置文件已存在时先检查，不覆盖。机器适配只改本地GPU UUID、embedding endpoint/vllm路径和本地lock模板；方法、任务、模型不随意改。以下操作须在付费前完成：

```bash
SB_LOCK_TEMPLATE='runtime/local/skillsbench-docker-{task_id}-v6-lock.json'
.venv/bin/python - "$SB_CODE" "$SB_LOCK_TEMPLATE" <<'LOCAL'
import sys
from pathlib import Path
import yaml
root, template = Path(sys.argv[1]), sys.argv[2]
for variant in ("full-85-gpt56-v6", "full-85-opus48-v6"):
    directory = root / "runs/skillsbench" / variant
    target = directory / "config.local.yaml"
    if target.exists():
        raise SystemExit(f"Inspect existing local config first: {target}")
    config = yaml.safe_load((directory / "config.yaml").read_text())
    config["source"]["runtime_lock"] = template
    target.write_text(yaml.safe_dump(config, sort_keys=False))
LOCAL
SB_CFG="$SB_PACK/config.local.yaml"
```

### 3.1 固定 native Codex

安装ELF二进制及同release code-mode companion，不使用npm JS launcher替代：

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
```

正式fresh执行使用同一个作者CodexSkillOnly：GPT-5.6 Terra经`bedrock-responses`，Opus经`bedrock-messages`转换。两个账户都要有准确型号的访问权限，均为us-east-1。GPT采用code mode，Opus采用普通终端工具；这是完整同型号pipeline比较，工具配置不完全相同，不称纯等计算量能力对照。Opus真实provider兼容性要单独smoke；本地mock不代表真实模型调用通过。

| 配置 | 精确model ID | 传输 |
|---|---|---|
| GPT套 | `openai.gpt-5.6-terra` | `bedrock-responses` |
| Opus套 | `anthropic.claude-opus-4-8` | `bedrock-messages` |

### 3.2 Dense 与索引

```bash
uv venv --python python3.12 "$SB_CODE/data/embedding/.venv"
uv pip install --python "$SB_CODE/data/embedding/.venv/bin/python" -e . -r "$SB_CODE/runtime/embedding-requirements.txt"
"$SB_CODE/data/embedding/.venv/bin/python" -c 'from huggingface_hub import snapshot_download; snapshot_download("Qwen/Qwen3-Embedding-4B", revision="5cf2132abc99cad020ac570b19d031efec650f2b")'
"$SB_CODE/data/embedding/.venv/bin/python" "$SB_CODE/scripts/prepare_skillsbench.py" --pool
```

把两份本地配置的GPU UUID/endpoint/vllm路径改成同事机器实际值。另一终端从仓库根启动Dense，显式使用SkillsBench配置：

```bash
SB_CFG=experiments/tau-knowledge/skill-evolution/runs/skillsbench/full-85-gpt56-v6/config.local.yaml
.venv/bin/python - "$SB_CFG" <<'DENSE'
import os, sys
from pathlib import Path
from tau_skill_evolution.retrieval import embedding_argv
from tau_skill_evolution.spec import load_spec
s = load_spec(Path(sys.argv[1]))
a = embedding_argv(s)
os.execvpe(a[0], a, {**os.environ, "CUDA_VISIBLE_DEVICES": s.values["embedding"]["gpu_uuid"]})
DENSE
```

服务就绪后，回原终端构建固定索引：

```bash
SB_EMBEDDING=$(.venv/bin/python - "$SB_CFG" <<'SETTINGS'
import json, sys
from pathlib import Path
from tau_skill_evolution.spec import load_spec
print(json.dumps(load_spec(Path(sys.argv[1])).values["embedding"]))
SETTINGS
)
"$SB_CODE/data/embedding/.venv/bin/python" "$SB_CODE/scripts/prepare_skillsbench.py" --index-settings "$SB_EMBEDDING"
```

两模型可共用此服务和索引。embedding依赖范围已固定，尚非完整wheel hash锁；实际依赖和GPU准备仍需本机封存，不宣称复制配置即READY。

### 3.3 Docker 与85题环境

直接使用作者各题 Dockerfile 或精确 `docker-compose.yaml`，保留 USER/WORKDIR/ENTRYPOINT、网络、sidecar、健康检查及任务内安装能力。预检确认构建、启动、公开终端和官方grader可用，**不要求空工作区reward=1**；缺交付物的合法负成绩可以准入，真正评分驱动缺库不能准入。

任务setup是执行环节；`DEFERRED_TASK_SETUP`只在公开要求、实际哈希绑定输入及合法负评分证据一致时准入。它不是官方grader通过，最终真实评分仍严格。镜像build成功、旧READY或文件夹存在，都不能替代新机器fresh检查。

如机器已有足够容量的Docker daemon，直接选其endpoint。若沿用本项目home内DinD实例，必须核对其Mounts能看到 **v6结果目录及专用TMPDIR的相同绝对路径**。旧实例只挂两个v4目录时，不能直接拿它跑v6。停止全部任务/build后才能重建外层容器挂载；禁止两个daemon同时使用同一data-root。不要全局prune同事镜像。

需要在home中新建实例时，可用以下一次性启动块；需现有Docker API允许privileged，但无需调用sudo。目录仍在可见项目内，不是rootless：

```bash
SB_ROOT=$(realpath "$SB_CODE")
SB_OUTER_HOST=unix:///var/run/docker.sock
SB_DOCKER_NAME=skill-evolution-author-v6-$(id -un)
SB_DOCKER_DATA="$SB_ROOT/data/docker-author-v6"
SB_DOCKER_RUN="$HOME/.local/share/skillsbench-docker/author-v6-run"
SB_PREP_TMP="$HOME/.cache/skillsbench-author-v6-tmp"
SB_DIND_IMAGE=docker@sha256:7613944c7bc318c7b97541bd0e65b8a18d033e37e204305f1ee2639fc9a03827
unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
install -d -m 700 "$SB_DOCKER_RUN" "$SB_PREP_TMP" "$SB_DOCKER_DATA"
docker --host "$SB_OUTER_HOST" pull "$SB_DIND_IMAGE"
docker --host "$SB_OUTER_HOST" run --detach --name "$SB_DOCKER_NAME" --privileged \
    --label org.tau.purpose=skillsbench-author-v6 --env DOCKER_TLS_CERTDIR= \
    --mount "type=bind,src=$SB_DOCKER_DATA,dst=/var/lib/docker" \
    --mount "type=bind,src=$SB_DOCKER_RUN,dst=/run/skill-docker" \
    --mount "type=bind,src=$SB_PREP_TMP,dst=$SB_PREP_TMP" \
    --mount "type=bind,src=$SB_ROOT/runs/skillsbench,dst=$SB_ROOT/runs/skillsbench" \
    --entrypoint /bin/sh "$SB_DIND_IMAGE" -c \
    'SB_GROUP=
    for SB_ENTRY in $(cut -d: -f1,3 /etc/group); do
        if [ "${SB_ENTRY#*:}" = "$1" ]; then SB_GROUP=${SB_ENTRY%%:*}; break; fi
    done
    if [ -z "$SB_GROUP" ]; then addgroup -g "$1" skill-host || exit 1; SB_GROUP=skill-host; fi
    exec dockerd-entrypoint.sh dockerd --host=unix:///run/skill-docker/docker.sock --group="$SB_GROUP" --data-root=/var/lib/docker --storage-driver=overlay2 --pidfile=/run/skill-docker/docker.pid' \
    sh "$(id -g)"
export DOCKER_HOST="unix://$SB_DOCKER_RUN/docker.sock"
export TMPDIR="$SB_PREP_TMP"
for SB_WAIT in $(seq 1 60); do
    if docker info >/dev/null 2>&1; then break; fi
    sleep 1
done
docker info >/dev/null
docker --host "$SB_OUTER_HOST" inspect --format '{{.State.Status}} {{json .Mounts}}' "$SB_DOCKER_NAME"
df -h "$SB_DOCKER_DATA"
```

这是可选的新空实例，会重新构建/载入镜像，不是默认再复制所有已准备环境。内层`DockerRootDir=/var/lib/docker`是容器路径；实际home空间看外层Mounts及上述df。Unix socket在项目外短路径，镜像/cache数据在项目内。外层看到结果父目录，不代表内层任务获得其它题目录；任务bind仍由逐题runner限定。不挂宿主Docker socket或整套宿主凭据。

选好daemon后，在原终端准备环境；两模型共用同一lock模板。完整准备结束再冻结identity，运行中不改锁：

```bash
.venv/bin/python "$SB_CODE/scripts/prepare_skillsbench.py" --docker --all-tasks --jobs 8 --runtime-lock "$SB_LOCK_TEMPLATE"
```

`--jobs 8`为离线准备并发，可按资源改小。构建不套正式任务时限，不自动重试；失败保留其它题的结果，按日志逐题用`--task TASK_ID --docker --runtime-lock "$SB_LOCK_TEMPLATE"`补齐。实际digest写入本地锁，不填虚构值，不覆盖历史锁。新增实验必须在daemon可见挂载范围内。

## 4. 凭据与实际 preflight

模型凭据放项目外受保护目录。单次可通过CLI `--env-file 本机文件`加载；长矩阵推荐JSON token文件，形如`{"token":"本机真实token","expires_at":"实际UTC到期时间"}`，0600、原子替换，实际到期前更新。每次POST重读；程序不会自行续期。一小时key不保证跑完85题，不把签名URL表面期限当底层会话期限。

```bash
SB_TOKEN_DIR=/path/to/private/bedrock-tokens
SB_ACCOUNT=123456789012
export AWS_BEARER_TOKEN_BEDROCK_FILE="$SB_TOKEN_DIR/$SB_ACCOUNT.json"
unset AWS_BEARER_TOKEN_BEDROCK
```

将占位路径/账号换为本机真实值，不在shell历史粘贴真实key。任务专用凭据独立加载；PG必需项为`SKILLSBENCH_TASK_PG_ESSAY_TO_AUDIOBOOK_OPENAI_API_KEY`。其它可选凭据按逐题声明提供；缺可选项如实记录，不回退宿主全局同名变量，不传全部环境。不要将task凭据写配置、Git、日志或Compose正文。

```bash
.venv/bin/python - "$SB_CFG" <<'CONFIG'
import sys
from pathlib import Path
from tau_skill_evolution.spec import load_spec
s = load_spec(Path(sys.argv[1]))
assert s.namespace == "skillsbench.skill-evolution.v6"
assert len(s.tasks) == len(s.cells) == 85 and s.arms == ("benign",)
print(s.provider_settings["model"], s.provider_settings["transport"], len(s.cells))
CONFIG
.venv/bin/r2sp preflight --experiment skillsbench --runtime docker --config "$SB_CFG" > "$SB_PACK/preflight.json"
```

必须exit0且JSON`ready=true`。检查型号权限、Dense、pinned数据、逐题镜像锁、fresh环境/grader/native Codex。模型目录鉴权不等于真实生成兼容性；下节smoke须两模型各做一次。目前PG缺必需凭据，完整85题准入会被阻止。补凭据后重新fresh准入，或按5.1节明确只启动其余84题；不能忽略失败继续85矩阵。

每个新终端重新设置`SB_CODE/SB_VARIANT/SB_PACK/SB_CFG/SB_RUN`、PATH、AWS Region、token文件和正确DOCKER_HOST/TMPDIR。变量不会自动继承其它终端；不要不知情地落回系统daemon或另一型号配置。

## 5. 两模型各做一个 smoke，然后完整运行

先以dialogue-parser验证机制；从这里开始收费。smoke与matrix目录隔离，不拿smoke checkpoint续正式矩阵，不根据smoke成绩删题或修改方法。

```bash
SB_SMOKE="$SB_PACK/smoke/author-v6-001"
mkdir -p "$SB_PACK/smoke"
.venv/bin/r2sp preflight --experiment skillsbench --runtime docker --config "$SB_CFG" --task dialogue-parser > "$SB_PACK/smoke/preflight.json"
.venv/bin/r2sp evaluate --experiment skillsbench --runtime docker --config "$SB_CFG" --task dialogue-parser --arm benign --no-skill --run-dir "$SB_SMOKE"
.venv/bin/r2sp run --experiment skillsbench --runtime docker --config "$SB_CFG" --task dialogue-parser --arm benign --run-dir "$SB_SMOKE"
.venv/bin/r2sp report --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_SMOKE"
```

确认真实检索、base、单次S0、Generator执行/提交、作者公开检查、fresh GT及独评有封存结果。utility0可以符合机制验收；S0成功早停允许没有S1。没有到达GT、UNKNOWN或未解决运行错误不能称完整smoke。这个配置的smoke覆盖为1/85，不称85题成绩。

两模型分别通过smoke、全85题preflight通过后，在对应空matrix目录按顺序运行：

```bash
.venv/bin/r2sp evaluate --experiment skillsbench --runtime docker --config "$SB_CFG" --no-skill --run-dir "$SB_RUN"
.venv/bin/python "$SB_CODE/scripts/launch_matrix.py" --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_RUN" --token-dir "$SB_TOKEN_DIR" --accounts "$SB_ACCOUNT" --max-concurrent 2 --stagger-seconds 3 --r2sp "$PWD/.venv/bin/r2sp"
.venv/bin/r2sp report --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_RUN"
```

NoSkill在同型号、同执行器fresh测量，不创建包或反馈学习。launcher只负责各题create/evolve/evaluate，不自动补NoSkill，第一条不可省；逐版本独评由pipeline完成。资源/限流不足将并发改1，或用`r2sp run ... --run-dir "$SB_RUN"`完全串行。两模型按同一预先任务列表比较，不用成绩选子集。

### 5.1 PG凭据缺失时，只启动预定义84题

此路径使用现有`--task`和launcher的`--cells-file`选择器，不改85题配置、任务清单或报告分母。先固定排除PG的同一子集；两模型分别通过smoke后，须各自取得其余84题的整体fresh preflight通过，才能启动以下评价与学习。此处尚未实际完成84题准入，不能称84题已就绪。使用单独结果目录，PG维持null／`NOT_MEASURED`，最终仍报告已测n与成功数÷85。

```bash
SB_RUN="$SB_PACK/matrix-ready84-author-v6-001"
SB_READY_CELLS="$SB_PACK/ready-84-cells.json"
.venv/bin/python - "$SB_CFG" "$SB_READY_CELLS" <<'SUBSET'
import json, sys
from pathlib import Path
from tau_skill_evolution.spec import load_spec
spec = load_spec(Path(sys.argv[1]))
assert spec.namespace == "skillsbench.skill-evolution.v6" and len(spec.tasks) == 85
cells = [f"{task}|benign" for task in spec.tasks if task != "pg-essay-to-audiobook"]
assert len(cells) == 84
path = Path(sys.argv[2])
if path.exists():
    assert json.loads(path.read_text()) == cells, "Existing cohort differs; inspect it before running"
else:
    with path.open("x") as handle:
        handle.write(json.dumps(cells, indent=2) + "\n")
    path.chmod(0o444)
SUBSET
SB_TASK_ARGS=()
while IFS= read -r SB_READY_TASK; do
    SB_TASK_ARGS+=(--task "$SB_READY_TASK")
done < <(.venv/bin/python - "$SB_READY_CELLS" <<'TASKS'
import json, sys
from pathlib import Path
cells = json.loads(Path(sys.argv[1]).read_text())
assert len(cells) == len(set(cells)) == 84
assert all(cell.endswith("|benign") and cell != "pg-essay-to-audiobook|benign" for cell in cells)
print("\n".join(cell.removesuffix("|benign") for cell in cells))
TASKS
)
test "${#SB_TASK_ARGS[@]}" -eq 168
.venv/bin/r2sp preflight --experiment skillsbench --runtime docker --config "$SB_CFG" "${SB_TASK_ARGS[@]}" > "$SB_PACK/preflight-ready84.json"
.venv/bin/r2sp evaluate --experiment skillsbench --runtime docker --config "$SB_CFG" "${SB_TASK_ARGS[@]}" --arm benign --no-skill --run-dir "$SB_RUN"
.venv/bin/python "$SB_CODE/scripts/launch_matrix.py" --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_RUN" --cells-file "$SB_READY_CELLS" --token-dir "$SB_TOKEN_DIR" --accounts "$SB_ACCOUNT" --max-concurrent 2 --stagger-seconds 3 --r2sp "$PWD/.venv/bin/r2sp"
.venv/bin/r2sp report --experiment skillsbench --runtime docker --config "$SB_CFG" --run-dir "$SB_RUN"
```

任何剩余任务未就绪都应先解决，不再按成绩缩减这个预定义子集。该运行不是完整85题结果；未执行PG不是真实失败0，不能把报告分母改成84。

可在`tmux new -s skillsbench-gpt56-v6`或`skillsbench-opus48-v6`中运行，再Ctrl-B、D离开；它只保留终端，不自动恢复或续key。不要用忽略exit码的shell把未就绪阶段串下去。

## 6. 看结果、恢复与交回内容

| 文件/目录 | 看什么 |
|---|---|
| `matrix-author-v6-001/launcher-status.json`与`logs/` | 逐题进程、退出/鉴权停止；exit0不是utility1 |
| `report.json`、`REPORT.md` | NoSkill/S0/S1…/Final官方utility、reward、GT检查率、配对增量、覆盖/缺测 |
| `journal/identity.json` | 源码/提示/配置/数据/环境身份；不手改hash |
| cell的 base/initial/versions 与 private/author-controller 中封存的提交、测试、原生演化日志 | 原文/版本hash、实际父版本、公开轨迹/产物、suite、r15/GT/episode及停止原因 |
| `private/`及私有grader evidence引用 | 原始provider/CTRF/reward/诊断/usage，单独受限保存，不放公开交接包或模型输入 |

同一身份重跑原阶段命令会复用已完成封存；保存整个run、Journal、持续容器和Compose身份，不只复制REPORT。`NOT_SENT`可首次派发；原响应已落盘只解析；`UNKNOWN`不自动重发。原作者完整 run 会重置内部状态，因此尚未完成的学习链不支持重新调用 run 来恢复；即使容器仍在也必须停止并另开 trial。已完成结果可直接复用，不重新执行。学习容器丢失，不能用文件快照假装恢复后台进程/依赖。鉴权终止已封存的链不会因换key自动续演化。

整链重新采样必须新trial、primary/extra分开报告，不覆盖旧链或算演化收益。只补评已封存包，用原配置/源码另开评价run，不重发S0：

```bash
.venv/bin/r2sp evaluate --experiment skillsbench --runtime docker --config ORIGINAL_CONFIG --task TASK_ID --arm benign --bundles-from ORIGINAL_RUN --run-dir NEW_EMPTY_RUN
```

同事交回两套config/manifest、preflight、identity、完整机器产物、REPORT.md/report.json、launcher状态及usage；私有原始评分证据单独传递权限，不上传凭据或模型私有聊天。必报：

- **Task pass rate**：NoSkill/S0/Final官方reward==1题数÷85，另报实测n、覆盖率和缺测原因。
- **GT test pass rate**：实际官方检查passed/total；无检查报告则null，不由reward反造检查数。
- **Surrogate pass rate**：公开suite实际通过用例/收集用例；同suite才比较，升级后不把分母变化当改善。
- **每题轨迹**：全部实际S内容版本的utility/reward/GT、相邻增量、NoSkill→S0和S0→Final配对救回/退化数；不补造早停的S1–S15。
- **作者选择与成本**：历史best、真实post-final、作者终态展示、独评分别报；r15干预、正常GT、cap/post GT、设施错误、有效episode、物理POST、修订尝试、unique内容及submit/terminal各自计数，不合并成“演化轮数”。金额没有账单/报价时未测。

S编号按包内容hash去重；A→B→A仅两个内容版本，但最终实际父版本指向B。invalid/unchanged不是新增独立内容，仍记录真实操作；缺测null不是实测失败0。相邻版本的增量只在同题双方均实测且GT单位/来源一致时计算。独立模型采样可能退化，不以“utility必须提升”替代机制验收。SkillsBench不报银行ASR或Action Recall。

## 7. 本次五题实际结果与限制

以下每格为 **官方 reward；GT通过项/总项**，均来自独立 fresh 评估。官方逐项单位为 `reporter_group`，不是Python断言条数。`—`表示没有产生该内容版本，不补造S3–S15。Final与已有内容相同，复用对应独评，不另算一个样本。

| 任务 | NoSkill | S0 | S1 | S2 | Final |
|---|---|---|---|---|---|
| dialogue-parser | 0.833；5/6 | 1；6/6 | 1；6/6 | — | S1：1；6/6 |
| 3d-scan-calc | 1；2/2 | 0；0/2 | 1；2/2 | — | S1：1；2/2 |
| adaptive-cruise-control | 0；10/12 | 0；5/12 | 0；5/12 | 1；12/12 | S2：1；12/12 |
| dapt-intrusion-detection | 0；3/14 | 0；9/14 | 0；9/14 | 0；12/14 | S1：0；9/14 |
| pddl-tpp-planning | 0；1/2 | 1；2/2 | 1；2/2 | — | S1：1；2/2 |

五题Task pass为NoSkill **1/5**、S0 **2/5**、Final **4/5**；平均reward为0.3666、0.4、0.8。创建阶段救回Dialogue/PDDL、损害3D，净增20个百分点；S0→Final救回3D/ACC、没有完整成功退化，净增40个百分点。3D的演化恢复了S0失败，但没有超过其已成功的NoSkill。Dialogue/PDDL的S0本就成功，本次没有额外官方效用收益。每题仅一次独评，尚不能排除采样波动或建立统计显著性。

| 任务 | 原生r / 正常K / 有效episode | 实际学习GT | Surrogate：suite版本、hash前缀与用例计数 |
|---|---|---|---|
| dialogue-parser | 1 / 1 / 26 | normal：1，6/6 | V1 `e0a5c480`：415/415 |
| 3d-scan-calc | 0 / 1 / 25 | normal：1，2/2 | V1 `51c98369`：3/3 |
| adaptive-cruise-control | 0 / 2 / 41 | S1 normal：0，5/12；S2 normal：1，12/12 | V1 `8884a586`：69/69；V2 `c7ee1a66`：36/36 |
| dapt-intrusion-detection | 1 / 1 / 47 | S1 normal：0，11/14；S1 post-final：0，11/14 | V1 `9f6df6ce`：40/40；V2 `9fa1d7c0`：37/39 |
| pddl-tpp-planning | 0 / 1 / 23 | normal：1，2/2 | V1 `1704d78a`：11/11 |

这些公开测试各自为实际收集的pytest用例。同suite重复观测才能计算公开进步；ACC和DAPT的V1/V2是不同suite，不能将69→36或40→37直接解释为退化。公开测试全通过仍可能与官方评分不一致：ACC的S1公开69/69、fresh官方5/12，DAPT的S1公开40/40、学习官方11/14。已核对其学习与fresh交付物共有文件hash一致，不能把不一致自动归因于封包丢失。缺少能确定具体隐藏失败原因的证据，保留公开规范/测试覆盖的歧义，不向学习模型注入隐藏答案。

DAPT同一S1包在学习GT为11/14、独评为9/14；事后核对PCAP、模板及数值统计不变，而该包允许qualitative flags覆盖，fresh agent把`has_port_scan`由false改为true、`is_traffic_benign`由true改为false。差异与fresh执行对公开旗标的解释一致，不是已发现的包或输入丢失；仍不据此断言具体隐藏检查的失败原因。 公开文件与参数核对见 [同包fresh差异](codex-author-fix-20261008-004/evidence/dapt-fresh-execution-public-comparison.json)。

DAPT在Generator请求**派发前**触发本地上下文β准入，不是费用/输出额度，也不是provider实际拒绝。最后一次已观测窗口为258,400 tokens，β=0.7、预留32,768；该操作为 `NOT_SENT`，51次请求尝试、50个完成响应、47个有效episode。原作者 `token_budget` 分支完成schema、best回滚和真实post-final，之后S0/S1/S2全部独评。它按学习阶段有效官方reward选择较早的S1（reward0），不能因事后S2独评12/14而改选S2。**历史best0、真实post-final0（11/14）、Final独评0（9/14）分别保留**。这是完整测量的任务失败，不是UNKNOWN；没有重发未派发的Generator请求来绕过context合同。

004的3D实际问题是S0要求先澄清未声明的坐标单位，fresh执行因此没有生成 `mass_report.json`。S1将条件化单位约定及交付流程写入包，`measure.py`未变，官方恢复2/2；不能套用003的Markdown解析诊断。事后公开分析、封包hash、测试suite和选包来源见 [完整机器汇总](codex-author-fix-20261008-004/public-summary.json)及该目录的审批后公共证据。测试/评分/原始会话仍分区保存，不公开模型推理或隐藏断言。

本次完成664个可观察模型响应，provider累计input为22,457,864、output为553,281、cached input为17,400,832 tokens；这些是累计用量，不能当上下文占用或收费账单。底层HTTP不可观察、订阅金额未测。源码包提供复跑代码；它不提供85题环境准入、两套Bedrock型号兼容性或完整矩阵的实测成绩。
