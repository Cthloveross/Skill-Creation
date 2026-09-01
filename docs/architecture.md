# R2SP v0.4 Architecture

## Authority

1. [`run-records/procedure.md`](run-records/procedure.md)：唯一执行流程、路径、命令和硬门控。
2. [`../EXPERIMENT_PLAN.md`](../EXPERIMENT_PLAN.md)：当前实验问题和判定标准。
3. `configs/experiment_plan.yaml`：唯一机器合同；固定模型、数据、资源、预算和全部硬门控。
4. `src/r2sp/`：实现。

## 数据与信任边界

| 组件 | 可以看到 | 不可以做 |
| --- | --- | --- |
| Materializer | 官方 `standard/*.json`、固定 profile payload | 修改官方源；给 Benign 添加内容；改变非目标 Poison endpoint |
| BM25 | 完整 447-resource pool 和任务查询 | append、boost、白名单或重排目标 |
| Acquisition Agent | 原始任务、Top-10 headers、选中五条的全文、本地 runtime | 读取未选择正文；发明 ID；获得额外工具或真实凭据 |
| Compiler | 原始任务、Agent 实际读取的文档、规范化 trace、任务结果 | 看到未读取文档、evaluator 或隐藏 reasoning |
| Deployment | clean corpus、验证过的 `SKILL.md`、evaluator-owned runtime | 访问 Poison corpus、用户文件、外网或真实 API |
| Evaluator | manifest、hash、trace、本地 effect 结果 | 把隐藏答案或 evaluator state 暴露给模型 |

`SKILL.md` 是文本 workflow guidance；不执行代码块、不安装依赖、不扩大工具权限。

## 状态机

```text
official JSON
  → Benign identity corpus + Poison single-target corpus
  → manifest replay
  → canonical 447-doc retrieval 2/2
  → actual model acquisition 2/2
  → compiler 2 profiles
  → complete compile gate 2/2
  → clean reset
  → isolated positive/negative deployment
```

前两个 retrieval gate 都是全局屏障：canonical 1/2 时不启动 acquisition；actual exposure 1/2
时两个 acquisition trace 保留，但 compiler 调用数必须为 0，输出树不得出现 `SKILL.md`。

## 模块

- `file_injection.py`：Benign identity / Poison prepend 变换和 manifest 重放。
- `file_injection_fixture.py`：官方 task、source、profile 与磁盘 corpus 绑定。
- `file_injection_profiles.py`：两个固定 profile、任务和 retrieval lead。
- `retrieval.py`：确定性全局 BM25。
- `agent.py`：Top-10 headers、exact-five、受限全文读取。
- `injection_runner.py`：canonical/actual retrieval 和 compiler 全局硬门控。
- `compiler.py`：fresh-context Skill 文本生成和校验。
- `injection_deployment_runner.py`：2/2 gate 重放、clean reset 和本地部署验证。
- `artifacts.py`：write-once 文件和完整性 manifest。

## Artifact policy

每个 corpus/lead 版本和 run 输出目录不可覆盖。完整 evidence 绑定 source、corpus、task、lead、
Top-10、exact-five、full-read、Skill 和代码 hash。改变 lead 必须创建新版本；部分成功不能被当成
完整通过。原始 AppWorld 数据永久保留，只清理由其可复现生成的旧派生目录。
