"""Pinned paths and commitments for the tau-Knowledge experiment."""

from __future__ import annotations

from pathlib import Path

from tau_skill_evolution.core.attack_payload import ATTACK_COMMANDS

PACKAGE_ROOT = Path(__file__).resolve().parent
EXPERIMENT_ROOT = PACKAGE_ROOT.parents[1]
UPSTREAM_ROOT = EXPERIMENT_ROOT / "data" / "upstream" / "tau2-bench"
BANKING_ROOT = UPSTREAM_ROOT / "data" / "tau2" / "domains" / "banking_knowledge"
DOCUMENTS_ROOT = BANKING_ROOT / "documents"
TASKS_ROOT = BANKING_ROOT / "tasks"
MATERIALIZED_ROOT = EXPERIMENT_ROOT / "data" / "materialized"
INJECTIONS_ROOT = EXPERIMENT_ROOT / "injections"

UPSTREAM_COMMIT = "fc0055dc4e0a316c3f83133267fbd6faaa770992"
UPSTREAM_ROOT_TREE = "4837da1c2b310152f63d3d7987f4325183ca6f7c"
BANKING_TREE = "0ce703cbc3e07b0b09905daf29700813b3b8f122"
EXPECTED_DOCUMENT_COUNT = 698
EXPECTED_TASK_COUNT = 97

TARGET_DOCUMENT_ID = "doc_credit_cards_gold_rewards_card_001"
FIXED_FILE_SHA256 = {
    "tasks/task_001.json": "9a797288dd215e89c0fab9d0063581a3a64d433f06af6179eaad795521b23ef0",
    "tasks/task_002.json": "81a1aae95b6bb4d61991d0b9cef836b302b675685309174a53d878693cbd94c5",
    "tasks/task_034.json": "364587224e8e88709a65db5415ec5ba874b1dd5a581d7ab70048dcd110fe3970",
    f"documents/{TARGET_DOCUMENT_ID}.json": (
        "67cadb8e04c5859974f3236af915f26153da1d5f8f5fa304bbce7dd9e91acd98"
    ),
    "db.json": "e692feb797c659f0e21ff7380aa87beb4e95a0694d7bb7945f073102f0293d28",
}

PAYLOAD_FILES = {
    "mock-api-call": INJECTIONS_ROOT / "mock-api-call.txt",
    "delete-sentinel": INJECTIONS_ROOT / "delete-sentinel.txt",
}
RETRIEVAL_FILE = INJECTIONS_ROOT / "retrieval.txt"
PAYLOAD_COMMANDS = dict(ATTACK_COMMANDS)
SIDECAR_TOOLS = {
    "mock-api-call": "mock_api_record",
    "delete-sentinel": "sandbox_delete_sentinel",
}

MAX_TASK_TOOL_CALLS = 800

MODEL_SEED = 20260904

# Bedrock Mantle Responses models this method may use. The first entry is the
# historical default; configs select one explicitly via provider.model.
SUPPORTED_MODELS = ("openai.gpt-5.5", "openai.gpt-5.6-terra")
DEFAULT_MODEL = SUPPORTED_MODELS[0]

# The official tau2 bank worker runs in data/upstream/tau2-bench/.venv. The
# original pin was 3.12.14, but uv's download index (checked 2026-10-04) does
# not publish 3.12.14, and 3.12.12 is what is installed in that venv. The pin
# is exact: preflight and official_runtime both compare against this tuple.
WORKER_PYTHON_VERSION = (3, 12, 12)
