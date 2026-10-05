#!/usr/bin/env python3
"""Loopback front for the pinned embedding service: local tokenize, remote embeddings.

The experiment counts tokens with the embedding server's ``/tokenize`` route on
every model request.  When vLLM runs on a remote GPU host behind an SSH tunnel,
that route becomes the bottleneck (tokenization is CPU-bound on the small GPU
host).  This proxy listens on the configured loopback endpoint, answers
``/tokenize`` locally with the *same* pinned Hugging Face tokenizer
(``tokenizer.json`` of the pinned revision, so counts are identical) and forwards
``/v1/models`` and ``/v1/embeddings`` verbatim to the upstream vLLM server.

Usage (run with the embedding venv python, which has ``tokenizers``):

    data/embedding/.venv/bin/python scripts/embedding_proxy.py \
        --listen 127.0.0.1:18140 --upstream http://127.0.0.1:18141
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL_ID = "Qwen/Qwen3-Embedding-4B"
REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"
MAX_MODEL_LEN = 4096


def tokenizer_path() -> Path:
    cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
    owner, name = MODEL_ID.split("/", 1)
    return cache / "hub" / f"models--{owner}--{name}" / "snapshots" / REVISION / "tokenizer.json"


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tokenize = 0
        self.tokenize_seconds = 0.0
        self.forwarded = 0
        self.errors = 0

    def snapshot(self) -> dict[str, float | int]:
        with self.lock:
            return {
                "tokenize_requests": self.tokenize,
                "tokenize_seconds": round(self.tokenize_seconds, 3),
                "forwarded_requests": self.forwarded,
                "errors": self.errors,
            }


def make_handler(tokenizer: object, upstream: str, stats: Stats) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "tau-embedding-proxy/1.0"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def _forward(self, method: str) -> None:
            body = self._body()
            request = urllib.request.Request(
                upstream.rstrip("/") + self.path,
                data=body if method == "POST" else None,
                headers={
                    "Content-Type": self.headers.get("Content-Type", "application/json"),
                    "Accept": self.headers.get("Accept", "*/*"),
                },
                method=method,
            )
            try:
                with urllib.request.urlopen(request, timeout=600) as response:
                    payload = response.read()
                    status = response.status
                    content_type = response.headers.get("Content-Type", "application/json")
            except urllib.error.HTTPError as exc:
                payload, status = exc.read(), exc.code
                content_type = exc.headers.get("Content-Type", "application/json")
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                with stats.lock:
                    stats.errors += 1
                self._send(502, json.dumps({"error": f"upstream unavailable: {exc}"}).encode())
                return
            with stats.lock:
                stats.forwarded += 1
            self._send(status, payload, content_type)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/proxy/stats":
                self._send(200, json.dumps(stats.snapshot()).encode())
                return
            self._forward("GET")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/tokenize":
                self._forward("POST")
                return
            started = time.monotonic()
            try:
                decoded = json.loads(self._body())
                prompt = decoded.get("prompt")
                if not isinstance(decoded, dict) or not isinstance(prompt, str):
                    raise ValueError("prompt must be a string")
                if decoded.get("model") not in (None, MODEL_ID):
                    raise ValueError("unknown model")
                add_special = bool(decoded.get("add_special_tokens", True))
            except (ValueError, UnicodeDecodeError) as exc:
                with stats.lock:
                    stats.errors += 1
                self._send(400, json.dumps({"error": str(exc)}).encode())
                return
            encoding = tokenizer.encode(prompt, add_special_tokens=add_special)  # type: ignore[attr-defined]
            ids = encoding.ids
            payload = {
                "count": len(ids),
                "max_model_len": MAX_MODEL_LEN,
                "tokens": ids,
                "token_strs": None,
            }
            with stats.lock:
                stats.tokenize += 1
                stats.tokenize_seconds += time.monotonic() - started
            self._send(200, json.dumps(payload).encode())

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="127.0.0.1:18140")
    parser.add_argument("--upstream", default="http://127.0.0.1:18141")
    parser.add_argument("--tokenizer", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    if args.workers <= 0:
        parser.error("--workers must be positive")
    from tokenizers import Tokenizer

    path = args.tokenizer or tokenizer_path()
    if not path.is_file():
        print(f"pinned tokenizer missing: {path}", file=sys.stderr)
        return 2
    tokenizer = Tokenizer.from_file(str(path))
    host, port = args.listen.rsplit(":", 1)
    stats = Stats()

    class Server(ThreadingHTTPServer):
        # Hundreds of experiment cells may tokenize at once; the default backlog of 5
        # resets connections under that burst.
        request_queue_size = 4096
        allow_reuse_address = True
        daemon_threads = True

    server = Server((host, int(port)), make_handler(tokenizer, args.upstream, stats))
    print(
        json.dumps(
            {
                "listen": args.listen,
                "upstream": args.upstream,
                "tokenizer": str(path),
                "workers": args.workers,
            }
        ),
        flush=True,
    )
    # Tokenization holds the GIL, so one process serves only a few large requests per
    # second.  Pre-fork workers that all accept on the inherited listening socket.
    children: set[int] = set()

    def spawn() -> None:
        pid = os.fork()
        if pid == 0:
            with contextlib.suppress(KeyboardInterrupt):
                server.serve_forever()
            os._exit(0)
        children.add(pid)

    for _ in range(args.workers):
        spawn()
    try:
        while children:
            pid, _ = os.wait()
            children.discard(pid)
            spawn()
    except KeyboardInterrupt:
        for pid in children:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, 15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
