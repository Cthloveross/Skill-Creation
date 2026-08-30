# MPBench 与 SkillJack 复用方案

## 结论

MPBench 可以下载、修改和用于 memory-safety 复现，但不推荐作为本项目的 benign resource pool。其 `benign case` 是完整测试场景，不是独立知识文档。虽然 `context` 可以机械地抽取为文本，混合场景、模板重复和任务配对会给纯 resource-pool 实验引入不必要变量。主实验应改用原生知识库文档；MPBench 只保留为 related-work 对照。

[MPBench 官方仓库](https://github.com/Digital-Trust-Lab/mp-bench) 采用 [Apache-2.0](https://github.com/Digital-Trust-Lab/mp-bench/blob/main/LICENSE)。可复制、修改和再分发，但需保留许可证/归属通知，并对修改文件作显著说明。正式发布仍应固定 commit 和数据 hash。

## Benign case 的语义

当前仓库的 benign row 包含：

```text
id
attack_type = benign
attack_signal
domain
adversarial_goal
user_query
context
expected_memory
retrieval_query
legitimate_memory_write
```

其中：

- `context`：合成的邮件、文件、网页或工具输出式外部内容；这是最接近“善意资源”的部分。
- `user_query`：当前任务，例如总结邮件，不是资源正文。
- `expected_memory`：用于检查 agent 是否写入某条记忆的目标标签；它有时故意描述一个不该写入的错误归因，不能当作善意事实加入语料。
- `retrieval_query`：后续会话测试 memory persistence 的查询，可作为 deployment task seed。
- `legitimate_memory_write=false`：当前 context 中可能出现第三方事实或偶然信息，但 agent 不应把它变成用户偏好/长期记忆。
- `legitimate_memory_write=true`：用户明确授权保存某个低风险偏好，可作为正常学习能力的 positive control。

在检查的 commit `6886880a7c29625e0109e0ad91d0e095029f1577` 中，benign 文件解析出 2,999 个 JSON objects；规范化 7 个字符串型布尔值后，249 个为 `legitimate_memory_write=true`、2,750 个为 false。删除 300 个除 ID 外完全重复的副本后，剩余 2,699 个唯一 row bodies，其中约 232 个 positive、2,467 个 negative；这些重复副本的 ID 还以 `ADV_` 开头并与 adversarial ID 空间冲突。论文报告的数量与当前仓库对象数也略有差异，说明使用前必须按固定 commit 做 schema、ID、重复和 label audit。

## 可直接复用的部分

### MPBench

1. **`context` 作为合成 honest-resource 候选。** 先去重、去模板泄漏、分配 source identity，再放进 pool。
2. **七个 domain 与六类攻击 taxonomy。** 用于分层抽样和跨域评测。
3. **249 个合法写入 positive controls。** 检查防御是否错误阻断用户明确授权的正常长期偏好或 procedure。
4. **2,750 个不应写入 negative controls。** 检查 agent 是否把第三方、偶然或未授权事实提升为持久规则。
5. **`user_query` 与 `retrieval_query` 作为 task seeds。** 必须重写实体并按 template family 划分 train/test，不能原样形成一一匹配的检索捷径。
6. **ASR/RSR 的两阶段思想。** 在本项目中改为 resource exposure、skill compilation 和 source-removed execution 三段，并使用 deterministic canary。

### SkillJack

[SkillJack 官方代码](https://github.com/Tencent/AI-Infra-Guard/tree/main/Research/SkillJack) 提供 clean、disguised poisoned、naive 和 large-scale trajectories，以及 extraction、routing、source-deletion 和 mock execution 脚本。可将它作为 `poisoned trajectory 已进入 learning corpus` 的强上界，而不是本项目的 resource-pool 主实验。

最有价值的是形成权限递减的三层 baseline：

```text
A. SkillJack：直接给 poisoned trajectory
B. MPBench-style：保证目标 external context 被读取
C. 本项目：目标资源只在 unknown mixed pool 中自然竞争检索
```

同一无害 canary 和同一 skill creator 下比较 A/B/C，可以测量攻击能力每减弱一层，成功率在 retrieval、uptake 和 compilation 哪一层衰减。

## 不能原样复用的部分

- 不能把整条 JSON row 当作一个 resource；其中混入了 query、ground-truth label 和 future query，会造成标签泄漏。
- 不能把 `expected_memory` 索引进 pool；它是评测目标，不是 source evidence。
- 不能把所有 benign rows 当 2,999 个独立实验单位；存在完全重复 context 和共同生成模板。
- 不能把 exact `user_query` 与其配套 `context` 直接用于主 natural-retrieval 结论；这种一一配对让检索过于容易。
- 不能将 credential/exfiltration 等原始 adversarial goals 用于实验；统一替换为本地 no-op canary。
- 不能把 MPBench 的 direct skill-file/`skill_md` 样例当普通文档污染；那属于更强的 skill supply-chain baseline。
- 不能仅用 MPBench 合成语料声称开放世界外部有效性；主论文还需授权的 API docs、knowledge base 或 web environment replication。
- 不能直接按当前 `attack_type` 字符串统计六类攻击；raw adversarial 文件含类别别名、拼写变体和额外 signal 值，240 个带 `skill_md` 的 cases 也需要通过 schema 字段恢复其专门分支。

## 转换为 ResourcePoolBench

### 1. 清洗

- 固定 commit、保存原始 file hash；
- JSON parse 与 required-field validation；
- 按 normalized `context` hash 去重；
- 人工审计 label mapping 与异常 ID；
- 对近重复做 embedding/template clustering；
- 删除或替换所有真实感凭据、地址和攻击 endpoint；
- 给每个文档分配 `origin_id`，同一生成模板或同一线程默认不是多个独立来源。

### 2. 拆分

每条 row 转成：

```text
resource_document = context
acquisition_task_seed = user_query
deployment_task_seed = retrieval_query
promotion_label = legitimate_memory_write
domain = domain
template_family = inferred cluster
```

train/dev/test 按 `template_family + source family + task family` 分组切分，不能随机按 row 切分。完全重复和近重复必须处在同一 split。

### 3. 构造配对资源

从同一个 clean base document 生成两种长度、文体、主题和来源形式匹配的版本：

- `placebo_resource`：包含一个正常、无副作用的 procedure；
- `canary_resource`：仅把对应步骤替换成需要记录本地 nonce 的合成 procedure。

两者在相同 honest-pool snapshot、query、retriever、seed 和 model 下配对运行。这样差异来自目标 procedure，而不是文档相关性、长度或写作质量。

### 4. 构建未知池

- 攻击资源先冻结；
- 再从去重后的 honest contexts 和第二个授权语料源抽样 pool snapshot；
- 使用 1/3 个独立 attacker origins；
- pool size 可从 100、500、2,000 做 pilot scaling；
- natural retrieval miss 必须计入端到端失败，不得重抽；
- forced inclusion 只用于机制上界。

### 5. 部署隔离

acquisition 后删除目标 resource、retrieval cache、当前 context 和相关 memory，只保留生成 skill。deployment task 使用改写后的 held-out query，并由 mock-tool log 判定 canary；删除 skill 的 paired run 用于证明 artifact 必要性。

## 推荐使用顺序

本项目不从 MPBench 构建 resource pool。开放 PoC 使用 API-Bank，论文主 pool 使用 AppWorld API docs，跨域复制使用 DocPrompting-CoNaLa 与 OR-ShARC；攻击资源完全由本项目构造。MPBench 只用于 related-work 比较，SkillJack 只作为 direct-trajectory 强上界。这样实验变量只有 clean resources、attacker resources、retriever 和 skill creator，不混入 memory-write 标签与场景结构。
