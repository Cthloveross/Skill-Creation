# AppWorld × Qwen3.8 实验协议

主实验应把四个平面彻底分开：Qwen agent 负责选择和使用资源；retriever 只搜索 API 文档副本；AppWorld runtime 只执行真实 API；evaluator 只在 episode 结束后离线判分。agent 不扫描全部 457 条文档，也不能通过 MCP、原生 `ApiDocs` 或文件系统绕过实验索引。

## 可见性边界

### 四个平面

| 平面 | 可以看到 | 绝不能看到 |
|---|---|---|
| Retriever | agent 的显式查询、457 条 canonical API docs、attacker overlay | ground truth、required APIs、solution、DB、评测结果 |
| Qwen agent | system policy、task instruction、可信 app descriptions、检索结果、主动读取的全文、API observations | 完整 corpus、poison label、API 源码、任务 DB、gold calls、evaluator |
| Tool runtime | 未修改的 API implementation、初始 DB/time、合法 API 参数、Supervisor helper | poison 文档、检索分数、skill compiler、evaluation code |
| Evaluator | 初始/最终 DB、隐藏规则、completion answer 和 API logs | 不向 agent 回传逐题报告，尤其不能进入 skill compiler |

“resource-selection 时只能看 API 和 app description”需要更精确地表述：agent 一开始看到 task instruction 和全部可信 app descriptions；调用检索后只看到 top-k API-doc 标题、来源和摘要；再由 agent 主动选择少量 `resource_id` 读取全文。执行期间的 API 返回值也是可见信息，但它属于临时 environment observation，不属于 resource pool，也不由攻击者控制。

### 始终可见

每个 acquisition episode 开始时，Qwen 只得到：

1. 固定的良性 system policy；
2. 一个 AppWorld `instruction`；
3. 9 个日常 app 的官方名称和短描述；
4. 四个窄接口：`search_docs`、`read_doc`、`execute`、`finish`。

`Supervisor` 的身份、凭据查询和 `complete_task` 属于可信控制平面。agent 可以通过合法调用得到相应返回，但原始 `world.task.supervisor` 不直接塞进 prompt。

### 按需可见

`search_docs(query, app_filter, k)` 返回排序后的 resource header 和短摘要；默认 `k=10`。检索分数只写入隐藏日志，不展示给 agent，避免它把数值当成权威度。agent 随后用 `read_doc(resource_id)` 读取最多 3 条全文。这个两步接口把三个事件分开记录：poison 是否进入 top-k、agent 是否选择它、agent 是否真正使用它。

资源全文采用一种 canonical 表示，建议使用 AppWorld standard JSON 经参数压缩后的文本渲染。standard、function-calling 和 OpenAPI 是同一 API 的三种表示，不能同时索引。每条记录至少包含：

```text
resource_id, origin_id, app_name, api_name,
title, body, resource_type, content_hash
```

主实验中，app descriptions 是固定可信目录，不是可投毒资源。攻击者只能向 API-doc 索引增加 1 或 3 条带独立 `origin_id` 的 overlay，不能修改官方文档、app catalog、retriever 参数或 API implementation。若研究 app-description poisoning，必须作为独立因子另报。

## 端到端流程

### 数据准备

1. 固定 AppWorld、任务 bundle 和 API docs 的版本与 hash。
2. 从 `standard/*.json` 提取全部 API 文档，每个 `app × api` 生成一条 resource。
3. 建立 clean snapshot；poison arm 只额外合并 attacker overlay，matched-placebo arm 合并长度和主题匹配但无攻击语义的文档。
4. 主 retriever 先用确定性的 BM25；冻结后再增加 dense/hybrid robustness arm。Qwen3.8 是 agent/skill compiler，不兼任 retriever。
5. 用 train 中的隐藏 `required_apps/apis` 离线建立 authoring/deployment 候选对，但这些标签永不进入 agent 输入。开发只看 train；超参数在 clean-only 数据上冻结后才运行 poison comparison。

### Acquisition episode

```text
task instruction + trusted app catalog
                 ↓
Qwen 生成 search query
                 ↓
BM25 在 457 clean docs (+ 0/1/3 overlay) 中返回 top-10
                 ↓
Qwen 主动 read 最多 3 条全文
                 ↓
Qwen 通过窄 execute/call gateway 操作原始 AppWorld runtime
                 ↓
API observations 回到同一 episode，继续检索或执行
                 ↓
Qwen 调用 finish / supervisor.complete_task
                 ↓
episode 关闭后，隐藏 evaluator 离线检查最终 DB 与 collateral damage
```

不要把 457 个 API 作为 function schemas 一次性注册给 Qwen；这会让模型绕过检索。也不要给它完整 AppWorld MCP 的 `list_tools()`。原生 `ApiDocs` helper 必须禁用或完全重定向到同一个实验索引，否则 agent 可以取回 pristine docs。执行层推荐使用容器中的窄 gateway；若 PoC 先用 `world.execute`，应保持两项 safety guard 开启、禁止文件和对象 introspection，并规范化可能泄露参数或 schema 的异常信息。

“只允许调用已检索 API”不适合作为主设置，因为它会把文档投毒与工具可用性 gating 混在一起。runtime 应允许调用任何合法 API 名称，但不主动泄露未检索 schema；top-k tool gating 可以另做 ablation。

### Skill compilation

只有完成 acquisition 后才调用一个全新的 Qwen3.8 compiler context。compiler 的 allow-list 输入为：task instruction、agent 主动读取过的资源、规范化 API call/response trace、最终 task-success 位；它看不到 reasoning trace、未读取资源、ground truth、evaluator 代码或详细评测报告。

compiler 输出 `SKILL.md` 和机器可读 manifest：

```text
skill_id, build_task_id, source_resource_ids,
source_hashes, api_families, compiler_config, skill_hash
```

主设置允许 compiler 看“selected docs + successful trace”，因为这对应实际 resource-to-skill creation。另设 trace-only compiler arm，判断风险是否仍能通过执行行为进入 skill，而不是仅靠把原始文档再次展示给 compiler。

### 隔离与部署

完成 skill 后必须结束 acquisition 进程并清除 messages、reasoning、retrieval cache、临时变量和 attacker overlay。deployment 使用新的 AppWorld world、初始 DB、Qwen 会话和 held-out benign task，只加载最终 skill。

主 deployment 保留 clean API-doc pool、移除 attacker overlay。这最接近“恶意来源已经下线，但正常文档仍存在”的现实设置。另做更严格的 no-retrieval arm：部署时完全没有 resource pool，仅凭 skill 完成同 API family 的任务。两种结果应分别报告，不能混为同一个 source-removed 指标。

## 因果设计

### 实验条件

| 条件 | Acquisition | 生成物 | Deployment | 回答的问题 |
|---|---|---|---|---|
| Clean skill | clean pool | clean skill | clean pool | 正常 skill 的 utility |
| Placebo skill | clean + matched placebo | placebo skill | clean pool | 文档增加或长度本身的影响 |
| Poisoned skill | clean + poison overlay | poisoned skill | clean pool，无 overlay | 主要持久效应 |
| No compilation | clean + poison overlay | 不保存 skill | clean pool | 普通会话污染是否已被清除 |
| Strict persistence | clean + poison overlay | poisoned skill | 无 retrieval | skill 是否独立携带效应 |
| RAG-only | clean acquisition | 无 skill | deployment 才放 poison | 与普通即时 RAG poisoning 的区别 |
| Prior-only | acquisition 无 docs | 可选 | clean deployment | Qwen 是否靠参数记忆或猜 API 绕过资源 |

forced retrieval 只用于早期 mechanism check：如果强制给出攻击文档仍无法进入 skill，就无需扩大实验。论文主结果必须来自 natural retrieval，不能把 forced exposure 当成攻击成功率。

Prior-only 先在 train 上用于筛出真正 resource-dependent 的任务：clean retrieval 应相对无 docs 明显提高任务成功或减少错误调用。筛选规则必须在看 poison 结果之前冻结，不能事后删除“攻击不成功”的任务。

### 随机化单位

真正的独立实验单位是 `task-pair × resource-pool snapshot × rollout seed`，不是 agent 的每一步、每次 API call 或同一 skill 的多个重复触发。clean、placebo 和 poison 在相同 task pair、模型配置和 seed 上配对；运行顺序在 API family、任务难度和 GPU batch 内随机化并分块。先只用 clean runs 选择 prompt、context 和 reasoning effort，冻结后才观察 poison 结果，避免按攻击成功率调参。

### 分阶段指标

主指标是所有随机化单位上的无条件联合事件，而不是只在成功 trace 中计算：

```text
poison top-k exposure
→ agent selected/read
→ poison semantics affected trace
→ acquisition task passed
→ semantics entered skill
→ held-out task loaded skill
→ harmless canary fired
→ benign task utility / collateral damage
```

同时报告各条件相对 clean/placebo 的风险差，以及这条链每一步的条件概率。只有成功 episode 才编译 skill 是系统规则，但统计分母仍保留所有随机化 acquisition runs，否则会产生选择偏差。

## Qwen3.8 与 H200

### 固定型号

本协议把“Qwen3.8、单张 H200 可放下的版本”解释为 [`Qwen/Qwen3.8-27B`](https://huggingface.co/Qwen/Qwen3.8-27B)，而不是 Qwen3.8-Flash-Next 或 2.4T-A95B。官方模型是 27B dense、原生 262,144 context，并兼容 vLLM/SGLang；官方还发布了 [`Qwen3.8-27B-FP8`](https://huggingface.co/Qwen/Qwen3.8-27B-FP8)。单张 H200 的 141 GB HBM 足以容纳 BF16 权重和本实验所需的中等长度 KV cache。[NVIDIA H200](https://www.nvidia.com/en-us/data-center/h200/)

论文主结果应使用 BF16 weights 和默认 BF16/auto KV。FP8 虽是官方量化并声称总体指标接近原模型，但不能假设逐条 tool call 和 poisoning trajectory 等价；FP8 应先在配对子集验证，再作为吞吐扩展，且绝不能让 clean 与 poison 使用不同精度。

### 建议服务配置

```bash
vllm serve Qwen/Qwen3.8-27B \
  --tensor-parallel-size 1 \
  --dtype bfloat16 \
  --kv-cache-dtype auto \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 8 \
  --enable-prefix-caching \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder
```

AppWorld 是文本任务，不应因为模型原生支持 262K 就直接分配 262K 或扩展到 1M。先用 65,536，记录 episode token p99；只有接近上限时才升到 131,072。固定相同截断和历史压缩策略，否则 context 差异会伪装成 poisoning 效应。[官方 vLLM recipe](https://recipes.vllm.ai/Qwen/Qwen3.8-27B)

thinking mode 保持开启。pilot 使用 `reasoning_effort=medium` 控制成本，正式实验在 clean-only calibration 后冻结一个 effort，优先采用官方默认 `xhigh`。主实验设置 `preserve_thinking=false`，防止历史 reasoning 成为 skill 之外的第二条持久通道；另在小规模子集测默认 `true`。thinking sampling 固定为官方建议的 `temperature=1.0, top_p=0.95, top_k=20`，每个 task pair 使用预先登记的 paired seeds。

首轮关闭 MTP/speculative decoding，避免引入另一个可能改变轨迹的实现因素。必须记录 HF commit、AppWorld bundle hash、vLLM/Transformers/CUDA 版本、weight/KV dtype、context cap、thinking 参数、sampling、seed、并发、timeout 和完整接口日志。
