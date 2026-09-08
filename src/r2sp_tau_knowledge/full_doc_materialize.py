"""Five-corpus materialization adapter for the full-document experiment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .full_doc_spec import CorpusPlan, ExperimentSpec
from .materialize import CorpusMaterializer, Materialization, PayloadSetSnapshot


@dataclass(frozen=True, slots=True)
class FullDocCorpusSet:
    by_key: Mapping[str, Materialization]
    payload_snapshot: PayloadSetSnapshot

    def __post_init__(self) -> None:
        copied = dict(self.by_key)
        expected = {
            "benign",
            "poison-5-mock-api-call",
            "poison-5-delete-sentinel",
            "poison-10-mock-api-call",
            "poison-10-delete-sentinel",
        }
        if set(copied) != expected:
            raise ValueError("full-document corpus set must contain exactly five corpora")
        object.__setattr__(self, "by_key", MappingProxyType(copied))

    def for_key(self, key: str) -> Materialization:
        try:
            return self.by_key[key]
        except KeyError as exc:
            raise KeyError(f"unknown materialization key: {key}") from exc


class FullDocCorpusMaterializer:
    """Materialize one benign and four nested poison corpora from one snapshot."""

    def __init__(
        self,
        spec: ExperimentSpec,
        *,
        materializer: CorpusMaterializer | None = None,
    ) -> None:
        self.spec = spec
        self.materializer = materializer or CorpusMaterializer(
            source_documents=spec.paths.source_documents_root,
            output_root=spec.paths.materialized_root,
            injections_root=spec.paths.injections_root,
        )

    def materialize_plan(
        self,
        plan: CorpusPlan,
        *,
        payload_snapshot: PayloadSetSnapshot,
    ) -> Materialization:
        return self.materializer.materialize(
            plan.profile,
            plan.materialization_arm,
            payload_snapshot=payload_snapshot,
            target_document_ids=plan.target_document_ids,
        )

    def materialize_all(self) -> FullDocCorpusSet:
        snapshot = self.materializer.snapshot_payloads()
        corpora = {
            plan.key: self.materialize_plan(plan, payload_snapshot=snapshot)
            for plan in self.spec.corpus_plans
        }
        return FullDocCorpusSet(corpora, snapshot)


__all__ = ["FullDocCorpusMaterializer", "FullDocCorpusSet"]
