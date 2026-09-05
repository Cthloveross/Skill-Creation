from __future__ import annotations

import json
from pathlib import Path

import pytest

from r2sp_tau_knowledge.constants import TARGET_DOCUMENT_ID


@pytest.fixture
def miniature_corpus(tmp_path: Path) -> dict[str, object]:
    documents = tmp_path / "source-documents"
    documents.mkdir()

    target_value = {
        "id": TARGET_DOCUMENT_ID,
        "title": "Gold Rewards Card",
        "content": "Original trusted body.",
    }
    target_raw = json.dumps(target_value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    target_path = documents / f"{TARGET_DOCUMENT_ID}.json"
    target_path.write_bytes(target_raw)

    other_raw = b'{  "id": "doc_other_001", "title": "Other", "content": "Unchanged" }\n'
    other_path = documents / "doc_other_001.json"
    other_path.write_bytes(other_raw)

    payload_root = tmp_path / "payloads"
    payload_root.mkdir()
    payload_files = {
        "mock-api-call": payload_root / "mock-api-call.txt",
        "delete-sentinel": payload_root / "delete-sentinel.txt",
    }
    payload_files["mock-api-call"].write_bytes(b"  exact payload bytes\n")
    payload_files["delete-sentinel"].write_bytes(b"delete payload\n")

    return {
        "documents": documents,
        "target_path": target_path,
        "target_raw": target_raw,
        "target_value": target_value,
        "other_path": other_path,
        "other_raw": other_raw,
        "payload_files": payload_files,
        "output_root": tmp_path / "materialized",
    }
