# Historical GPU qualification evidence

This file preserves the measured server inventory and Qwen3.8 capacity results. It is not an
executable plan or the machine-readable contract. The current v0.4 workflow uses
`Qwen/Qwen3.8-27B-FP8`, revision `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`, FP8 weight-only
Marlin with FP16 compute, physical GPUs `0,6`, TP=2, PP=1, 32,768 context and port 18138. The
authoritative settings are in
[`run-records/procedure.md`](run-records/procedure.md#9-模型与-gpu-合同).

## Verdict

| Target | Status | Reason |
| --- | --- | --- |
| Current v0.4: Qwen3.8-27B-FP8, two RTX 6000, TP=2 | **Selected and live-qualified** | The 28.75 GiB checkpoint loaded across GPUs 0/6, used 14.28 GiB model memory per GPU, exposed 32,768 context, and completed the paired acquisition/compiler run. |
| Protocol v0.3: one H200, BF16, TP=1, 65,536 tokens | **Incompatible** | This server has Turing GPUs with compute capability 7.5 and 24 GiB per card. BF16 requires compute capability 8.0+, and the pinned weights exceed one card. |
| Four-card FP16 27B profile | **Memory-feasible, not qualified** | Four cards provide enough aggregate memory to shard the weights, but this topology was not run in this qualification. Do not infer its speed or 65,536-token stability from the eight-card result. |
| Eight-card FP16 27B profile | **Qualified for non-research engineering use** | The pinned Qwen3.8-27B passed real generation, a 56,012-token prompt, and the complete six-check service contract at `max_model_len=65,536` with TP=2/PP=4. |

Changing H200/BF16/TP=1 to RTX 6000/FP16/multi-GPU changes a frozen experimental factor. Results
from that profile are instrumentation evidence only and must not be labelled protocol-v0.3 research
results.

## Observed server inventory

- 10 × NVIDIA Quadro RTX 6000, 24,576 MiB each; compute capability 7.5.
- Driver 580.95.05; CUDA toolkit 11.7 exists at `/usr/local/cuda-11.7` but is not on `PATH`.
- PCIe maximum link: Gen3 ×16. All GPUs report peer read/write support.
- Five bonded two-link NVLink pairs: `0-6`, `1-3`, `2-4`, `5-7`, and `8-9`.
- All GPUs were idle during the audit and report NUMA node 0.
- Host memory: 376 GiB total, approximately 350 GiB available during the audit.
- `/home`: 176 GiB free but 99% used. `/tmp` had 103 GiB free before the disposable
  qualification environment was created.
- Python 3.10.12 is installed; Python 3.11 is absent.
- `torch`, `vllm`, and `appworld` were absent from the project virtual environment during this
  historical audit; model serving used a disposable environment under `/tmp`.
- Docker CLI and NVIDIA container utilities exist, but the current user cannot access the Docker
  daemon socket.
- Port 8000 is already occupied by an unrelated host-wide Uvicorn process; this trial uses 18000.
- The pinned Qwen model was downloaded into a disposable `/tmp` Hugging Face cache for the
  qualification; it was not added to the normal user cache or the repository. The 62 GiB
  temporary environment and cache were deleted after the measurements, restoring `/tmp` to
  103 GiB free.

The pinned model index declares 55,562,855,904 bytes (51.75 GiB) of safetensor weights across 18
shards. Weight-only lower bounds are therefore approximately 25.87 GiB/card for a two-card
TP=2/PP=1 layout and 12.94 GiB/card at four-way sharding. The two-card layout cannot fit on a 24 GiB
card even before KV/state caches, activations, and runtime overhead. A three-card pipeline layout is
not ruled out, but its model support, load balance, and residual headroom are unknown. Four cards
are the first conservative unquantized profile selected for this project; this is an engineering
choice, not a proven minimum.

vLLM 0.28 documents compute capability 7.5 as its general NVIDIA minimum, so these GPUs are not
excluded at the framework level. Qwen3.8-27B has 48 linear-attention layers and 16 full-attention
layers. The official recipe reports newer GPU families, so the staged local measurements below,
not aggregate memory alone, are the basis for this server's engineering verdict.

## Measured Qwen3.8-27B eight-card qualification

The target run used the pinned revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, vLLM 0.28.0, PyTorch 2.13.0+cu130,
FP16 model and KV cache, eager execution, `TRITON_ATTN`, Triton GDN prefill/decode, text-only mode,
and NCCL 2.29.7. Physical GPU order `0,6,1,3,2,4,5,7` formed four NVLink-aligned TP=2 groups and
PP=4 split the 64 transformer layers across them.

The first multi-GPU attempt found one packaging issue before model load: FlashInfer 0.6.16.post3
evaluated `array.array[int]` at import time on Python 3.10 and raised `TypeError`. Adding postponed
annotation evaluation in the disposable package made `import flashinfer.comm` succeed.
`--disable-custom-all-reduce` then selected PYNCCL for TP and PP communication. That flag alone is
not sufficient because vLLM imports the FlashInfer all-reduce module even when the custom kernel is
disabled. A durable environment must use a FlashInfer build where that import succeeds; do not
depend on an unrecorded manual site-package edit.

Measured stages:

| `max_model_len` | Target check | Result |
| ---: | --- | --- |
| 16,384 | Full six-check `r2sp probe-model-service` | **6/6, `ready=true`** after correcting the probe's compiler budget to the protocol's 4,096-token ceiling. First engine profile/cache/warmup was 314.76 s. Stable decode was approximately 9.7–11.4 tokens/s. |
| 32,768 | 30,012-token chat prompt + one output token | **Passed** in 35.573 s; no OOM or queueing. Cached engine warmup was 4.52 s. The complete service probe then passed **6/6**. |
| 65,536 | 56,012-token chat prompt + one output token | **Passed** in 97.182 s; all eight GPUs reached 100% utilization, peak observed allocation was 20,978 MiB, and no request waited for capacity. Cached engine warmup was 4.36 s. The complete service probe then passed **6/6**. |

At 65,536, vLLM reported 1,422,206 tokens of aggregate GPU KV capacity and theoretical
single-length concurrency 21.70 for this cache layout. At 16,384, the observed idle allocations
were 19,522–20,868 MiB per selected card. The 30K and 56K end-to-end prefill checks averaged about
844 and 576 prompt tokens/s respectively; the prompts were deliberately repetitive capacity
fixtures, not a representative AppWorld workload benchmark.

These historical six-check results cover model identity, tokenizer, ordinary completion,
reasoning/tool parsing, the four-tool agent loop, and valid non-placeholder skill compilation. The
current v0.3 probe adds a seventh exact-five structured-selection parser check; the earlier 6/6
measurements must not be relabelled as 7/7. The original probe used a
512-token compiler cap and produced a false negative because Qwen exhausted that budget in hidden
reasoning. `src/r2sp/model_probe.py` now uses up to 4,096 compiler output tokens while reserving
context, and a regression test fixes this contract.

The eight-card profile is therefore a measured working choice for this project. Remaining unknowns
are four-card performance, two four-card replicas versus one eight-card endpoint, a combined
56K-prompt plus 8,192-output-token worst case, and restart behavior across a newly built environment.

## Reproducing the qualified profile

Preconditions:

1. Allocate an explicit model/package cache on a filesystem with at least 100 GiB of working
   headroom. Do not default this download to the nearly full `/home` filesystem.
2. Create a separate model-service environment with a vLLM build compatible with the installed
   driver and Turing (SM 7.5). The vLLM wheel carries its own CUDA user-space stack; the host's CUDA
   11.7 toolkit need not be reused. Do not add GPU runtime packages to the dependency-light core
   venv.
3. Confirm exclusive access to the eight selected GPUs before serving.
4. Keep the service bound to loopback; the runner intentionally rejects non-loopback model URLs.
5. Verify `python -c 'import flashinfer.comm'` in the serving environment before allocating GPUs.
   Resolve the Python 3.10 annotation issue described above if this import fails.

Qualified eight-card command:

```bash
export HF_HOME=/absolute/cache/path/huggingface
export CUDA_VISIBLE_DEVICES=0,6,1,3,2,4,5,7
export VLLM_GDN_DECODE_KERNEL=triton
export VLLM_USE_FLASHINFER_SAMPLER=0

NCCL_DEBUG=WARN vllm serve Qwen/Qwen3.8-27B \
  --revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --tokenizer-revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --dtype half \
  --tensor-parallel-size 2 \
  --pipeline-parallel-size 4 \
  --distributed-executor-backend mp \
  --disable-custom-all-reduce \
  --max-model-len 65536 \
  --max-num-seqs 1 \
  --gpu-memory-utilization 0.85 \
  --kv-cache-dtype float16 \
  --attention-backend TRITON_ATTN \
  --gdn-prefill-backend triton \
  --mamba-cache-dtype float16 \
  --mamba-ssm-cache-dtype float32 \
  --language-model-only \
  --enforce-eager \
  --no-enable-prefix-caching \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --host 127.0.0.1 \
  --port 18000
```

This ordering makes each TP=2 group one physical NVLink pair and leaves the smaller pipeline
transfers between pairs. It is the qualified capacity profile, not a proven performance optimum.
Benchmark it against one four-card TP=2/PP=2 endpoint before choosing a production throughput
layout. For independent episodes, two four-card endpoints may outperform one eight-card pipeline;
the result cannot be deduced from topology or memory alone.

Validation must be incremental:

1. Reproduce 16,384 tokens and one sequence before increasing the limit.
2. Run the checked-in no-side-effect model integration probe. It verifies `/v1/models`,
   `/tokenize`, ordinary completion, reasoning/tool parsing, exact-five selection parsing, the agent
   loop, and the compiler; its
   output is permanently marked non-research:

   ```bash
   r2sp probe-model-service \
     --base-url http://127.0.0.1:18000/v1 \
     --max-model-len 16384
   ```

3. Record peak memory on every rank while the probe runs.
4. Increase to 32,768 tokens, then 65,536 only if the preceding stage is stable.
5. Treat a 65,536-token startup as insufficient evidence for any different workflow; validate that
   workflow's own prompt/output path separately.

This qualification observed 65,536-token serving, a 56,012-token real prompt, and the complete
service contract. It did not run the scientific episode matrix or the combined maximum prompt plus
maximum output path, so research-workload completion and end-to-end runtime remain unknown.

## Primary references

- [NVIDIA CUDA floating-point requirements](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/mathematical-functions.html)
- [Qwen3.8-27B pinned weight index](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/model.safetensors.index.json)
- [Qwen3.8-27B pinned model configuration](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/config.json)
- [Qwen3.8 official model collection](https://huggingface.co/collections/Qwen/qwen38)
- [Official vLLM Qwen3.8-27B recipe](https://recipes.vllm.ai/Qwen/Qwen3.8-27B)
- [vLLM 0.28 NVIDIA GPU requirements](https://docs.vllm.ai/en/v0.28.0/getting_started/installation/gpu/)
- [vLLM 0.28 serve options](https://docs.vllm.ai/en/v0.28.0/cli/serve/)
- [vLLM attention backend support](https://docs.vllm.ai/en/v0.28.0/design/attention_backends/)
- [vLLM Qwen GDN backend selection](https://github.com/vllm-project/vllm/blob/v0.28.0/vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py)
