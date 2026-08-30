# AppWorld 在本项目中的用法

AppWorld 可以同时提供“给 agent 做的良性任务”“完成任务所需的 API 文档”“真正可调用的本地应用”和“任务是否完成的自动评测”。它不是一个通用网页文档库，但正好能把任务、可检索资源、执行环境和隐藏评测器物理分开，因此适合作为本项目的主实验环境。[Trivedi et al. 2024](https://doi.org/10.18653/v1/2024.acl-long.850) 报告了 9 个日常应用、457 个 API 和 750 个自然语言任务，并用数据库状态单元测试检查任务成功与额外副作用。

## 数据边界

### 资产分层

| AppWorld 资产 | 是否提供 | agent 如何使用 | 是否放入 resource pool |
|---|---:|---|---:|
| 自然语言任务 instruction | 是，750 个任务 | 作为当前用户请求 | 否 |
| app 简介 | 是 | 作为固定、可信的一级目录 | 主实验中否；单独做投毒扩展 |
| API documentation | 是 | 通过统一检索器按需检索 | 是 |
| API 实现、数据库和模拟用户 | 是 | agent 通过工具调用改变世界状态 | 否 |
| solution、required APIs、evaluation code | train/dev 有完整信息，测试集只开放有限元数据 | 训练或隐藏评测使用 | 绝不能给被测 agent |

这里最需要区分的是“API”和“API 文档”。API 是 agent 真正执行动作的工具；API 文档才是它搜索和阅读的资源。我们实验中的 clean resource pool 应由文档组成，而不是由 API implementation、任务答案或历史轨迹组成。

### 文档范围

AppWorld 允许本地下载全部 API documentation，并提供三种表示：官方 standard JSON、function-calling schema 和完整 OpenAPI。`world.task.api_docs` 可以访问和压缩这些文档，`ApiDocs` helper app 也允许 agent 在运行中按需查询。`world.task.app_descriptions` 另有每个 app 的一到数行功能简介。官方明确允许开发者把部分或全部文档预先展示给 agent，也允许用 `api_docs` 和 `app_descriptions` 构建自己的检索器。[官方仓库](https://github.com/StonyBrookNLP/appworld)

因此，我们不必只给 agent task-specific APIs。更符合 threat model 的做法是：把 9 个 app 的全部 457 份 API 文档放进一个固定共享索引，再把 app 简介作为单独的 `app_card` 资源。官方文件按 app 保存；我们在实验适配层把它规范化成“一条 API 文档对应一条 resource”。攻击者的 1 条 overlay 与 457 条 clean API resources 自然竞争，资源占比约 0.22%；3 条约 0.65%。

为了避免把两种攻击面混在一起，后续精确协议再收紧一步：主实验把 app descriptions 当作固定可信的一级路由目录，只把 457 条 API docs 放入可投毒索引。攻击 app descriptions 作为单独扩展实验，不与 API-doc poisoning 合并报告。

“全部文档”也有边界。AppWorld 的文档主要是 API schema、参数、描述、返回值和错误等结构化技术材料，并不是包含教程、政策、FAQ 和支持文章的大型自然语言知识库。若论文要证明攻击同样发生在长篇 prose 上，需要另加 DocPrompting 或 OR-ShARC；不能假装 AppWorld 自带这类语料。

### 任务结构

AppWorld 确实提供直接交给 agent 的任务。每个 task 至少包含三部分：`instruction`、代表用户身份的 `supervisor`，以及由任务数据库和当前时间构成的 `initial state`。任务涉及购物、音乐、支付、笔记、消息等模拟日常工作流，可能需要跨 app、多轮查询和多次 API 调用。agent 完成后调用 `supervisor.complete_task()`，隐藏 evaluator 再比较数据库状态，并检查 collateral damage。

数据已有 `train`、`dev`、`test_normal` 和 `test_challenge` 划分。train/dev 可用于开发、筛任务和构建 skill；正式 deployment 应保留 test split 或我们另行冻结的 held-out tasks。`ground_truth`、gold API calls、solution 和 evaluator 不是 resource，不能进入检索索引或 skill prompt。

## 实验适配

### 构建阶段

推荐的数据流是：

```text
AppWorld benign instruction
          ↓ 作为检索 query
全量 clean API docs + 少量 attacker overlay
          ↓ top-k 文档
良性 agent 调用本地 AppWorld APIs
          ↓
AppWorld evaluator 验证任务成功与额外修改
          ↓
成功 trace 交给我们的 skill compiler
```

这样 attack surface 只在 resource index。攻击者不控制原始任务、agent、retriever 参数、API implementation、数据库、compiler 或 evaluator。clean 和 poison 两个实验臂使用相同任务、初始状态、检索器和模型，只改变 overlay 是否存在。

### 隔离阶段

skill 生成后，删除 overlay、全部检索文本、检索 cache、构建会话和普通 memory，只保留生成出的 skill artifact。随后创建新的 AppWorld world 和新会话，在 held-out benign task 上加载该 skill。最终结果同时看 AppWorld 的状态化任务成功率、额外副作用，以及我们自己加入的本地无副作用 canary。

### 缺失组件

AppWorld 不会替我们提供攻击资源、skill compiler、source-removal harness 或“构建任务—部署任务”配对。现有 750 个任务可以直接作为良性任务底座，但哪些任务适合先学出一个可复用 skill、哪些后续任务能自然触发它，需要我们根据 required app/API 和任务语义建立配对；先用 train/dev 构建候选，再对 held-out tasks 做人工复核和冻结。

## 使用结论

可以直接复用的部分包括 457 份 API 文档、app descriptions、750 个 agent tasks、本地可执行的 apps/DB、任务初始状态、执行日志和状态化 evaluator。我们新增的只有检索池适配器、攻击者 overlay、skill compiler、构建—部署配对、彻底清除来源的实验 harness 和 canary 记录器。

最干净的主设置不是“只给正确 API 的文档”，也不是“把 AppWorld 所有文件都丢进池里”，而是“全量 API docs 构成可投毒 clean pool；app descriptions 是固定可信目录；instruction 单独作为任务；implementation 单独作为工具；ground truth 单独作为隐藏 evaluator”。这正好对应本项目想研究的低权限 resource 如何被提升为持久 skill 行为。

AppWorld 的 API docs、任务、实现和 evaluator 属于加密的 protected portion。研究者可以下载后在本地实验，但公开再分发这些内容或其衍生物时必须保持加密。论文 artifact 最稳妥的做法是发布索引构建代码、官方 resource IDs/hashes、overlay、配置和日志，而不发布解密后的官方文档或任务内容；公开前还应向作者确认衍生 benchmark 的发布形式。[许可说明](https://github.com/StonyBrookNLP/appworld#lock_with_ink_pen-license)
