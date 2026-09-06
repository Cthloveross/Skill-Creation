#!/usr/bin/env python3
"""Qualify an owned model service and optionally run fixed benign knowledge probes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from batch_source import source_provenance, verified_bundle, verify_checkout  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("creation", "evaluation"), default="creation")
    parser.add_argument("--compiler-input", type=Path)
    parser.add_argument("--retrieval-queries", type=Path)
    args = parser.parse_args()
    from r2sp_tau_knowledge.batch import load_spec
    from r2sp_tau_knowledge.batch_model import GenerationConfig, OpenAICompatibleClient
    from r2sp_tau_knowledge.batch_runtime import BatchRuntime
    from r2sp_tau_knowledge.benign_probe import run_probes, verified_documents

    # Model identity is taken from a validated creation spec even when only
    # qualifying the evaluation runtime, which requires no generation source.
    spec = load_spec(args.spec, "creation")
    if args.compiler_input:
        verified_documents(args.compiler_input)
    queries = None
    if args.retrieval_queries:
        queries = json.loads(args.retrieval_queries.read_bytes())
        if (
            args.phase != "creation"
            or not isinstance(queries, list)
            or not 1 <= len(queries) <= 2
            or any(not isinstance(query, str) or not query.strip() for query in queries)
        ):
            raise ValueError("retrieval probes require creation phase and one or two queries")
    args.output.mkdir(parents=True, exist_ok=False)
    provenance = source_provenance(PROJECT_ROOT, args.output / "source-bundles")
    report = {
        "schema_version": "r2sp.benign-runtime-qualification.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": True,
        "model": spec.model,
        "source": provenance,
        "status": "INVALID",
    }
    runtime = BatchRuntime(phase=args.phase, model=spec.model)
    try:
        with runtime:
            report["runtime"] = runtime.metadata
            if queries is not None:
                from r2sp_tau_knowledge.batch_services import DENSE_ENDPOINT, RUNTIME_ROOT
                from r2sp_tau_knowledge.benign_retrieval_probe import run_retrieval_probe
                from r2sp_tau_knowledge.dense_client import HttpCachedDenseEmbedder

                report["retrieval_probe"] = run_retrieval_probe(
                    queries,
                    HttpCachedDenseEmbedder(
                        DENSE_ENDPOINT, cache_root=RUNTIME_ROOT / "cache" / "dense"
                    ),
                    reference_ids=(
                        "doc_credit_cards_platinum_rewards_card_002",
                        "doc_credit_cards_platinum_rewards_card_007",
                        "doc_credit_cards_platinum_rewards_card_010",
                    ),
                )
            if args.compiler_input:
                fact_client = OpenAICompatibleClient(
                    spec.model["endpoint"],
                    config=GenerationConfig(
                        model=spec.model["id"],
                        revision=spec.model["revision"],
                        temperature=0,
                        enable_thinking=False,
                        preserve_thinking=False,
                        reasoning_effort=None,
                        max_output_tokens=2048,
                    ),
                )
                report["probes"] = run_probes(
                    fact_client=fact_client,
                    compiler_client=runtime.backend.client,
                    compiler_input_path=args.compiler_input,
                    existing_skills={},
                )
            _, members = verified_bundle(
                Path(provenance["source_bundle_path"]), provenance["source_bundle_sha256"]
            )
            verify_checkout(PROJECT_ROOT, members)
            report["status"] = "COMPLETE"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        report["runtime"] = runtime.metadata
    with (args.output / "report.json").open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "report": str(args.output / "report.json")}))
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
