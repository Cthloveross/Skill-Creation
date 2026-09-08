# τ-Knowledge DeepSeek-V4 API + 4B Dense

这是 `experiments/tau-knowledge/` 下与 `preliminary/`、`hybrid-full-doc/` 并列的
第三个独立实验目录。

## 从这里开始

核心实验设计、流程、结果、metric 定义、结论和 seal provenance 集中在一份文件中：

**[`PROTOCOL.md`](PROTOCOL.md) — 最终实验完整记录**

不要把旧 `hybrid-full-doc` 的 Qwen 结果与最终 V4 结果混用。最终 headline 是：

| Metric | Benign | Poison 5% | Poison 10% |
| --- | ---: | ---: | ---: |
| Exact utility | 4/20 | 4/20 | 7/20 |
| Strict ASR | — | 10/20 | 13/20 |
| Joint success | — | 4/20 | 5/20 |

Benign false activation 为 `0/20`；攻击链为 5% `20→12→10`、10% `20→15→13`。

## 状态

- 科学结果：2026-09-08 的 60+60 origin run 已完成并封存。
- 当前目录：配置和 runner 已独立，但尚未付费 fresh rerun。
- 原 seal 绑定旧 creation 绝对路径，不能搬迁或重封。
- `results/metrics.json` 是 byte-exact 机器结果快照；`origin.json` 记录原路径与 hash。

## 文件

```text
PROTOCOL.md     唯一权威人读记录
configs/        机器实验合同
injections/     retrieval carrier 与两个 attack body
prompts/        acquisition/compiler/evaluation prompts
scripts/        runner 与后台 launcher
results/        origin-bound 只读结果快照
```

`data/` 和 `runs/` 是 ignored runtime output，runner 会在 fresh run 时自动创建。

## 新 replicate

以下会启动一份新的、付费的 60+60 replicate；不会复用旧结果：

```bash
TAU_FINAL=experiments/tau-knowledge/deepseek-v4-api-4b-dense
.venv/bin/python "$TAU_FINAL/scripts/run_experiment.py" preflight
"$TAU_FINAL/scripts/launch_background.sh"
```
