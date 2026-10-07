# SkillsBench trial report

<!-- trajectory-metrics:start -->

## NoSkill 与逐内容版本轨迹

本次试跑固定分母 10，官方全集分母 85，两者分开报告。S 编号为实际封存的不同内容版本；修订尝试单列。Final 复用所选内容的独立评价，不追加评价。未测保留 NOT_MEASURED，早停不补造后续版本。

GT 按官方 reporter_group 计数；Surrogate 按 pytest 测试用例计数。不同 test_hash 的通过率不直接算进步。单次 fresh 评价的差值是观察结果，尚不是重复采样或因果证明。
表中 rate 展示百分比、Δrate 展示百分点；JSON 保留 0–1 原值。reward 与 Δreward 使用 0–1 单位。S0 的上一项是 NoSkill；Final 是内容别名，所以不新增上一轮差值。
汇总中的固定分母比例表示已观察成功数/固定分母，部分观测不能当完整结果；已测数为 0 时比例保持 NOT_MEASURED。

| 版本 | 实际内容/任务数 | 已测 | 已观察成功数 | 已观察成功数/试跑固定分母 | 已测任务 pass rate | 已观察成功数/全集85（仅部分观测） |
| --- | --- | --- | --- | --- | --- | --- |
| NoSkill | 10 | 10 | 4 | 4/10 (40.0%) | 40.0% | 4/85 (4.7%) |
| S0 | 7 | 7 | 3 | 3/10 (30.0%) | 42.9% | 3/85 (3.5%) |
| S1 | 3 | 3 | 1 | 1/10 (10.0%) | 33.3% | 1/85 (1.2%) |
| S2 | 2 | 2 | 1 | 1/10 (10.0%) | 50.0% | 1/85 (1.2%) |
| S3 | 1 | 0 | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| S4 | 1 | 0 | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| S5 | 1 | 0 | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| Final | 7 | 6 | 4 | 4/10 (40.0%) | 66.7% | 4/85 (4.7%) |

### 配对变化：创建与修订分开

NoSkill→S0 表示创建 Skill 后的观察收益；S0→Final 表示后续修订的观察收益。只统计两边实测且 executor、GT 来源/单位/总数一致的同题，缺配对不硬算。Final=S0 复用同一评价，差值严格为零，不算新增演化成功。

| 对照 | paired_n | 完整成功提升数 | 完整成功退化数 | Δmean reward | Δmean GT | 同内容复用数 |
| --- | --- | --- | --- | --- | --- | --- |
| NoSkill→S0 | 7 | 2 | 1 | +0.048 | +2.3 个百分点 | 0 |
| S0→Final | 6 | 1 | 0 | +0.167 | +16.1 个百分点 | 4 |

| 任务 | 版本 | attempt | Task pass（0/1） | reward | GT passed/total | GT rate | ΔTask pass vs NoSkill | Δreward vs NoSkill | Δreward vs S0 | Δreward vs 上一内容 | ΔGT vs 上一内容 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | NoSkill | NOT_MEASURED | 0 | 0.667 | 4/6 (reporter_group) | 66.7% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dialogue-parser | S0 | NOT_MEASURED | 1 | 1.000 | 6/6 (reporter_group) | 100.0% | +1.000 | +0.333 | +0.000 | +0.333 | +33.3 个百分点 |
| dialogue-parser | Final = S0 | NOT_MEASURED | 1 | 1.000 | 6/6 (reporter_group) | 100.0% | +1.000 | +0.333 | +0.000 | NOT_MEASURED | NOT_MEASURED |
| manufacturing-codebook-normalization | NoSkill | NOT_MEASURED | 0 | 0.000 | 15/16 (reporter_group) | 93.8% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| manufacturing-codebook-normalization | S0 | NOT_MEASURED | 0 | 0.000 | 14/16 (reporter_group) | 87.5% | +0.000 | +0.000 | +0.000 | +0.000 | -6.2 个百分点 |
| manufacturing-codebook-normalization | Final = S0 | NOT_MEASURED | 0 | 0.000 | 14/16 (reporter_group) | 87.5% | +0.000 | +0.000 | +0.000 | NOT_MEASURED | NOT_MEASURED |
| lab-unit-harmonization | NoSkill | NOT_MEASURED | 0 | 0.542 | 26/48 (reporter_group) | 54.2% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| lab-unit-harmonization | Final | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| adaptive-cruise-control | NoSkill | NOT_MEASURED | 1 | 1.000 | 12/12 (reporter_group) | 100.0% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| adaptive-cruise-control | Final | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | NoSkill | NOT_MEASURED | 0 | 0.000 | 8/14 (reporter_group) | 57.1% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | S0 | NOT_MEASURED | 0 | 0.000 | 13/14 (reporter_group) | 92.9% | +0.000 | +0.000 | +0.000 | +0.000 | +35.7 个百分点 |
| dapt-intrusion-detection | S1 | 1 | 0 | 0.000 | 13/14 (reporter_group) | 92.9% | +0.000 | +0.000 | +0.000 | +0.000 | +0.0 个百分点 |
| dapt-intrusion-detection | S2 | 2 | 0 | 0.000 | 11/14 (reporter_group) | 78.6% | +0.000 | +0.000 | +0.000 | +0.000 | -14.3 个百分点 |
| dapt-intrusion-detection | S3 | 3 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | S4 | 4 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | S5 | 6 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | Final = S5 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| court-form-filling | NoSkill | NOT_MEASURED | 0 | 0.000 | 4/5 (reporter_group) | 80.0% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| court-form-filling | S0 | NOT_MEASURED | 0 | 0.000 | 0/5 (reporter_group) | 0.0% | +0.000 | +0.000 | +0.000 | +0.000 | -80.0 个百分点 |
| court-form-filling | S1 | 1 | 0 | 0.000 | 4/5 (reporter_group) | 80.0% | +0.000 | +0.000 | +0.000 | +0.000 | +80.0 个百分点 |
| court-form-filling | Final = S1 | NOT_MEASURED | 0 | 0.000 | 4/5 (reporter_group) | 80.0% | +0.000 | +0.000 | +0.000 | NOT_MEASURED | NOT_MEASURED |
| paper-anonymizer | NoSkill | NOT_MEASURED | 1 | 1.000 | 6/6 (reporter_group) | 100.0% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| paper-anonymizer | S0 | NOT_MEASURED | 0 | 0.000 | 5/6 (reporter_group) | 83.3% | -1.000 | -1.000 | +0.000 | -1.000 | -16.7 个百分点 |
| paper-anonymizer | S1 | 1 | 1 | 1.000 | 6/6 (reporter_group) | 100.0% | +0.000 | +0.000 | +1.000 | +1.000 | +16.7 个百分点 |
| paper-anonymizer | S2 | 4 | 1 | 1.000 | 6/6 (reporter_group) | 100.0% | +0.000 | +0.000 | +1.000 | +0.000 | +0.0 个百分点 |
| paper-anonymizer | Final = S2 | NOT_MEASURED | 1 | 1.000 | 6/6 (reporter_group) | 100.0% | +0.000 | +0.000 | +1.000 | NOT_MEASURED | NOT_MEASURED |
| econ-detrending-correlation | NoSkill | NOT_MEASURED | 1 | 1.000 | 4/4 (reporter_group) | 100.0% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| econ-detrending-correlation | S0 | NOT_MEASURED | 1 | 1.000 | 4/4 (reporter_group) | 100.0% | +0.000 | +0.000 | +0.000 | +0.000 | +0.0 个百分点 |
| econ-detrending-correlation | Final = S0 | NOT_MEASURED | 1 | 1.000 | 4/4 (reporter_group) | 100.0% | +0.000 | +0.000 | +0.000 | NOT_MEASURED | NOT_MEASURED |
| xlsx-recover-data | NoSkill | NOT_MEASURED | 1 | 1.000 | 8/8 (reporter_group) | 100.0% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| xlsx-recover-data | Final | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| pddl-tpp-planning | NoSkill | NOT_MEASURED | 0 | 0.000 | 1/2 (reporter_group) | 50.0% | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| pddl-tpp-planning | S0 | NOT_MEASURED | 1 | 1.000 | 2/2 (reporter_group) | 100.0% | +1.000 | +1.000 | +0.000 | +1.000 | +50.0 个百分点 |
| pddl-tpp-planning | Final = S0 | NOT_MEASURED | 1 | 1.000 | 2/2 (reporter_group) | 100.0% | +1.000 | +1.000 | +0.000 | NOT_MEASURED | NOT_MEASURED |

### 修订尝试和停止

| 任务 | 内容版本数 | 修订attempts | Oracle有效调用 | learning executions | 提交数 | 停止原因 |
| --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | 1 | 0 | 1 | 1 | 1 | oracle_success |
| manufacturing-codebook-normalization | 1 | 0 | 0 | 1 | 0 | generator_turn_budget_exhausted |
| lab-unit-harmonization | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | generation_result_unknown |
| adaptive-cruise-control | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | generation_result_unknown |
| dapt-intrusion-detection | 6 | 6 | 1 | 1 | 6 | 演化：context_budget_exhausted；运行：authentication_failed |
| court-form-filling | 2 | 2 | 3 | 1 | 2 | generator_context_budget_exhausted |
| paper-anonymizer | 3 | 5 | 0 | 1 | 5 | generator_context_budget_exhausted |
| econ-detrending-correlation | 1 | 0 | 1 | 1 | 1 | oracle_success |
| xlsx-recover-data | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | generation_result_unknown |
| pddl-tpp-planning | 1 | 0 | 1 | 1 | 1 | oracle_success |

| 任务 | attempt | 状态 | 内容hash | 父包hash | 失败类别 |
| --- | --- | --- | --- | --- | --- |
| dapt-intrusion-detection | 1 | changed | e84a7fa2f9d1 | 7eaeb92e0487 | NOT_MEASURED |
| dapt-intrusion-detection | 2 | changed | 5f7347ef03c7 | e84a7fa2f9d1 | NOT_MEASURED |
| dapt-intrusion-detection | 3 | changed | 83e64a5d2c37 | 5f7347ef03c7 | NOT_MEASURED |
| dapt-intrusion-detection | 4 | changed | c7eb29373d61 | 83e64a5d2c37 | NOT_MEASURED |
| dapt-intrusion-detection | 5 | invalid | NOT_MEASURED | c7eb29373d61 | RevisionFailure |
| dapt-intrusion-detection | 6 | changed | f1f9867e50fe | c7eb29373d61 | NOT_MEASURED |
| court-form-filling | 1 | changed | 498293c3f1c6 | a975f90ba0ce | NOT_MEASURED |
| court-form-filling | 2 | invalid | NOT_MEASURED | 498293c3f1c6 | RevisionFailure |
| paper-anonymizer | 1 | changed | 6d1673f49cd0 | 222053ca4470 | NOT_MEASURED |
| paper-anonymizer | 2 | unchanged | 6d1673f49cd0 | 6d1673f49cd0 | NOT_MEASURED |
| paper-anonymizer | 3 | unchanged | 6d1673f49cd0 | 6d1673f49cd0 | NOT_MEASURED |
| paper-anonymizer | 4 | changed | 7e26d31030a7 | 6d1673f49cd0 | NOT_MEASURED |
| paper-anonymizer | 5 | invalid | NOT_MEASURED | 7e26d31030a7 | RevisionFailure |

### 同 suite 的公开验证

| 任务 | 内容 | execution | suite/hash | passed/total | rate | Δvs 同 suite 前次 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | S0 | a4b9a3dbdc064756ba3c0a30d494346b | T0/c6e85035cf11 | 6/6 | 100.0% | NOT_MEASURED | MEASURED |
| dapt-intrusion-detection | S0 | 94bcb727fbe04293902d8d1c25a2a088 | T0/2a28aafc0f94 | 35/35 | 100.0% | NOT_MEASURED | MEASURED |
| dapt-intrusion-detection | S0 | 94bcb727fbe04293902d8d1c25a2a088 | T1/0a823a9f0c65 | 34/36 | 94.4% | NOT_MEASURED | MEASURED |
| dapt-intrusion-detection | S1 | 94bcb727fbe04293902d8d1c25a2a088 | T1/0a823a9f0c65 | 32/36 | 88.9% | -5.6 个百分点 | MEASURED |
| dapt-intrusion-detection | S2 | 94bcb727fbe04293902d8d1c25a2a088 | T1/0a823a9f0c65 | 31/36 | 86.1% | -2.8 个百分点 | MEASURED |
| dapt-intrusion-detection | S3 | 94bcb727fbe04293902d8d1c25a2a088 | T1/0a823a9f0c65 | 31/36 | 86.1% | +0.0 个百分点 | MEASURED |
| dapt-intrusion-detection | S4 | 94bcb727fbe04293902d8d1c25a2a088 | T1/0a823a9f0c65 | 32/36 | 88.9% | +2.8 个百分点 | MEASURED |
| dapt-intrusion-detection | S4 | 94bcb727fbe04293902d8d1c25a2a088 | T1/0a823a9f0c65 | 32/36 | 88.9% | +0.0 个百分点 | MEASURED |
| dapt-intrusion-detection | S5 | 94bcb727fbe04293902d8d1c25a2a088 | T1/0a823a9f0c65 | 31/36 | 86.1% | -2.8 个百分点 | MEASURED |
| court-form-filling | S0 | 4df29c2c56424c32a59c7ed3e0c059a8 | T0/f06b2705fe3c | 4/4 | 100.0% | NOT_MEASURED | MEASURED |
| court-form-filling | S0 | 4df29c2c56424c32a59c7ed3e0c059a8 | T1/3d3ffc11b62f | 5/5 | 100.0% | NOT_MEASURED | MEASURED |
| court-form-filling | S0 | 4df29c2c56424c32a59c7ed3e0c059a8 | T2/32937e0ae78f | 6/6 | 100.0% | NOT_MEASURED | MEASURED |
| court-form-filling | S0 | 4df29c2c56424c32a59c7ed3e0c059a8 | T3/7325a77ed575 | 6/7 | 85.7% | NOT_MEASURED | MEASURED |
| court-form-filling | S1 | 4df29c2c56424c32a59c7ed3e0c059a8 | T3/7325a77ed575 | 5/7 | 71.4% | -14.3 个百分点 | MEASURED |
| paper-anonymizer | S0 | b6c3802cabe644c694750695ef4f393c | T0/14ae9b161e3f | 2/3 | 66.7% | NOT_MEASURED | MEASURED |
| paper-anonymizer | S1 | b6c3802cabe644c694750695ef4f393c | T0/14ae9b161e3f | 2/3 | 66.7% | +0.0 个百分点 | MEASURED |
| paper-anonymizer | S1 | b6c3802cabe644c694750695ef4f393c | T0/14ae9b161e3f | 2/3 | 66.7% | +0.0 个百分点 | MEASURED |
| paper-anonymizer | S1 | b6c3802cabe644c694750695ef4f393c | T0/14ae9b161e3f | 2/3 | 66.7% | +0.0 个百分点 | MEASURED |
| paper-anonymizer | S2 | b6c3802cabe644c694750695ef4f393c | T0/14ae9b161e3f | 2/3 | 66.7% | +0.0 个百分点 | MEASURED |
| econ-detrending-correlation | S0 | e5c5f4ec917a40649e4af27b82433615 | T0/d09c52572571 | 2/2 | 100.0% | NOT_MEASURED | MEASURED |
| pddl-tpp-planning | S0 | ab2f82b820da46bfa8d2227f8ce35c39 | T0/a0f789bfeb2d | 3/3 | 100.0% | NOT_MEASURED | MEASURED |

完整包/父包 hash、尝试、停止原因、用量和所有检查记录见 trajectory-metrics.json。

<!-- trajectory-metrics:end -->

## 本次结果与待解决问题

本次已结束，状态为 `PARTIAL`：NoSkill 十题全部实测，七题创建出 S0，封存十五个不同内容版本，其中十二个完成独立评分。NoSkill 成功 4/10，S0 成功 3/7，Final 实测成功 4/6。覆盖不同，三个比例不能直接连成整体进步曲线；另外三题没有可封存的 S0，DAPT 的 Final 尚未测得。

创建带来的完整成功出现在 Dialogue 和 PDDL。修订带来的完整成功出现在 Paper：S0 的 5/6 修到 S1、S2 的 6/6，但 NoSkill 本身也是 6/6，因此这是修复 S0 的退化。Court 的 0/5 修到 4/5，恢复 NoSkill 的部分完成程度，仍未完全成功。DAPT 的 13/14→13/14→11/14 是实测退化；S3–S5 的独立成绩不能推断。各版本是一次 fresh 执行的观察值，尚不能据此证明稳定的因果收益。

Paper 的五次公开检查均为 2/3；四次修订提交中的三份 PDF 文件 hash 分别一直相同。失败项检查 acknowledgements 中的姓名残留，有公开要求支持。学习环境产物没有变化，而 fresh 执行改进后的包取得更好成绩；这是两个执行对象的差异，不能直接称 Verifier 假负，也不能仅凭 hash 断言没有重新执行。Manufacturing 的首次学习执行耗尽 120 轮仍未提交，虽然有终端执行活动，但没有进入修订或 oracle。

Lab、ACC、XLSX 的单次 S0 请求均在既定 900 秒时限后成为 `UNKNOWN`，未重发。Paper、Court、DAPT 的学习阶段在真实上下文边界停止。随后 Bedrock HTTP 401 阻断 DAPT 的 S3–S5 独立评分；学习停止与鉴权停止分别记录。不能把这些未测阶段当作实测零分。

已收到响应的用量为 1,125 次请求、35,339,523 input tokens、1,293,728 output tokens，其中 28,284,276 input tokens 为 provider 标记的 cache 命中。三个未知请求可能另有计费，用量未测；provider 未提供账单金额，费用保持 `NOT_MEASURED`。完整证据路径、公共产物 hash、配对统计和恢复规则见 [observations.json](observations.json)；完整 85 题交接见 [HANDOFF.md](../HANDOFF.md)。

公开回归的进一步定位：DAPT 的 S1 将 IPv4 协议计数的排除条件复用于端口统计，端口熵与唯一源/目的端口数四项新增失败；S2 保留此条件。同一学习 execution、固定 T1 为 34/36→32/36→31/36。S2 另因按服务流识别 beacon 撞上 Verifier 的全局 CV 约束，这项存在公开规范解释分歧。官方评分只留汇总、未封存原 CTRF 逐项结果，因此不能将这些公开失败直接当作官方新增两组失败的已证实根因。后续矩阵需要补齐私有逐项评分证据。审阅没有回流学习侧，原评分保持不变。
