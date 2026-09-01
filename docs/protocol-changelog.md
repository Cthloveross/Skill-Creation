# R2SP Current Protocol

当前只维护 `v0.4` 正确流程；完整定义见
[`run-records/procedure.md`](run-records/procedure.md)。

## v0.4 — 2026-09-01

- Arm 只使用 `A_benign` / `B_poison`。
- Benign 是官方 API-document tree 的字节等价完整副本，无 lead、wrapper、tool 或 nonce。
- 只有 Poison 在一个注册目标 endpoint `description` 前置 retrieval lead 和 required block。
- 不做两臂 token 长度匹配。
- 使用原始 authoring instruction 对完整 447-resource pool 做 canonical BM25 准入。
- 不 append、boost、白名单或重排检索目标。
- canonical Poison Top-10 必须 2/2；否则不启动模型。
- canonical miss 会停止流程；下一步只能版本化 lead、重新 materialize，并从完整 447-resource
  检索重跑。
- 两个真实 acquisition 全部完成后统一检查实际 Top-10 → exact-five → full-read；任何 miss 都使
  compiler 调用数为 0，且不生成任何 `SKILL.md`。
- deployment 只接受完整 compile gate 2/2，并验证 Skill、source、corpus 和 complete hash。
- 三个 live 入口绑定同一 `configs/experiment_plan.yaml`；配置、canonical gate 或 deployment gate
  失败时不访问模型服务，也不构造实际 HTTP provider。
- 所有输出 write-once；修改 lead 必须创建新 corpus/artifact 版本并从 materialize 重跑。
