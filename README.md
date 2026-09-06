# Resource-to-Skill research

本项目研究 Agent 从资源中归纳 Skill，以及 Skill 在新任务和新上下文中的作用。当前可执行主线收敛为 **τ-Knowledge 良性 Skill 批量创建与普通任务评估**：创建和评估使用独立配置、模型身份、任务列表与输出，创建完成后不会自动评估。新 v2 使用独立 `batch_*` 模块，保留历史入口及其默认配置；旧 ASR 仅登记既有 artifact 和历史重放证据。

请从这三份文档阅读项目：

- 本页：项目定位与导航。
- [experiments/WORKFLOW.md](experiments/WORKFLOW.md)：当前配置、脚本、checkpoint、提交与重放流程。
- [experiments/RESULTS.md](experiments/RESULTS.md)：按协议版本登记历史结果与证据限制。

| 实验 | 当前定位 | 代码 |
| --- | --- | --- |
| τ-Knowledge | r8 / v2 良性创建、独立 utility 评估 | `src/r2sp_tau_knowledge/` |
| AppWorld | 保留历史实现；当前入口为离线检索边界回归 | `src/r2sp/` |
| 共享层 | 检索、协议对象、hash、指纹与隔离证明 | `src/r2sp_common/` |

官方 τ 快照包含 698 篇知识文档和 97 个任务；AppWorld 有 447 个 task-facing API resources。两个数据集的 runtime、runner 与 evaluator 独立。数据、模型、容器及运行 artifact 不随源码提交。

```bash
make check

# 只校验十项良性创建配置，不启动模型
.venv/bin/python experiments/tau-knowledge/preliminary/scripts/run_batch.py validate \
  --phase create \
  --spec experiments/tau-knowledge/preliminary/configs/generation-benign-10.example.yaml

# 默认只打印创建作业，不提交 Slurm
bash experiments/tau-knowledge/preliminary/scripts/submit_generation.sh \
  --spec experiments/tau-knowledge/preliminary/configs/generation-benign-10.example.yaml
```

本次交付范围为代码、文档和离线验证，镜像构建与模型验证已暂停。当前实测与资产就绪状态以 [结果登记](experiments/RESULTS.md) 为准，代码实现或 dry-run 成功不代表真实模型实验已完成。

研究背景保留在 [威胁模型](analysis/02_threat_model.md) 和 [研究设计](analysis/03_experiment_design.md)。这些分析描述研究问题与历史条件，不扩展当前 v2 的良性执行范围。
