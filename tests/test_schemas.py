from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "experiments" / "pilot" / "schemas"
HASH = "a" * 64


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def _minimal_research_run() -> dict:
    return {
        "schema_version": "1",
        "protocol_version": "0.4",
        "mode": "research",
        "research_candidate": True,
        "run_id": "research-test",
        "seed": 42,
        "code_hash": HASH,
        "config_hash": HASH,
        "input_hash": HASH,
        "fingerprint": HASH,
        "preflight_hash": HASH,
        "clean_pool_hash": HASH,
        "clean_resource_count": 457,
        "frozen_asset_hashes": {
            "appworld_runtime_snapshot_hash": HASH,
            "selection_contract_probe_hash": HASH,
        },
        "schedule_hash": HASH,
        "model_provenance": {"backend": "qwen3.8"},
        "appworld_provenance": {
            "backend": "appworld",
            "runtime_snapshot_hash": HASH,
            "runtime_snapshot_file_count": 123,
            "runtime_snapshot_size_bytes": 4567,
            "runtime_snapshot_claim": "byte_binding_not_publisher_authentication",
        },
    }


def _minimal_model_smoke_run() -> dict:
    return {
        "schema_version": "1",
        "protocol_version": "0.4",
        "mode": "synthetic_model_smoke",
        "research_candidate": False,
        "run_id": "synthetic-model-smoke",
        "seed": 42,
        "code_hash": HASH,
        "config_hash": HASH,
        "input_hash": HASH,
        "clean_pool_hash": HASH,
        "clean_resource_count": 457,
        "fixture_provenance": {
            "schema_version": "r2sp.fixture-provenance.v1",
            "source_type": "synthetic",
            "mode": "synthetic_smoke",
            "research_eligible": False,
            "purpose": "instrumentation_validation_only",
        },
        "model_provenance": {"backend": "qwen3.8"},
        "warning": "Synthetic model evidence is never research evidence.",
    }


class SchemaTests(unittest.TestCase):
    def test_checked_in_schemas_are_valid_draft_2020_12(self) -> None:
        for path in sorted(SCHEMA_ROOT.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))

    def test_case_and_overlay_schemas_pin_current_protocol(self) -> None:
        for name in ("cases.schema.json", "overlay-attestation.schema.json"):
            with self.subTest(schema=name):
                schema = _load_schema(name)
                self.assertEqual(schema["properties"]["protocol_version"]["const"], "0.4")

    def test_research_run_requires_both_appworld_snapshot_bindings(self) -> None:
        validator = Draft202012Validator(_load_schema("run-record.schema.json"))
        validator.validate(_minimal_research_run())

        missing_frozen_hash = deepcopy(_minimal_research_run())
        missing_frozen_hash["frozen_asset_hashes"].pop("appworld_runtime_snapshot_hash")
        with self.assertRaises(ValidationError):
            validator.validate(missing_frozen_hash)

        missing_provenance_hash = deepcopy(_minimal_research_run())
        missing_provenance_hash["appworld_provenance"].pop("runtime_snapshot_hash")
        with self.assertRaises(ValidationError):
            validator.validate(missing_provenance_hash)

        missing_selection_contract = deepcopy(_minimal_research_run())
        missing_selection_contract["frozen_asset_hashes"].pop("selection_contract_probe_hash")
        with self.assertRaises(ValidationError):
            validator.validate(missing_selection_contract)

    def test_model_backed_smoke_accepts_current_fixture_but_cannot_be_research_candidate(
        self,
    ) -> None:
        validator = Draft202012Validator(_load_schema("run-record.schema.json"))
        validator.validate(_minimal_model_smoke_run())

        mislabeled = deepcopy(_minimal_model_smoke_run())
        mislabeled["research_candidate"] = True
        with self.assertRaises(ValidationError):
            validator.validate(mislabeled)


if __name__ == "__main__":
    unittest.main()
