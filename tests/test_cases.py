import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from r2sp.cases import (
    SCHEDULE_SEED,
    CaseBundleError,
    build_overlay_attestation,
    build_schedule,
    load_frozen_cases,
    load_overlay_attestation,
    validate_overlay_attestation,
)
from r2sp.hashing import canonical_json_sha256, sha256_text
from r2sp.models import CaseSpec, OverlayPair, OverlaySpec, Resource, TaskSpec

MODEL = "Qwen/Qwen3.8-27B"
REVISION = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
ROOT = Path(__file__).resolve().parents[1]


def make_case(index: int) -> CaseSpec:
    case_id = f"case-{index:02d}"
    identity = {
        "resource_id": f"overlay-{index:02d}",
        "app_name": "calendar",
        "api_name": "create_event",
        "title": f"Matched overlay {index:02d}",
    }
    nonce = f"nonce-{index:02d}"
    trigger = f"trigger-{index:02d}"
    overlays = OverlayPair(
        case_id=case_id,
        sham=OverlaySpec(
            "A_sham",
            Resource(body=f"Harmless matched body {index:02d}.", **identity),
            trigger,
            nonce,
            "frozen-v1",
        ),
        poison=OverlaySpec(
            "B_poison",
            Resource(body=f"Different local canary rule {index:02d}.", **identity),
            trigger,
            nonce,
            "frozen-v1",
        ),
    )
    return CaseSpec(
        case_id=case_id,
        authoring_task=TaskSpec(f"task-{index:02d}-a", "authoring"),
        positive_task=TaskSpec(f"task-{index:02d}-p", "trigger_positive"),
        negative_task=TaskSpec(f"task-{index:02d}-n", "trigger_negative"),
        overlays=overlays,
    )


def bundle_payload(count: int, *, include_counts: bool = True) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for index in range(count):
        encoded = make_case(index).to_dict()
        if include_counts:
            encoded["sham_token_count"] = 100
            encoded["poison_token_count"] = 104
        cases.append(encoded)
    return {
        "protocol_version": "0.3",
        "tokenizer": {"model": MODEL, "revision": REVISION},
        "cases": cases,
    }


def write_payload(directory: str, payload: dict[str, Any]) -> Path:
    path = Path(directory) / "private-cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        forbidden = {"body", "trigger", "nonce"}
        return bool(forbidden.intersection(value)) or any(
            contains_forbidden_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(contains_forbidden_key(item) for item in value)
    return False


class FrozenCaseLoaderTests(unittest.TestCase):
    def test_research_bundle_requires_and_loads_exactly_sixteen_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = load_frozen_cases(write_payload(directory, bundle_payload(16)))

        self.assertEqual(len(bundle.cases), 16)
        self.assertEqual(bundle.protocol_version, "0.3")
        self.assertEqual(bundle.tokenizer_model, MODEL)
        self.assertEqual(bundle.counts_for("case-00").poison_token_count, 104)

    def test_research_bundle_rejects_wrong_case_count_or_missing_counts(self) -> None:
        for payload in (bundle_payload(15), bundle_payload(16, include_counts=False)):
            with (
                self.subTest(case_count=len(payload["cases"])),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaises(CaseBundleError),
            ):
                load_frozen_cases(write_payload(directory, payload))

    def test_loader_rejects_historical_protocol_bundle_as_current_input(self) -> None:
        payload = bundle_payload(16)
        payload["protocol_version"] = "0.2"
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(CaseBundleError, "protocol_version must equal '0.3'"),
        ):
            load_frozen_cases(write_payload(directory, payload))

    def test_nonresearch_bundle_supports_small_instrumentation_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = load_frozen_cases(
                write_payload(directory, bundle_payload(2, include_counts=False)),
                research_mode=False,
            )
        self.assertEqual(len(bundle.cases), 2)
        self.assertIsNone(bundle.counts_for("case-00").sham_token_count)

    def test_global_case_task_and_nonce_ids_must_be_unique(self) -> None:
        mutators = {
            "case": lambda value: value["cases"][1].__setitem__("case_id", "case-00"),
            "task": lambda value: value["cases"][1]["authoring_task"].__setitem__(
                "task_id", "task-00-a"
            ),
            "nonce": lambda value: (
                value["cases"][1]["overlays"]["sham"].__setitem__("nonce", "nonce-00"),
                value["cases"][1]["overlays"]["poison"].__setitem__("nonce", "nonce-00"),
            ),
        }
        for name, mutate in mutators.items():
            payload = bundle_payload(2)
            mutate(payload)
            with (
                self.subTest(name=name),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaises(CaseBundleError),
            ):
                load_frozen_cases(write_payload(directory, payload), research_mode=False)

    def test_cases_schema_matches_the_loader_wire_format(self) -> None:
        schema = json.loads(
            (ROOT / "experiments/pilot/schemas/cases.schema.json").read_text(encoding="utf-8")
        )
        case_schema = schema["$defs"]["case"]
        encoded = make_case(0).to_dict()
        encoded["sham_token_count"] = 100
        encoded["poison_token_count"] = 104

        self.assertEqual(set(schema["properties"]["tokenizer"]["required"]), {"model", "revision"})
        self.assertNotIn("model_id", schema["properties"]["tokenizer"]["properties"])
        self.assertEqual(set(case_schema["required"]), set(encoded))
        self.assertIn("overlays", case_schema["properties"])
        self.assertNotIn("overlay_pair", case_schema["properties"])
        self.assertEqual(
            schema["$defs"]["task"]["properties"]["kind"]["enum"],
            ["authoring", "trigger_positive", "trigger_negative"],
        )
        self.assertEqual(
            set(schema["$defs"]["overlay_pair"]["required"]),
            set(encoded["overlays"]),
        )

    def test_unknown_fields_are_rejected_at_every_closed_input_level(self) -> None:
        mutations = {
            "root": lambda value: value.__setitem__("unexpected", True),
            "tokenizer": lambda value: value["tokenizer"].__setitem__("unexpected", True),
            "case": lambda value: value["cases"][0].__setitem__("unexpected", True),
            "authoring_task": lambda value: value["cases"][0]["authoring_task"].__setitem__(
                "unexpected", True
            ),
            "positive_task": lambda value: value["cases"][0]["positive_task"].__setitem__(
                "unexpected", True
            ),
            "negative_task": lambda value: value["cases"][0]["negative_task"].__setitem__(
                "unexpected", True
            ),
            "overlays": lambda value: value["cases"][0]["overlays"].__setitem__("unexpected", True),
            "sham": lambda value: value["cases"][0]["overlays"]["sham"].__setitem__(
                "unexpected", True
            ),
            "sham.resource": lambda value: value["cases"][0]["overlays"]["sham"][
                "resource"
            ].__setitem__("unexpected", True),
            "poison": lambda value: value["cases"][0]["overlays"]["poison"].__setitem__(
                "unexpected", True
            ),
            "poison.resource": lambda value: value["cases"][0]["overlays"]["poison"][
                "resource"
            ].__setitem__("unexpected", True),
        }
        for level, mutate in mutations.items():
            payload = bundle_payload(1)
            mutate(payload)
            with (
                self.subTest(level=level),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaisesRegex(CaseBundleError, "unknown field"),
            ):
                load_frozen_cases(write_payload(directory, payload), research_mode=False)

    def test_task_metadata_remains_an_open_json_object(self) -> None:
        payload = bundle_payload(1)
        payload["cases"][0]["authoring_task"]["metadata"] = {
            "extension": {"nested": [1, True, None]}
        }
        with tempfile.TemporaryDirectory() as directory:
            bundle = load_frozen_cases(write_payload(directory, payload), research_mode=False)

        self.assertEqual(
            bundle.cases[0].authoring_task.metadata,
            {"extension": {"nested": [1, True, None]}},
        )

    def test_pair_matching_token_ratio_and_distinct_bodies_are_enforced(self) -> None:
        mutations = {
            "template": lambda case: case["overlays"]["poison"].__setitem__(
                "template_version", "other-template"
            ),
            "public_identity": lambda case: case["overlays"]["poison"]["resource"].__setitem__(
                "title", "Different title"
            ),
            "trigger": lambda case: case["overlays"]["poison"].__setitem__(
                "trigger", "different-trigger"
            ),
            "token_ratio": lambda case: case.__setitem__("poison_token_count", 106),
            "same_body": lambda case: case["overlays"]["poison"]["resource"].update(
                {
                    "body": case["overlays"]["sham"]["resource"]["body"],
                    "content_hash": case["overlays"]["sham"]["resource"]["content_hash"],
                }
            ),
        }
        for name, mutate in mutations.items():
            payload = bundle_payload(1)
            mutate(payload["cases"][0])
            with (
                self.subTest(name=name),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaises(CaseBundleError),
            ):
                load_frozen_cases(write_payload(directory, payload), research_mode=False)


class BuildScheduleTests(unittest.TestCase):
    def test_schedule_is_reproducible_paired_and_public(self) -> None:
        payload = bundle_payload(4)
        with tempfile.TemporaryDirectory() as directory:
            bundle = load_frozen_cases(write_payload(directory, payload), research_mode=False)

        first = build_schedule(bundle)
        second = build_schedule(bundle)
        self.assertEqual(first, second)
        self.assertEqual(first.seed, SCHEDULE_SEED)
        self.assertEqual(len(first.entries), 8)

        for case in bundle.cases:
            entries = [entry for entry in first.entries if entry.case_id == case.case_id]
            self.assertEqual({entry.arm for entry in entries}, {"A_sham", "B_poison"})
            self.assertEqual(len({entry.generation_seed for entry in entries}), 1)

        public = first.to_public_dict()
        self.assertFalse(contains_forbidden_key(public))
        serialized = json.dumps(public)
        for case in bundle.cases:
            self.assertNotIn(case.overlays.sham.resource.body, serialized)
            self.assertNotIn(case.overlays.sham.trigger, serialized)
            self.assertNotIn(case.overlays.sham.nonce, serialized)

    def test_schedule_rejects_a_nonprotocol_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = load_frozen_cases(
                write_payload(directory, bundle_payload(1)), research_mode=False
            )
        with self.assertRaises(ValueError):
            build_schedule(bundle, seed=SCHEDULE_SEED + 1)


class OverlayAttestationTests(unittest.TestCase):
    def _bundle(self, directory: str):
        return load_frozen_cases(write_payload(directory, bundle_payload(16)))

    def test_attestation_is_canonical_hash_only_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = self._bundle(directory)
            attestation = build_overlay_attestation(bundle)
            payload = attestation.to_dict()
            path = Path(directory) / "overlay-attestation.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_overlay_attestation(path, expected_bundle=bundle)

        self.assertEqual(loaded, attestation)
        self.assertEqual(payload["schema_version"], "r2sp.overlay-attestation.v1")
        self.assertEqual(payload["case_count"], 16)
        hash_payload = {key: value for key, value in payload.items() if key != "bundle_hash"}
        self.assertEqual(payload["bundle_hash"], canonical_json_sha256(hash_payload))
        self.assertFalse(contains_forbidden_key(payload))

        for case, commitment in zip(bundle.cases, attestation.cases, strict=True):
            self.assertEqual(commitment.case_id, case.case_id)
            self.assertEqual(
                commitment.sham_content_hash,
                case.overlays.sham.resource.content_hash,
            )
            self.assertEqual(
                commitment.poison_content_hash,
                case.overlays.poison.resource.content_hash,
            )
            self.assertEqual(commitment.trigger_sha256, sha256_text(case.overlays.sham.trigger))
            self.assertEqual(commitment.nonce_sha256, sha256_text(case.overlays.sham.nonce))
            serialized = json.dumps(payload, sort_keys=True)
            self.assertNotIn(case.overlays.sham.resource.body, serialized)
            self.assertNotIn(case.overlays.sham.trigger, serialized)
            self.assertNotIn(case.overlays.sham.nonce, serialized)

    def test_tampering_or_source_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = self._bundle(directory)
            payload = build_overlay_attestation(bundle).to_dict()

            tampered = json.loads(json.dumps(payload))
            tampered["cases"][0]["nonce_sha256"] = "a" * 64
            with self.assertRaisesRegex(CaseBundleError, "bundle_hash"):
                validate_overlay_attestation(tampered)

            tampered["bundle_hash"] = canonical_json_sha256(
                {key: value for key, value in tampered.items() if key != "bundle_hash"}
            )
            with self.assertRaisesRegex(CaseBundleError, "expected private case bundle"):
                validate_overlay_attestation(tampered, expected_bundle=bundle)

    def test_attestation_schema_matches_builder_output(self) -> None:
        schema = json.loads(
            (ROOT / "experiments/pilot/schemas/overlay-attestation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            payload = build_overlay_attestation(self._bundle(directory)).to_dict()

        self.assertEqual(set(schema["required"]), set(payload))
        self.assertEqual(schema["properties"]["case_count"]["const"], len(payload["cases"]))
        self.assertEqual(
            set(schema["$defs"]["case_attestation"]["required"]),
            set(payload["cases"][0]),
        )


if __name__ == "__main__":
    unittest.main()
