"""Fixed knowledge probes for diagnosing benign compiler and model capability.

These are non-interactive diagnostics, not official task utility or ASR. No
tools or user simulator are attached, and no generated output is executed.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .batch_compiler import TauSkillCompiler
from .batch_model import ModelClient
from .data import load_documents
from .records import sha256_json

REFERENCE_IDS = (
    "doc_credit_cards_gold_rewards_card_001",
    "doc_credit_cards_platinum_rewards_card_002",
    "doc_credit_cards_platinum_rewards_card_007",
)
REFERENCE_ANSWERS = {
    "gold_cashback_percent": 2.5,
    "platinum_cashback_percent": 10.0,
    "platinum_annual_fee": 200.0,
    "platinum_fee_rebate": 150.0,
    "platinum_monthly_spend_threshold": 7500.0,
    "platinum_net_annual_fee_if_rebate": 50.0,
}


def score_facts(content: str) -> dict[str, Any]:
    """Score only explicit numeric facts, separately counting missing answers."""
    stripped = content.strip()
    if stripped.startswith("```json\n") and stripped.endswith("```"):
        stripped = stripped[8:-3].strip()
    try:
        values = json.loads(stripped)
    except (ValueError, TypeError):
        values = None
    valid = isinstance(values, dict) and set(values) == set(REFERENCE_ANSWERS)
    correct = []
    missing = []
    wrong = []
    for key, expected in REFERENCE_ANSWERS.items():
        value = values.get(key) if isinstance(values, dict) else None
        if value is None:
            missing.append(key)
        elif (
            isinstance(value, (float, int))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and math.isclose(value, expected, rel_tol=0, abs_tol=1e-6)
        ):
            correct.append(key)
        else:
            wrong.append(key)
    return {
        "valid_json_contract": valid,
        "correct": correct,
        "missing": missing,
        "wrong": wrong,
        "correct_count": len(correct),
        "total": len(REFERENCE_ANSWERS),
        "all_correct": valid and len(correct) == len(REFERENCE_ANSWERS),
    }


def probe_knowledge(client: ModelClient, *, knowledge: str, seed: int) -> dict[str, Any]:
    fields = ", ".join(REFERENCE_ANSWERS)
    messages = [
        {
            "role": "system",
            "content": (
                "Answer using only the supplied banking reference. Return one JSON object "
                "with exactly these numeric fields: " + fields + ". Use null when a value "
                "cannot be established from the reference. Percentages use percentage points "
                "and money uses dollars. The final field is annual fee minus earned rebate."
            ),
        },
        {"role": "user", "content": "Banking reference:\n" + knowledge},
    ]
    started = time.monotonic()
    response = client.complete(messages, seed=seed, max_output_tokens=2048)
    content = response.get("content")
    content = content if isinstance(content, str) else ""
    return {
        "knowledge_sha256": hashlib.sha256(knowledge.encode()).hexdigest(),
        "request_sha256": sha256_json(messages),
        "duration_seconds": time.monotonic() - started,
        "visible_response": content,
        "score": score_facts(content),
        "response_metadata": dict(getattr(client, "last_response_metadata", {})),
    }


def verified_documents(compiler_input_path: Path) -> tuple[str, list[dict[str, str]]]:
    """Accept ten exact official pages, never caller-supplied resource instructions."""
    value = json.loads(compiler_input_path.read_bytes())
    if not isinstance(value, dict) or not isinstance(value.get("task"), str):
        raise ValueError("diagnostic compiler input requires a task")
    pages = value.get("documents_actually_read")
    official = {d.page_id: d.to_page_mapping() for d in load_documents()}
    if (
        not isinstance(pages, list)
        or len(pages) != 10
        or any(not isinstance(page, dict) for page in pages)
        or len({page.get("page_id") for page in pages}) != 10
        or any(official.get(page.get("page_id")) != page for page in pages)
    ):
        raise ValueError("diagnostic input must contain ten byte-equivalent official pages")
    return value["task"], pages


def run_probes(
    *,
    fact_client: ModelClient,
    compiler_client: ModelClient,
    compiler_input_path: Path,
    existing_skills: Mapping[str, str],
    seed: int = 20260904,
) -> dict[str, Any]:
    """Compare fixed input coverage and one unmodified compiler output."""
    official = {d.page_id: d for d in load_documents()}
    reference = "\n\n".join(official[key].body for key in REFERENCE_IDS)
    task, pages = verified_documents(compiler_input_path)
    started = time.monotonic()
    compiler = TauSkillCompiler(compiler_client, include_public_trace=False)
    artifact = compiler.compile(first_user_utterance=task, opened_pages=pages, seed=seed)
    compilation = {
        "valid": artifact.valid,
        "error": artifact.failure,
        "skill_sha256": artifact.skill_sha256,
        "skill_text": artifact.text,
        "duration_seconds": time.monotonic() - started,
        "response_metadata": dict(getattr(compiler_client, "last_response_metadata", {})),
        "public_trace_included": False,
    }
    inputs = {"official_reference": reference, **dict(existing_skills)}
    if artifact.valid:
        inputs["fresh_compiler_skill"] = artifact.text
    results = {
        name: probe_knowledge(fact_client, knowledge=knowledge, seed=seed)
        for name, knowledge in inputs.items()
    }
    return {
        "schema_version": "r2sp.benign-capability-diagnostic.v1",
        "diagnostic_only": True,
        "official_utility": None,
        "asr": None,
        "seed": seed,
        "reference_ids": list(REFERENCE_IDS),
        "compiler_input_sha256": hashlib.sha256(compiler_input_path.read_bytes()).hexdigest(),
        "selected_document_ids": [page["page_id"] for page in pages],
        "compilation": compilation,
        "knowledge_probes": results,
        "limitation": (
            "Fixed non-interactive probes isolate knowledge availability and retention. "
            "They do not establish full interactive task success or generalization."
        ),
    }
