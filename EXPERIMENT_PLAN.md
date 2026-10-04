# 实验计划

当前方法与参数见[PROTOCOL](experiments/tau-knowledge/skill-evolution/PROTOCOL.md)。

- [τ97题×三条件交接](experiments/tau-knowledge/skill-evolution/runs/tau-full-97-20261004-001/HANDOFF.md)
- [SkillsBench85题共享资料池交接](experiments/tau-knowledge/skill-evolution/runs/skillsbench-pooled-85-20261004-001/HANDOFF.md)

截至2026-10-04，两套完整矩阵均未启动，正式Docker仍未就绪；τ的新`task_019` smoke尚未执行。

SkillsBench首个`smoke/`完成24次Analyzer调用、18次搜索，冻结1块/293 tokens，以`budget_exhausted_incomplete`停止收集。停止由下一轮输入估计116849超过114688上下文上限触发，并非搜索30次用完或找不到背景资料。Generator只调用一次，已完成响应带多余JSON结尾，解析失败，创建终止；没有Skill包，后续阶段均为`NOT_MEASURED`，不能称演化跑通。

随后真实GPT-5.5结构化输出探针返回HTTP200和`ready=true`，用量52 tokens；这是格式能力检查，不是S0或任务成绩。当前仅Generator启用strict JSON schema，SkillsBench公开轨迹只保留状态和产物。新`smoke-002/`在新身份下只复用校验通过的同一FrozenBase，不继承旧Generator请求或评分；新一次S0已完成整个执行、公开验证、fresh oracle与独立评价。Surrogate经一次测试程序修复后2/2通过，Skill修订0次，oracle一次通过并早停；独立官方reward=1、utility=true、检查2/2。这是复用已冻结资料的完整后续链，不是第二次独立资料收集，也不能证明Skill演化增益。

最新本机`make check`为547通过/12跳过；干净分发检查535通过/24跳过，lint、71文件格式、编译与两域配置均通过，日志见父目录`PUBLISH_FRESH_CHECK.log`。数据/rootfs相关集成显式跳过，Docker实际集成未验证。测试、检索探针和结构化输出探针均不替代模型任务成绩。

GitHub交付新pipeline及两个父目录的公开配置、清单、hash、验收记录和汇总，排除凭据、原始数据、rootfs、原始journal与私有评分。**公开快照不是可恢复checkpoint**；同事按HANDOFF准备本地环境，并从新空运行目录开始。当前运行身份与源码hash由各父目录的`SOURCE_HASHES.json`另行封存。
