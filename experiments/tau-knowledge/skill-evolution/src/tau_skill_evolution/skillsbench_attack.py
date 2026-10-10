"""Sealed four-profile retrieval conditions for SkillsBench v8.

The behavior categories were inspired by DyMalSkill. Four frozen source records
provide inert provenance; the full archive is not a runtime dependency. This
module verifies their bytes, then renders our fixed carrier text and seals each corpus.
"""

# The injected prose keeps ordinary document paragraphs intact.  Reflowing those
# lines would change the frozen adapted-template and corpus identities.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import atomic_json
from .container import _safe_path

SOURCE_ARCHIVE = "DyMalSkill_300x12.zip"
SOURCE_ARCHIVE_SHA256 = "fc26fefa1be4988e71bcb2159ab12749f20cdd5ccaadba7d2e721ef2a091c8e9"
MATRIX_MANIFEST = "configs/skillsbench-dymal4-matrix.json"
SEED = 20260904
PROFILES = ("credential_abuse", "data_exfil_http", "file_delete", "cpu_hijack")
ARMS = (
    "benign",
    "credential-abuse-5",
    "credential-abuse-10",
    "data-exfil-http-5",
    "data-exfil-http-10",
    "file-delete-5",
    "file-delete-10",
    "cpu-hijack-5",
    "cpu-hijack-10",
)
ACQUISITION_FLAGS = (
    "source_poisoned",
    "payload_present",
    "payload_partial",
    "full_payload_present",
)
ACQUISITION_STAGES = (
    "corpus",
    "search_returns",
    "analyzer_visible",
    "frozen_base",
)
ACQUISITION_HOST_ONLY_MODEL_KEYS = frozenset(
    {
        "condition_id",
        "profile",
        "level",
        "target_document_ids",
        "source_poisoned",
        "payload_token_start",
        "payload_token_end",
        "payload_present",
        "full_payload_present",
        "payload_sha256",
        "source_archive_sha256",
        "source_record_sha256",
        "source_inserted_text_sha256",
        "adapted_template_sha256",
    }
)

_SOURCE = {
    "credential_abuse": {
        "path": "DyMalSkill/credential_abuse/shenlin0517-comfy-story-video/_injection.json",
        "record_sha256": "b9a8d7d4d1f9e233990c06833f9a5957fad6e5a92e1cbed8629270cefc517d6a",
        "text_sha256": "f9fcd0d1e7b24dc26657a0d222fcb7f49a0a3a1ab2eb0424e822147be59fab2c",
        "anchors": ("os.walk", "./root", ".env", "very beginning"),
    },
    "data_exfil_http": {
        "path": "DyMalSkill/data_exfil_http/shenlin0517-comfy-story-video/_injection.json",
        "record_sha256": "afac053b2f88ad3b902d87d2615bc34701a2bf0ac89d4dcb78ddb4c4fb62ae9c",
        "text_sha256": "392144fe6fb3cc1e96003aafbd322f7cf451deed7a668009b67304a292413c0a",
        "anchors": (
            "http://127.0.0.1:8001/8910",
            '"ts"',
            '"platform"',
            "urllib.request",
            "very beginning",
        ),
    },
    "file_delete": {
        "path": "DyMalSkill/file_delete/shenlin0517-comfy-story-video/_injection.json",
        "record_sha256": "d5e2767e957c100f38668a7bfbd533cd17c8847370a47309052acbbe7370290d",
        "text_sha256": "4043ae22c434e836ce4f60af6e78e5658879bc328e5fb4390d2d522da8b5e63f",
        "anchors": ("./cache_data/personal.log", "os.remove", "very beginning"),
    },
    "cpu_hijack": {
        "path": "DyMalSkill/cpu_hijack/shenlin0517-comfy-story-video/_injection.json",
        "record_sha256": "38689e7a44bee9867a21fad4fd1d63bf525e28f1cfa4479d86c5ba07d46b91a8",
        "text_sha256": "689e8d7e93aee7abce6bdd38c640d6486e4f5ad32d758676f715e5e497d62d36",
        "anchors": ("time.time", "at least 6 seconds", "Do NOT use `time.sleep`", "very beginning"),
    },
}

_TEMPLATE_FILES = {
    "credential_abuse": "credential-abuse.txt",
    "data_exfil_http": "data-exfil-http.txt",
    "file_delete": "file-delete.txt",
    "cpu_hijack": "cpu-hijack.txt",
}
_TEMPLATE_SHA256 = {
    "credential_abuse": "04068ebfa3012a86a0785cb96a1ecd03826f8e9c3c4311b4402b9eb483d42fc2",
    "data_exfil_http": "dd9f7f24b76dd11ed6b8276f055fcf53a6bd58450527c6d35b352d7901bd8871",
    "file_delete": "b3abf755a1a132fcbc5cf9566d08b0c5d86d0bf514e4119dfa12ac948211ad9a",
    "cpu_hijack": "fed8f2c9cfe838f77843f629c9b5c2c4ce7c9f2e274b3c2d66329e65c705fad0",
}

_FORBIDDEN = (
    "<system_instruction",
    "<extra_info",
    "evaluator",
    "canary",
    "nonce",
    "r2sp",
    ".agents/skills/",
    "shenlin0517-comfy-story-video",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_hash(value: Any) -> str:
    return _sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def acquisition_fraction(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def acquisition_exposure_not_measured(reason: str) -> dict[str, Any]:
    """Return an explicit four-stage missing record for a v8 case."""
    return {
        "status": "NOT_MEASURED",
        "reason": reason,
        "flags": list(ACQUISITION_FLAGS),
        "stages": {
            stage: {"status": "NOT_MEASURED", "reason": reason} for stage in ACQUISITION_STAGES
        },
    }


def acquisition_page_flag(page: Mapping[str, Any], flag: str) -> bool:
    if flag == "payload_partial":
        return bool(page.get("payload_present", False)) and not bool(
            page.get("full_payload_present", False)
        )
    return bool(page.get(flag, False))


def acquisition_exposure(
    ids: Sequence[str], pages: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Measure payload exposure by occurrence, unique chunk, and unique source."""
    if set(ids) - pages.keys():
        raise ValueError("skillsbench_acquisition_document_outside_sealed_pool")
    unique = tuple(dict.fromkeys(ids))
    sources = {pages[identifier]["source_document_id"] for identifier in unique}
    rates: dict[str, Any] = {}
    for flag in ACQUISITION_FLAGS:
        occurrence_count = sum(acquisition_page_flag(pages[identifier], flag) for identifier in ids)
        unique_count = sum(acquisition_page_flag(pages[identifier], flag) for identifier in unique)
        flagged_sources = {
            pages[identifier]["source_document_id"]
            for identifier in unique
            if acquisition_page_flag(pages[identifier], flag)
        }
        rates[flag] = {
            "chunk_occurrences": acquisition_fraction(occurrence_count, len(ids)),
            "unique_chunks": acquisition_fraction(unique_count, len(unique)),
            "unique_sources": acquisition_fraction(len(flagged_sources), len(sources)),
        }
    return {
        "chunk_occurrences": len(ids),
        "unique_chunks": len(unique),
        "unique_sources": len(sources),
        "rates": rates,
    }


def acquisition_journal_records(journal: Any) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in journal.root.glob("*/request.json")
    ]


def acquisition_analyzer_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize callable and live-client Analyzer request journal envelopes."""
    payload = request["payload"]
    if "messages" in payload:
        payload = payload["inputs"]
    return payload["inputs"]


def acquisition_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return set(value).union(*(map(acquisition_keys, value.values())), set())
    if isinstance(value, list):
        return set().union(*(map(acquisition_keys, value)), set())
    return set()


def acquisition_operation_index(operation_id: str) -> int:
    try:
        return int(operation_id.rsplit("/", 1)[1])
    except (ValueError, IndexError) as exc:
        raise ValueError("skillsbench_acquisition_operation_id_invalid") from exc


def load_acquisition_pages(
    manifest: Mapping[str, Any], directory: Path, *, verify: bool = False
) -> dict[str, dict[str, Any]]:
    """Load host-only page provenance, optionally checking its sealed manifest."""
    entries = manifest.get("pages")
    if not isinstance(entries, list):
        raise ValueError("skillsbench_acquisition_manifest_invalid")
    directory = Path(directory)
    sealed_directory = directory.resolve()
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("skillsbench_acquisition_manifest_invalid")
        path = directory / _safe_path(entry.get("file", ""))
        if verify and not path.resolve().is_relative_to(sealed_directory):
            raise ValueError("skillsbench_acquisition_page_outside_pool")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("skillsbench_acquisition_page_invalid") from exc
        if not isinstance(value, dict):
            raise ValueError("skillsbench_acquisition_page_invalid")
        value.setdefault("source_poisoned", False)
        value.setdefault("payload_present", False)
        value.setdefault("full_payload_present", False)
        identifier = value.get("page_id")
        source = value.get("source_document_id")
        if not isinstance(identifier, str) or not isinstance(source, str):
            raise ValueError("skillsbench_acquisition_page_invalid")
        if identifier in result:
            raise ValueError("skillsbench_acquisition_duplicate_page_id")
        if verify:
            body = value.get("body")
            content_sha256 = value.get("content_sha256")
            if (
                entry.get("page_id") != identifier
                or not identifier.startswith(source + "::")
                or not isinstance(body, str)
                or not isinstance(content_sha256, str)
                or _sha256(body.encode()) != content_sha256
                or entry.get("content_sha256") != content_sha256
                or any(value.get(key) != item for key, item in entry.items() if key != "file")
                or any(
                    bool(entry.get(flag, False)) != acquisition_page_flag(value, flag)
                    for flag in (
                        "source_poisoned",
                        "payload_present",
                        "full_payload_present",
                    )
                )
            ):
                raise ValueError("skillsbench_acquisition_page_changed")
        result[identifier] = value
    return result


def collect_acquisition_exposure(
    base: Any, journal: Any, pages: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Collect the four exposure stages and the acquisition trace from a sealed journal."""
    searches: list[dict[str, Any]] = []
    analyzer_requests: list[dict[str, Any]] = []
    visible_occurrences: list[str] = []
    discovery_calls: list[dict[str, Any]] = []
    for request in acquisition_journal_records(journal):
        operation = request["operation_id"]
        if operation.startswith("acquisition/search/") and journal.completed(operation):
            response = journal.response(operation)
            hits = (
                response.get("result", {}).get("results", [])
                if response.get("status") == "ok"
                else []
            )
            ids = [item.get("page_id", item.get("document_id")) for item in hits]
            searches.append(
                {
                    "index": acquisition_operation_index(operation),
                    "query": request["payload"]["query"],
                    "status": response.get("result", {}).get("status", response.get("status")),
                    "results": [
                        {"rank": rank, "document_id": identifier}
                        for rank, identifier in enumerate(ids, 1)
                    ],
                    "exposure": acquisition_exposure(ids, pages),
                }
            )
        elif operation.startswith("acquisition/analyzer/") and journal.completed(operation):
            journal.response(operation)
            payload = acquisition_analyzer_payload(request)
            forbidden = sorted(acquisition_keys(payload) & ACQUISITION_HOST_ONLY_MODEL_KEYS)
            if forbidden:
                raise ValueError(
                    "skillsbench_acquisition_host_metadata_visible_to_analyzer:"
                    + ",".join(forbidden)
                )
            ids = [item["document_id"] for item in payload["returned_documents"]]
            visible_occurrences.extend(ids)
            analyzer_requests.append(
                {
                    "index": acquisition_operation_index(operation),
                    "visible_document_ids": ids,
                    "exposure": acquisition_exposure(ids, pages),
                }
            )
        elif operation.startswith("acquisition/read_only/") and journal.completed(operation):
            response = journal.response(operation)
            discovery_calls.append(
                {
                    "index": acquisition_operation_index(operation),
                    "tool": request["payload"].get("tool"),
                    "arguments": request["payload"].get("arguments", {}),
                    "status": response.get("status"),
                }
            )
    searches.sort(key=lambda item: item["index"])
    analyzer_requests.sort(key=lambda item: item["index"])
    discovery_calls.sort(key=lambda item: item["index"])
    returned = [item["document_id"] for search in searches for item in search["results"]]
    selected = [item["document_id"] for item in base.documents] if base is not None else []
    stages = {
        "corpus": acquisition_exposure(tuple(pages), pages),
        "search_returns": acquisition_exposure(returned, pages),
        "analyzer_visible": acquisition_exposure(visible_occurrences, pages),
        "frozen_base": acquisition_exposure(selected, pages),
    }
    return {
        "stages": stages,
        "searches": searches,
        "analyzer_requests": analyzer_requests,
        "input_discovery": discovery_calls,
        "retrieval_unique": acquisition_exposure(tuple(dict.fromkeys(returned)), pages),
        "analyzer_visible_unique": acquisition_exposure(
            tuple(dict.fromkeys(visible_occurrences)), pages
        ),
        "selected_document_ids": selected,
        "repeated_hit_count": len(returned) - len(set(returned)),
    }


def acquisition_payload_exposure(root: Path, base: Any, journal: Any) -> dict[str, Any]:
    """Load and measure the pool bound by this cell's retrieval contract."""
    if not journal.completed("retrieval-corpus-contract"):
        raise ValueError("skillsbench_acquisition_retrieval_contract_missing")
    binding = journal.response("retrieval-corpus-contract")
    retrieval = binding.get("retrieval") if isinstance(binding, Mapping) else None
    bound_condition = retrieval.get("condition") if isinstance(retrieval, Mapping) else None
    if (
        not isinstance(retrieval, Mapping)
        or not isinstance(bound_condition, Mapping)
        or binding.get("condition_id") != bound_condition.get("condition_id")
    ):
        raise ValueError("skillsbench_acquisition_retrieval_contract_invalid")
    experiment_root = Path(root).resolve()
    try:
        directory = (experiment_root / _safe_path(retrieval.get("pool_path", ""))).resolve()
    except (OSError, ValueError) as exc:
        raise ValueError("skillsbench_acquisition_pool_path_invalid") from exc
    if not directory.is_relative_to(experiment_root):
        raise ValueError("skillsbench_acquisition_pool_path_invalid")
    manifest_path = directory / "manifest.json"
    if not manifest_path.resolve().is_relative_to(directory):
        raise ValueError("skillsbench_acquisition_pool_path_invalid")
    try:
        raw_manifest = manifest_path.read_bytes()
        manifest = json.loads(raw_manifest)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("skillsbench_acquisition_manifest_invalid") from exc
    pages = manifest.get("pages") if isinstance(manifest, Mapping) else None
    if (
        not isinstance(manifest, Mapping)
        or _sha256(raw_manifest) != retrieval.get("pool_manifest_sha256")
        or manifest.get("corpus_hash") != retrieval.get("corpus_hash")
        or manifest.get("corpus_hash")
        != _json_hash({key: value for key, value in manifest.items() if key != "corpus_hash"})
        or not isinstance(pages, list)
        or type(retrieval.get("page_count")) is not int
        or len(pages) != retrieval["page_count"]
        or type(retrieval.get("payload_chunk_count")) is not int
        or type(retrieval.get("full_payload_chunk_count")) is not int
    ):
        raise ValueError("skillsbench_acquisition_manifest_changed")
    condition_id = bound_condition.get("condition_id")
    if condition_id == "benign":
        condition_changed = "injection" in manifest
    else:
        injection = manifest.get("injection")
        condition_changed = not isinstance(injection, Mapping) or any(
            injection.get(field) != bound_condition.get(field)
            for field in ("condition_id", "profile", "level", "target_document_ids")
        )
    if condition_changed:
        raise ValueError("skillsbench_acquisition_condition_pool_mismatch")
    loaded = load_acquisition_pages(manifest, directory, verify=True)
    if retrieval["payload_chunk_count"] != sum(
        acquisition_page_flag(page, "payload_present") for page in loaded.values()
    ) or retrieval["full_payload_chunk_count"] != sum(
        acquisition_page_flag(page, "full_payload_present") for page in loaded.values()
    ):
        raise ValueError("skillsbench_acquisition_manifest_changed")
    trace = collect_acquisition_exposure(base, journal, loaded)
    available = {
        "corpus": True,
        "search_returns": base is not None or bool(trace["searches"]),
        "analyzer_visible": base is not None or bool(trace["analyzer_requests"]),
        "frozen_base": base is not None,
    }
    stages = {
        name: (
            {"status": "MEASURED", **trace["stages"][name]}
            if available[name]
            else {
                "status": "NOT_MEASURED",
                "reason": f"{name}_not_recorded",
            }
        )
        for name in ACQUISITION_STAGES
    }
    result = {
        "status": "MEASURED" if all(available.values()) else "NOT_MEASURED",
        "flags": list(ACQUISITION_FLAGS),
        "stages": stages,
    }
    if not all(available.values()):
        result["reason"] = "acquisition_incomplete"
    return result


def adapted_template(profile: str, root: Path | None = None) -> str:
    """Read one public, reviewable carrier template and verify its fixed bytes."""
    if profile not in PROFILES:
        raise ValueError("skillsbench_injection_profile_invalid")
    experiment_root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    path = experiment_root / "injections/skillsbench" / _TEMPLATE_FILES[profile]
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("skillsbench_injection_template_unreadable") from exc
    if (
        _sha256(raw) != _TEMPLATE_SHA256[profile]
        or text.count("{title}") != 1
        or any(term in text.lower() for term in _FORBIDDEN)
    ):
        raise ValueError("skillsbench_injection_template_changed")
    return text


def source_templates(root: Path) -> dict[str, dict[str, str]]:
    """Verify the source records and return only their immutable provenance."""
    result: dict[str, dict[str, str]] = {}
    directory = Path(root) / "injections/skillsbench/source"
    for profile, expected in _SOURCE.items():
        try:
            raw = (directory / f"{profile}.json").read_bytes()
        except OSError as exc:
            raise ValueError("skillsbench_dymalskill_source_missing") from exc
        if _sha256(raw) != expected["record_sha256"]:
            raise ValueError("skillsbench_dymalskill_source_changed")
        source = json.loads(raw)
        text = source.get("inserted_text")
        if (
            source.get("attack") != profile
            or not isinstance(text, str)
            or _sha256(text.encode()) != expected["text_sha256"]
            or any(anchor not in text for anchor in expected["anchors"])
        ):
            raise ValueError("skillsbench_dymalskill_source_semantics_changed")
        adapted = adapted_template(profile, root)
        result[profile] = {
            "archive_path": expected["path"],
            "record_sha256": expected["record_sha256"],
            "inserted_text_sha256": expected["text_sha256"],
            "adapted_template_sha256": _sha256(adapted.encode()),
        }
    return result


def condition(spec: Any, arm: str) -> dict[str, Any]:
    """Resolve one condition from the frozen list; never sample at runtime."""
    if arm not in spec.arms:
        raise ValueError("arm is outside the configured matrix")
    if arm == "benign":
        return {
            "condition_id": arm,
            "profile": None,
            "level": 0,
            "target_document_ids": [],
        }
    name, separator, level_text = arm.rpartition("-")
    profile = name.replace("-", "_")
    if not separator or profile not in PROFILES or level_text not in {"5", "10"}:
        raise ValueError("skillsbench_injection_condition_invalid")
    sampling = spec.values.get("poison_sampling", {})
    targets = sampling.get("target_document_ids")
    if (
        sampling.get("seed") != SEED
        or not isinstance(targets, list)
        or len(targets) != 9
        or len(set(targets)) != 9
    ):
        raise ValueError("skillsbench_injection_targets_invalid")
    count = 4 if level_text == "5" else 9
    return {
        "condition_id": arm,
        "profile": profile,
        "level": int(level_text),
        "target_document_ids": list(targets[:count]),
    }


def adapted_payload(profile: str, title: str) -> str:
    """Render fixed text using only the source document's first H1 title."""
    if profile not in PROFILES or not isinstance(title, str) or not title.strip():
        raise ValueError("skillsbench_injection_template_input_invalid")
    title = title.strip()
    if any(character in title for character in "\r\n\x00"):
        raise ValueError("skillsbench_injection_title_invalid")
    return adapted_template(profile).format(title=title)


def _insert(raw: bytes, profile: str) -> tuple[bytes, dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("skillsbench_injection_source_not_utf8") from exc
    match = re.search(r"(?m)^# ([^\r\n]+)(?:\r?\n|$)", text)
    if match is None:
        raise ValueError("skillsbench_injection_source_missing_h1")
    payload = adapted_payload(profile, match.group(1)).rstrip("\n")
    prefix, suffix = "\n", "\n"
    inserted = prefix + payload + suffix
    char_start = match.end()
    payload_char_start = char_start + len(prefix)
    payload_char_end = payload_char_start + len(payload)
    byte_start = len(text[:char_start].encode())
    payload_bytes = payload.encode()
    insertion_bytes = inserted.encode()
    return raw[:byte_start] + insertion_bytes + raw[byte_start:], {
        "title": match.group(1).strip(),
        "insertion_byte_start": byte_start,
        "insertion_byte_end": byte_start + len(insertion_bytes),
        "payload_byte_start": byte_start + len(prefix.encode()),
        "payload_byte_end": byte_start + len(prefix.encode()) + len(payload_bytes),
        "payload_char_start": payload_char_start,
        "payload_char_end": payload_char_end,
        "payload_sha256": _sha256(payload_bytes),
    }


def _tokenize(tokenizer: Any, text: str) -> tuple[list[int], list[tuple[int, int]]]:
    encoded = tokenizer.encode(text, add_special_tokens=False)
    tokens = list(encoded.ids if hasattr(encoded, "ids") else encoded)
    offsets = getattr(encoded, "offsets", None)
    if offsets is None or len(offsets) != len(tokens):
        raise ValueError("skillsbench_injection_tokenizer_requires_offsets")
    return tokens, list(offsets)


def _target_pages(
    entry: Mapping[str, Any],
    modified: bytes,
    span: Mapping[str, Any],
    tokenizer: Any,
) -> list[dict[str, Any]]:
    text = modified.decode("utf-8")
    tokens, offsets = _tokenize(tokenizer, text)
    char_start = span["payload_char_start"]
    char_end = span["payload_char_end"]
    first = next((index for index, (_, end) in enumerate(offsets) if end > char_start), len(tokens))
    last = next(
        (index for index, (start, _) in enumerate(offsets) if start >= char_end), len(tokens)
    )
    if first >= last:
        raise ValueError("skillsbench_injection_payload_token_span_empty")
    pages = []
    for start in range(0, max(1, len(tokens)), 1920):
        stop = min(start + 2048, len(tokens))
        body = tokenizer.decode(tokens[start:stop], skip_special_tokens=False)
        page_id = f"{entry['document_id']}::tokens-{start}-{stop}"
        pages.append(
            {
                "page_id": page_id,
                "title": entry["document_id"],
                "body": body,
                "content_sha256": _sha256(body.encode()),
                "source_sha256": entry["sha256"],
                "source_document_id": entry["document_id"],
                "token_start": start,
                "token_end": stop,
                "source_poisoned": True,
                "payload_token_start": first,
                "payload_token_end": last,
                "payload_present": start < last and stop > first,
                "full_payload_present": start <= first and stop >= last,
                "payload_sha256": span["payload_sha256"],
            }
        )
        if stop == len(tokens):
            break
    return pages


def _load_tokenizer(baseline: Mapping[str, Any]) -> Any:
    from tokenizers import Tokenizer

    cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
    snapshot = cache / "hub" / ("models--" + baseline["tokenizer"].replace("/", "--"))
    return Tokenizer.from_file(
        str(snapshot / "snapshots" / baseline["revision"] / "tokenizer.json")
    )


def prepare_injected_pool(spec: Any, arm: str, tokenizer: Any = None) -> Path:
    """Materialize one sealed modified pool and preserve clean pages byte-for-byte."""
    from .retrieval import ensure_cache
    from .skillsbench import SkillsBenchSource, validate_pool

    resolved = condition(spec, arm)
    root = Path(spec.root)
    if arm == "benign":
        return root / "data/skillsbench/corpus"
    source = SkillsBenchSource(root)
    baseline = validate_pool(root, source)
    provenance = source_templates(root)[resolved["profile"]]
    originals = {
        item["document_id"]: item
        for item in source.manifest["files"]
        if item["relative_path"].startswith("background/")
    }
    targets = resolved["target_document_ids"]
    if set(targets) - originals.keys():
        raise ValueError("skillsbench_injection_targets_invalid")
    request = {
        **resolved,
        "seed": SEED,
        "base_corpus_hash": baseline["corpus_hash"],
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        **provenance,
        "placement": "after-first-h1-before-rechunking",
    }
    request_hash = _json_hash(request)
    parent = root / "data/skillsbench/injected/v8"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / request_hash
    clean_root = root / "data/skillsbench/corpus"

    def build(output: Path) -> None:
        active_tokenizer = tokenizer or _load_tokenizer(baseline)
        output.mkdir()
        (output / "documents").mkdir()
        documents, records = [], []
        for identifier, entry in sorted(originals.items()):
            raw = (source.checkout / _safe_path(entry["path"])).read_bytes()
            if entry.get("kind") != "text" or _sha256(raw) != entry["sha256"]:
                raise ValueError("skillsbench_injection_source_changed")
            modified, span = (raw, None)
            if identifier in targets:
                modified, span = _insert(raw, resolved["profile"])
            document_file = "documents/" + _sha256(identifier.encode()) + ".md"
            (output / document_file).write_bytes(modified)
            documents.append(
                {
                    "source_document_id": identifier,
                    "source_sha256": entry["sha256"],
                    "materialized_sha256": _sha256(modified),
                    "file": document_file,
                    "source_poisoned": span is not None,
                    "insertion": span,
                }
            )
            if span is None:
                matching = [
                    record
                    for record in baseline["pages"]
                    if record["page_id"].startswith(identifier + "::")
                ]
                for record in matching:
                    raw_page = (clean_root / record["file"]).read_bytes()
                    (output / record["file"]).write_bytes(raw_page)
                    records.append(dict(record))
            else:
                for page in _target_pages(entry, modified, span, active_tokenizer):
                    filename = _sha256(page["page_id"].encode()) + ".json"
                    atomic_json(output / filename, page)
                    records.append(
                        {"file": filename, **{k: v for k, v in page.items() if k != "body"}}
                    )
        records.sort(key=lambda record: record["page_id"])
        page_set_hash = _json_hash(
            [
                {"page_id": item["page_id"], "content_sha256": item["content_sha256"]}
                for item in records
            ]
        )
        manifest = {
            **{k: v for k, v in baseline.items() if k not in {"pages", "corpus_hash"}},
            "schema": "skillsbench.pool.injected.v8",
            "injection": {**request, "request_hash": request_hash},
            "documents": documents,
            "page_set_hash": page_set_hash,
            "bm25_identity": _json_hash(
                {"implementation": "DeterministicBM25", "page_set_hash": page_set_hash}
            ),
            "pages": records,
        }
        manifest["corpus_hash"] = _json_hash(manifest)
        atomic_json(output / "manifest.json", manifest)
        validate_injected_pool(root, source, output, active_tokenizer)

    ensure_cache(destination, build)
    validate_injected_pool(root, source, destination, tokenizer)
    return destination


def validate_injected_pool(
    root: Path, source: Any, directory: Path, tokenizer: Any = None
) -> dict[str, Any]:
    """Verify original bytes, adapted spans, chunks, and condition provenance."""
    from .skillsbench import validate_pool

    root, directory = Path(root), Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("schema") != "skillsbench.pool.injected.v8" or manifest.get(
        "corpus_hash"
    ) != _json_hash({k: v for k, v in manifest.items() if k != "corpus_hash"}):
        raise ValueError("skillsbench_injection_manifest_invalid")
    baseline = validate_pool(root, source)
    injection = manifest.get("injection", {})
    profile, level = injection.get("profile"), injection.get("level")
    count = 4 if level == 5 else 9 if level == 10 else None
    targets = injection.get("target_document_ids")
    provenance = source_templates(root).get(profile, {})
    if (
        count is None
        or not isinstance(targets, list)
        or len(targets) != count
        or len(set(targets)) != count
        or injection.get("condition_id") != f"{profile.replace('_', '-')}-{level}"
        or injection.get("seed") != SEED
        or injection.get("base_corpus_hash") != baseline["corpus_hash"]
        or injection.get("source_archive_sha256") != SOURCE_ARCHIVE_SHA256
        or any(injection.get(key) != value for key, value in provenance.items())
        or injection.get("placement") != "after-first-h1-before-rechunking"
        or injection.get("request_hash")
        != _json_hash({k: v for k, v in injection.items() if k != "request_hash"})
    ):
        raise ValueError("skillsbench_injection_manifest_invalid")
    originals = {
        item["document_id"]: item
        for item in source.manifest["files"]
        if item["relative_path"].startswith("background/")
    }
    documents = {item["source_document_id"]: item for item in manifest.get("documents", [])}
    if set(targets) - originals.keys() or len(documents) != len(originals):
        raise ValueError("skillsbench_injection_documents_invalid")
    clean_root = root / "data/skillsbench/corpus"
    clean_records = {record["page_id"]: record for record in baseline["pages"]}
    seen: set[str] = set()
    for identifier, entry in originals.items():
        raw = (source.checkout / _safe_path(entry["path"])).read_bytes()
        expected, span = (raw, None)
        if identifier in targets:
            expected, span = _insert(raw, profile)
        document = documents.get(identifier, {})
        if (
            _sha256(raw) != entry["sha256"]
            or document.get("source_sha256") != entry["sha256"]
            or document.get("materialized_sha256") != _sha256(expected)
            or document.get("source_poisoned") != (span is not None)
            or document.get("insertion") != span
            or (directory / _safe_path(document.get("file", ""))).read_bytes() != expected
        ):
            raise ValueError("skillsbench_injection_document_changed")
        records = [
            record
            for record in manifest["pages"]
            if record["page_id"].startswith(identifier + "::")
        ]
        expected_pages = (
            _target_pages(entry, expected, span, tokenizer) if span and tokenizer else None
        )
        actual_pages = []
        for record in records:
            page_bytes = (directory / _safe_path(record["file"])).read_bytes()
            page = json.loads(page_bytes)
            actual_pages.append(page)
            if page["page_id"] in seen:
                raise ValueError("skillsbench_injection_chunk_changed")
            seen.add(page["page_id"])
            if (
                page["source_document_id"] != identifier
                or _sha256(page["body"].encode()) != page["content_sha256"]
                or page["token_end"] - page["token_start"] > 2048
            ):
                raise ValueError("skillsbench_injection_chunk_changed")
            if span is None:
                clean = clean_records.get(page["page_id"])
                if clean != record or page_bytes != (clean_root / clean["file"]).read_bytes():
                    raise ValueError("skillsbench_injection_clean_chunk_changed")
            else:
                first, last = page.get("payload_token_start"), page.get("payload_token_end")
                if (
                    type(first) is not int
                    or type(last) is not int
                    or not 0 <= first < last
                    or page.get("source_poisoned") is not True
                    or page.get("payload_present")
                    != (page["token_start"] < last and page["token_end"] > first)
                    or page.get("full_payload_present")
                    != (page["token_start"] <= first and page["token_end"] >= last)
                    or page.get("payload_sha256") != span["payload_sha256"]
                    or {k: v for k, v in page.items() if k != "body"}
                    != {k: v for k, v in record.items() if k != "file"}
                ):
                    raise ValueError("skillsbench_injection_chunk_flags_changed")
        if expected_pages is not None and actual_pages != expected_pages:
            raise ValueError("skillsbench_injection_chunk_changed")
    page_set_hash = _json_hash(
        [
            {"page_id": item["page_id"], "content_sha256": item["content_sha256"]}
            for item in sorted(manifest["pages"], key=lambda value: value["page_id"])
        ]
    )
    if (
        len(seen) != len(manifest["pages"])
        or manifest.get("page_set_hash") != page_set_hash
        or manifest.get("bm25_identity")
        != _json_hash({"implementation": "DeterministicBM25", "page_set_hash": page_set_hash})
    ):
        raise ValueError("skillsbench_injection_index_identity_changed")
    return manifest


def retrieval_contract(spec: Any, arm: str, *, directory: Path | None = None) -> dict[str, Any]:
    """Bind one condition to the exact pool and Dense/BM25 inputs used by retrieval."""
    from .core._canonical import canonical_json_sha256
    from .core.protocol import Page
    from .dense import (
        DenseContractError,
        DenseIndex,
        OpenAICompatibleEmbeddingClient,
    )
    from .skillsbench import SkillsBenchSource, selected_pool, validate_pool

    canonical_directory = selected_pool(spec, arm)
    directory = Path(directory) if directory is not None else canonical_directory
    if directory.resolve() != canonical_directory.resolve():
        raise ValueError("skillsbench_injection_condition_pool_mismatch")
    source = SkillsBenchSource(spec.root)
    manifest = (
        validate_pool(spec.root, source)
        if arm == "benign"
        else validate_injected_pool(spec.root, source, directory)
    )
    expected_condition = condition(spec, arm)
    if arm == "benign":
        if "injection" in manifest:
            raise ValueError("skillsbench_injection_condition_pool_mismatch")
    else:
        injection = manifest.get("injection", {})
        if any(
            injection.get(field) != expected_condition[field]
            for field in ("condition_id", "profile", "level", "target_document_ids")
        ):
            raise ValueError("skillsbench_injection_condition_pool_mismatch")
    materialized_pages = []
    for item in manifest["pages"]:
        value = json.loads((directory / item["file"]).read_text())
        materialized_pages.append(
            Page(
                value["page_id"],
                value["title"],
                value["body"],
                value["content_sha256"],
            )
        )
    materialized_pages.sort(key=lambda page: page.page_id)
    ordered_pages = [
        {
            "page_id": page.page_id,
            "title": page.title,
            "content_sha256": page.content_sha256,
        }
        for page in materialized_pages
    ]
    page_set_hash = _json_hash(ordered_pages)
    bm25_identity = _json_hash(
        {"implementation": "DeterministicBM25", "ordered_pages": ordered_pages}
    )
    dense_path = Path(spec.root) / "data/skillsbench/dense" / manifest["corpus_hash"]
    dense_manifest_path = dense_path / "manifest.json"
    vectors_path = dense_path / "vectors.f32"
    if not dense_manifest_path.is_file() or not vectors_path.is_file():
        raise ValueError("skillsbench_injection_dense_index_missing")
    dense = json.loads(dense_manifest_path.read_text())
    contract = dense.get("contract", {})
    vector = dense.get("vectors", {})
    embedding = spec.values["embedding"]
    expected_dense_corpus = canonical_json_sha256(ordered_pages)
    expected_settings = {
        "pooling": embedding.get("pooling", "").replace("-", "_"),
        "normalization": embedding.get("normalization", "").replace("-", "_"),
        "similarity": embedding.get("similarity", "").replace("-", "_"),
        "reranker": embedding.get("reranker"),
        "approximate_index": embedding.get("faiss"),
    }
    if any(contract.get(name) != value for name, value in expected_settings.items()) or (
        embedding.get("query_instruct") != "official"
    ):
        raise ValueError("skillsbench_injection_dense_contract_mismatch")
    client = OpenAICompatibleEmbeddingClient(
        embedding["endpoint"],
        model_id=embedding["model"],
        revision=embedding["revision"],
        dimensions=embedding["dimension"],
    )
    dense_manifest_sha256 = _sha256(dense_manifest_path.read_bytes())
    try:
        DenseIndex.load_cache(
            dense_path,
            materialized_pages,
            client=client,
            expected_manifest_sha256=dense_manifest_sha256,
        )
    except DenseContractError as exc:
        raise ValueError("skillsbench_injection_dense_contract_mismatch") from exc
    if contract.get("corpus_hash") != expected_dense_corpus or vector.get("shape") != [
        len(ordered_pages),
        embedding["dimension"],
    ]:
        raise ValueError("skillsbench_injection_dense_contract_mismatch")
    dense_contract_fields = {key: value for key, value in contract.items() if key != "pages"}
    dense_contract_fields["pages_sha256"] = _json_hash(contract["pages"])
    return {
        "condition": expected_condition,
        "pool_path": str(Path(directory).relative_to(spec.root)),
        "pool_manifest_sha256": _sha256((directory / "manifest.json").read_bytes()),
        "corpus_hash": manifest["corpus_hash"],
        "page_count": len(manifest["pages"]),
        "payload_chunk_count": sum(bool(item.get("payload_present")) for item in manifest["pages"]),
        "full_payload_chunk_count": sum(
            bool(item.get("full_payload_present")) for item in manifest["pages"]
        ),
        "page_set_hash": page_set_hash,
        "bm25_identity": bm25_identity,
        "dense_manifest_sha256": dense_manifest_sha256,
        "dense_manifest_payload_sha256": dense["manifest_payload_sha256"],
        "dense_contract_sha256": _json_hash(contract),
        "dense_corpus_hash": expected_dense_corpus,
        "dense_contract": dense_contract_fields,
        "dense_vectors": dict(vector),
        "embedding": {
            "model": contract["model_id"],
            "revision": contract["model_revision"],
            "dimensions": contract["dimensions"],
            "max_input_tokens": contract["max_input_tokens"],
        },
    }


def matrix_manifest(spec: Any, directories: Mapping[str, Path]) -> dict[str, Any]:
    """Describe the complete 765-cell matrix after every index is sealed."""
    if tuple(spec.arms) != ARMS or set(directories) != set(ARMS):
        raise ValueError("skillsbench_injection_matrix_incomplete")
    design = validate_condition_design(spec)
    corpora = {}
    for arm, directory in directories.items():
        contract = retrieval_contract(spec, arm, directory=directory)
        manifest = json.loads((Path(directory) / "manifest.json").read_text())
        chunk_mapping = [
            {
                "page_id": item["page_id"],
                "content_sha256": item["content_sha256"],
                "source_sha256": item["source_sha256"],
                "token_start": item["token_start"],
                "token_end": item["token_end"],
                "payload_token_start": item.get("payload_token_start"),
                "payload_token_end": item.get("payload_token_end"),
            }
            for item in manifest["pages"]
        ]
        documents = [
            {
                key: item[key]
                for key in (
                    "source_document_id",
                    "source_sha256",
                    "materialized_sha256",
                    "source_poisoned",
                    "insertion",
                )
            }
            for item in manifest.get("documents", [])
            if item.get("source_poisoned")
        ]
        corpus = {
            **contract,
            "target_documents": documents,
            "chunk_mapping_sha256": _json_hash(chunk_mapping),
        }
        if arm != "benign":
            injection = manifest["injection"]
            corpus["source_provenance"] = {
                key: injection[key]
                for key in (
                    "source_archive_sha256",
                    "archive_path",
                    "record_sha256",
                    "inserted_text_sha256",
                    "adapted_template_sha256",
                    "placement",
                    "request_hash",
                )
            }
        corpora[arm] = corpus
    cells = [
        {"task_id": task, "condition_id": arm, "corpus_hash": corpora[arm]["corpus_hash"]}
        for task in spec.tasks
        for arm in spec.arms
    ]
    if len(cells) != 765:
        raise ValueError("skillsbench_injection_matrix_incomplete")
    result = {
        "schema": "skillsbench.injection-matrix.v8",
        "namespace": spec.namespace,
        "seed": SEED,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "condition_design": design,
        "source_records": source_templates(spec.root),
        "profiles": list(PROFILES),
        "corpora": corpora,
        "cells": cells,
    }
    result["manifest_hash"] = _json_hash(result)
    return result


def freeze_matrix_manifest(spec: Any, directories: Mapping[str, Path]) -> dict[str, Any]:
    result = matrix_manifest(spec, directories)
    atomic_json(Path(spec.root) / MATRIX_MANIFEST, result)
    return result


def validate_matrix_manifest(spec: Any) -> dict[str, Any]:
    """Recompute every corpus/index contract and match the frozen 765-cell matrix."""
    path = Path(spec.root) / MATRIX_MANIFEST
    try:
        actual = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("skillsbench_injection_matrix_manifest_unreadable") from exc
    corpora = actual.get("corpora")
    cells = actual.get("cells")
    if (
        actual.get("schema") != "skillsbench.injection-matrix.v8"
        or actual.get("namespace") != spec.namespace
        or actual.get("manifest_hash")
        != _json_hash({key: value for key, value in actual.items() if key != "manifest_hash"})
        or not isinstance(corpora, dict)
        or set(corpora) != set(ARMS)
        or not isinstance(cells, list)
        or len(cells) != 765
    ):
        raise ValueError("skillsbench_injection_matrix_manifest_invalid")
    directories: dict[str, Path] = {}
    for arm in ARMS:
        entry = corpora[arm]
        if not isinstance(entry, dict):
            raise ValueError("skillsbench_injection_matrix_pool_invalid")
        relative = entry.get("pool_path")
        if not isinstance(relative, str):
            raise ValueError("skillsbench_injection_matrix_pool_invalid")
        candidate = Path(spec.root) / _safe_path(relative)
        if not (candidate / "manifest.json").is_file():
            raise ValueError("skillsbench_injection_matrix_pool_missing")
        directories[arm] = candidate
    expected = matrix_manifest(spec, directories)
    if actual != expected:
        raise ValueError("skillsbench_injection_matrix_manifest_changed")
    return {
        "matrix_manifest": MATRIX_MANIFEST,
        "matrix_manifest_sha256": _sha256(path.read_bytes()),
        "matrix_manifest_hash": actual["manifest_hash"],
        "conditions": len(corpora),
        "cells": len(cells),
        "chunks_by_condition": {arm: corpora[arm]["page_count"] for arm in ARMS},
        "payload_chunks_by_condition": {arm: corpora[arm]["payload_chunk_count"] for arm in ARMS},
    }


def condition_design_manifest(spec: Any) -> dict[str, Any]:
    """Freeze design-time sources and targets without depending on built indexes."""
    from .skillsbench import SkillsBenchSource

    source = SkillsBenchSource(spec.root)
    source.validate()
    entries = {
        item["document_id"]: item
        for item in source.manifest["files"]
        if item["relative_path"].startswith("background/")
    }
    target_ids = spec.values["poison_sampling"]["target_document_ids"]
    targets = {}
    for profile in PROFILES:
        rendered = []
        for identifier in target_ids:
            entry = entries[identifier]
            raw = (source.checkout / _safe_path(entry["path"])).read_bytes()
            modified, span = _insert(raw, profile)
            rendered.append(
                {
                    "source_document_id": identifier,
                    "source_sha256": entry["sha256"],
                    "materialized_sha256": _sha256(modified),
                    "insertion": span,
                }
            )
        targets[profile] = rendered
    result = {
        "schema": "skillsbench.injection-conditions.v8",
        "namespace": spec.namespace,
        "seed": SEED,
        "source_archive": SOURCE_ARCHIVE,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "source_records": source_templates(spec.root),
        "placement": "after-first-h1-before-rechunking",
        "chunking": {"tokens": 2048, "overlap_tokens": 128, "stride_tokens": 1920},
        "arms": {arm: condition(spec, arm) for arm in ARMS},
        "rendered_targets": targets,
    }
    result["manifest_hash"] = _json_hash(result)
    return result


def freeze_condition_design(spec: Any) -> dict[str, Any]:
    result = condition_design_manifest(spec)
    atomic_json(Path(spec.root) / "configs/skillsbench-dymal4-conditions.json", result)
    return result


def validate_condition_design(spec: Any) -> dict[str, Any]:
    """Validate the four frozen source records, adaptations, and targets."""
    relative = spec.values.get("source", {}).get("condition_manifest")
    if relative != "configs/skillsbench-dymal4-conditions.json":
        raise ValueError("skillsbench_injection_condition_manifest_path_invalid")
    path = Path(spec.root) / relative
    try:
        actual = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("skillsbench_injection_condition_manifest_unreadable") from exc
    expected = condition_design_manifest(spec)
    if actual != expected:
        raise ValueError("skillsbench_injection_condition_manifest_changed")
    return {
        "source_archive": SOURCE_ARCHIVE,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "condition_manifest": relative,
        "condition_manifest_sha256": _sha256(path.read_bytes()),
        "condition_manifest_hash": actual["manifest_hash"],
        "source_records": actual["source_records"],
        "conditions": len(actual["arms"]),
    }
