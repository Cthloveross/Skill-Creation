# Retrieval 与 Skill Evolution

当前维护共享模型、封存与评估接口，以及银行、SkillsBench两个任务适配器：**只读观察与检索 → 冻结 B* → 一次创建 S0 → Generator直接执行与修改 → 独立验证 → fresh oracle / 独立评估**。方法为 `tau.skill-evolution.v4`（M15/K5）和 `skillsbench.skill-evolution.v7`（自主发现输入、直接作者控制器、r15/正常K5），默认 GPT-5.4、Docker；创建禁止执行、自测和重发。API创建最多一次HTTP POST；Codex订阅诊断只可确认一次创建turn，底层HTTP不可观察。

| 实验 | 完整规模 | 当前配置 | 交接 |
|---|---|---|---|
| τ-Knowledge | 97题 × benign/5%/10%，291链 | [experiment.yaml](configs/experiment.yaml) | [τ HANDOFF](runs/tau/HANDOFF.md) |
| SkillsBench | 85题，benign | [skillsbench.yaml](configs/skillsbench.yaml) | [SkillsBench HANDOFF](runs/skillsbench/HANDOFF.md) |

SkillsBench共享池仅合并85题背景资料（122块）；Analyzer接收原始instruction、工作目录和授权输入根，通过只读目录列举与文件读取发现当前题输入，不自动获得构建文件清单或环境配置。获取工具是原始输入的受限视图；学习阶段原文件仍在官方任务环境提供。每题独立演化Skill。学习期间由Generator操作持续任务环境；正式评分不继承学习状态，使用作者CodexSkillOnly。τ Generator直接操作银行工具及用户接口；评分仍使用官方tau2。

```text
src/tau_skill_evolution/  共享控制器、角色、两个适配器与安全原语
configs/                 当前配置与固定数据manifest
prompts/、meta/、licenses/ 实际提示与作者出处
runtime/                 依赖、镜像与逐题环境锁
scripts/、tests/          准备、运行、回归和显式集成检查
data/                    本地官方输入、私有grader、索引与环境；仅公开背景/清单分发
runs/                    两份当前交接与各版本验收
archive/                 旧运行、历史分析与归档索引
```

主要文档只读 [PROTOCOL](PROTOCOL.md) 与两份 HANDOFF；[来源记录](meta/coevo-authoring/SOURCE.md)保留作者出处。旧实验由 [归档索引](archive/index.json)集中归档，保存原始内容和旧路径映射；[HISTORY](archive/HISTORY.md)收纳历史解释，不作为运行入口。内部审计留在本地，不作为对外交接。

SkillsBench旧85题配置：[GPT-5.6 Terra](runs/skillsbench/full-85-gpt56-v6/config.yaml)与[Opus 4.8](runs/skillsbench/full-85-opus48-v6/config.yaml)及现有源码包均冻结为v6；它们不作为v7配置或checkpoint。当前方法的输入发现设置与新试跑见SkillsBench HANDOFF。2026-10-08关闭失败派发门禁的v6复验保留在 [005 readiness](runs/readiness-skillsbench-crosscheck-20261008-005/final-status.json)。[Codex订阅五题结果](runs/skillsbench/codex-author-fix-20261008-004/public-summary.json) 是此前冻结提交`4fbfeed6`、身份`0f39848a…`的完整测量：NoSkill/S0/Final Task pass为1/5、2/5、4/5，实际模型为gpt-6.1-sol；不改旧结果，也不将其冒充v7实测。全85题新身份fresh准入及两模型成绩仍未测；PG缺任务专用凭据，报告仍保留85分母。完整阶段合同见[Protocol 3.7](PROTOCOL.md#37-一条链的阶段合同)，历史五题实际流程集中在HANDOFF第7节。

```bash
make setup
make check
```

CLI统一为 `preflight / create / evolve / evaluate / report / run`，默认tau。准确环境准备和新空目录命令见HANDOFF。`evaluate --no-skill`仅执行无任务Skill对照；`--bundles-from`只导入经校验的历史安全包作fresh评分，不续接旧演化。create/evolve/evaluate/run会调用付费模型，鉴权失败停止后续任务；环境不可用时不回退host或历史workspace。

恢复必须保持源码、提示、配置、数据、运行环境和trial身份一致。已完成结果复用，UNKNOWN不重发。SkillsBench原控制器中途状态尚不可恢复，未完成链不能重新run重置计数，须另开trial；容器丢失/重启也不能靠快照冒充恢复。τ私有数据库和模拟器状态必须保留。新的源码或模型变体使用新的空run目录，旧结果及hash绑定路径只读保留。

初次v4机制验收保留在 [readiness-direct-evolution-v4-20261007-001](runs/readiness-direct-evolution-v4-20261007-001/acceptance.json)，v6复验见上方005 readiness。本地模拟provider与真实Docker检查不计模型成绩。v7的[五题GPT-5.4 API结果](runs/skillsbench/input-discovery-five-gpt54-20261008-003/public-summary.json)已完成：NoSkill/S0/Final Task pass为1/5、3/5、3/5，逐版本独评包含一次救回与一次退化；不混入两次已停止的诊断试跑。完整矩阵仍为NOT_MEASURED。
