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
