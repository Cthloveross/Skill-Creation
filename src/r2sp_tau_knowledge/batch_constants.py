"""Pinned paths and commitments for the independent benign r8 batch protocol."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
EXPERIMENT_ROOT = REPOSITORY_ROOT / "experiments" / "tau-knowledge" / "preliminary"
UPSTREAM_ROOT = EXPERIMENT_ROOT / "data" / "upstream" / "tau2-bench"
BANKING_ROOT = UPSTREAM_ROOT / "data" / "tau2" / "domains" / "banking_knowledge"
DOCUMENTS_ROOT = BANKING_ROOT / "documents"
TASKS_ROOT = BANKING_ROOT / "tasks"

UPSTREAM_COMMIT = "fc0055dc4e0a316c3f83133267fbd6faaa770992"
UPSTREAM_ROOT_TREE = "4837da1c2b310152f63d3d7987f4325183ca6f7c"
BANKING_TREE = "0ce703cbc3e07b0b09905daf29700813b3b8f122"
EXPECTED_DOCUMENT_COUNT = 698
EXPECTED_TASK_COUNT = 97

# These historical names are forbidden in every v2 evaluation tool list.
SIDECAR_TOOLS = {
    "mock-api-call": "mock_api_record",
    "delete-sentinel": "sandbox_delete_sentinel",
}

MAX_SEARCHES = 2
RETRIEVER_TOP_K = 10
VISIBLE_TOP_K = 10
SELECTION_K = 10
RRF_K = 60
MAX_TURNS = 60
MAX_TASK_TOOL_CALLS = 800

MODEL_ID = "Qwen/Qwen3.8-Flash-Next-FP8"
MODEL_REVISION = "236dfdf285828023ca3bcd3f37366c58a3469b13"
MODEL_SEED = 20260904
MODEL_MAX_CONTEXT_TOKENS = 65536
AGENT_MAX_OUTPUT_TOKENS = 16384
USER_SIMULATOR_MAX_OUTPUT_TOKENS = 8192
COMPILER_MAX_INPUT_TOKENS = 32768
COMPILER_MAX_OUTPUT_TOKENS = 32768
COMPILER_MAX_SKILL_TOKENS = 16384
MODEL_WEIGHT_SHARD_COUNT = 131
MODEL_WEIGHT_SIZE_BYTES = 185_523_317_458
MODEL_ARTIFACT_SHA256 = {
    "config.json": "c22eb0a053eed62e18f0184d3ca62d3798f208c3e00b9feee939fc3dbacdc8ca",
    "model.safetensors.index.json": (
        "0419e2c2dfbb925257d7409405433a793cf7ff7d96f3eba882a815ec6d9fe7a6"
    ),
    "chat_template.jinja": ("c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041"),
    "generation_config.json": ("e70c136c1b78ddc1fb0905bac8e733a4dc448d4f852a5dd75143fffc70be550e"),
    "tokenizer.json": "0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3",
    "tokenizer_config.json": ("b11349aafa7cdc6a320767cf7ceb29ed82f7eda5d65e8e0819e76f0ce947bf27"),
    "LICENSE": "a0dc422560841fd68e06d974907f8b4c709bca44a67daad2b528437bdf676c08",
}

DENSE_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
DENSE_MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
DENSE_DIMENSIONS = 1024
DENSE_MAX_INPUT_TOKENS = 8192
DENSE_WEIGHT_SIZE_BYTES = 1_191_586_416
DENSE_ARTIFACT_SHA256 = {
    "config.json": "b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9",
    "model.safetensors": ("0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"),
    "tokenizer.json": "def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a",
    "tokenizer_config.json": ("253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0"),
}
DENSE_QUERY_INSTRUCTION = (
    "Instruct: Given a web search query, retrieve relevant passages that answer the query"
    "\nQuery:{query}"
)

VLLM_IMAGE_TAG = "vllm/vllm-openai:qwen38-flash-next"
VLLM_OCI_INDEX_DIGEST = "sha256:fc120ece0a388cc0aa1caad4a9f1cd92113484ab7ec2fd0efadd62585be05bf8"
VLLM_AMD64_MANIFEST_DIGEST = (
    "sha256:0aea30240f3e3d9ffae8526643950e170eb5fa07fc427016a9dd90892afa2aa3"
)
VLLM_MIN_VERSION = "0.29.0"
