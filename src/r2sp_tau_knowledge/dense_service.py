"""Small localhost-only CPU service for the pinned Qwen dense encoder."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .batch_constants import (
    DENSE_DIMENSIONS,
    DENSE_MAX_INPUT_TOKENS,
    DENSE_MODEL_ID,
    DENSE_MODEL_REVISION,
    DENSE_QUERY_INSTRUCTION,
)


class DenseServiceError(RuntimeError):
    pass


def _revision(root: Path) -> str:
    metadata = root / ".cache" / "huggingface" / "download" / "config.json.metadata"
    try:
        return metadata.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError) as exc:
        raise DenseServiceError("dense model revision metadata is unavailable") from exc


class QwenDenseEncoder:
    """Reference last-token-pooling implementation from the model card."""

    def __init__(self, model_root: Path) -> None:
        if _revision(model_root) != DENSE_MODEL_REVISION:
            raise DenseServiceError("dense model revision mismatch")
        try:
            import torch
            import torch.nn.functional as functional
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise DenseServiceError("container lacks torch/transformers") from exc
        torch.set_num_threads(max(1, int(os.environ.get("R2SP_DENSE_CPU_THREADS", "24"))))
        self._torch = torch
        self._functional = functional
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_root,
            local_files_only=True,
            trust_remote_code=False,
            padding_side="left",
        )
        self._model = AutoModel.from_pretrained(
            model_root,
            local_files_only=True,
            trust_remote_code=False,
            torch_dtype=torch.float32,
        ).eval()

    def encode(self, texts: list[str], *, kind: str) -> list[list[float]]:
        if kind not in {"query", "document"}:
            raise ValueError("kind must be query or document")
        if (
            not texts
            or len(texts) > 32
            or any(not isinstance(text, str) or not text for text in texts)
        ):
            raise ValueError("texts must contain 1..32 non-empty strings")
        values = (
            [DENSE_QUERY_INSTRUCTION.format(query=text) for text in texts]
            if kind == "query"
            else texts
        )
        batch = self._tokenizer(
            values,
            padding=True,
            truncation=True,
            max_length=DENSE_MAX_INPUT_TOKENS,
            return_tensors="pt",
        )
        with self._torch.inference_mode():
            outputs = self._model(**batch)
            hidden = outputs.last_hidden_state
            mask = batch["attention_mask"]
            if bool(mask[:, -1].sum().item() == mask.shape[0]):
                pooled = hidden[:, -1]
            else:
                lengths = mask.sum(dim=1) - 1
                pooled = hidden[self._torch.arange(hidden.shape[0], device=hidden.device), lengths]
            normalized = self._functional.normalize(pooled.float(), p=2, dim=1)
        if normalized.shape[1] != DENSE_DIMENSIONS:
            raise DenseServiceError(
                f"dense dimension mismatch: {normalized.shape[1]} != {DENSE_DIMENSIONS}"
            )
        return normalized.cpu().tolist()


def _handler(encoder: QwenDenseEncoder) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "r2sp-dense/1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _json(self, status: int, value: dict[str, Any]) -> None:
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self._json(404, {"error": "not_found"})
                return
            self._json(
                200,
                {
                    "status": "ok",
                    "model_id": DENSE_MODEL_ID,
                    "revision": DENSE_MODEL_REVISION,
                    "dimensions": DENSE_DIMENSIONS,
                    "device": "cpu",
                },
            )

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/encode":
                self._json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8 * 1024 * 1024:
                    raise ValueError("invalid request size")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict) or set(value) != {"kind", "texts"}:
                    raise ValueError("request schema mismatch")
                vectors = encoder.encode(value["texts"], kind=value["kind"])
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200, {"vectors": vectors})

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the pinned dense encoder on localhost")
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18139)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("dense service may bind only to localhost")
    encoder = QwenDenseEncoder(args.model_root.resolve(strict=True))
    server = ThreadingHTTPServer((args.host, args.port), _handler(encoder))
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
