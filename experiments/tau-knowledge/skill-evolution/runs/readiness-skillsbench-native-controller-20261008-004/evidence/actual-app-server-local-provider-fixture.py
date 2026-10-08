"""Pinned actual app-server, local scripted Responses, no model or credentials.

Only the fixture RPC handshake remaps openai to a nonreserved local-provider ID.
Production model/provider validation is unchanged. Token usage is scripted, not
model performance. HOME credentials are never copied into the empty CODEX_HOME.
"""

import hashlib
import json
import queue
import shlex
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tau_skill_evolution.codex_plan import CodexPlanClient
from tau_skill_evolution.codex_provider import _response_sse
from tau_skill_evolution.journal import UnknownOperation
from tau_skill_evolution.model import InputTokenBudgetExceeded

EVIDENCE = Path(
    "experiments/tau-knowledge/skill-evolution/runs/readiness-skillsbench-native-controller-20261008-004/evidence"
).resolve()
BINARY = Path("/home/tc442/.local/skillsbench-codex-0.160.1/codex")
records = []
mode = {"name": "normal", "requests": 0}
posted, release = threading.Event(), threading.Event()


class Counter:
    def count(self, messages, **kwargs):
        return sum(len(m.get("content", "")) for m in messages)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        payload = json.loads(raw)
        mode["requests"] += 1
        number = len(records) + 1
        records.append(
            {
                "id": number,
                "request_sha256": hashlib.sha256(raw).hexdigest(),
                "path": self.path,
                "tools_count": len(payload.get("tools", [])),
            }
        )
        if mode["name"] == "interrupt":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(
                b'event: response.created\ndata: {"type":"response.created",'
                b'"response":{"id":"interrupted-fixture","status":"in_progress","output":[]}}\n\n'
            )
            self.wfile.flush()
            posted.set()
            release.wait(10)
            return
        input_tokens = 185730 if mode["name"] == "context" and mode["requests"] == 2 else 100
        item = {
            "type": "message",
            "id": f"msg_{number}",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": json.dumps({"content": "done", "tool_calls": []}),
                    "annotations": [],
                }
            ],
        }
        response = {
            "id": f"resp_{number}",
            "object": "response",
            "status": "completed",
            "model": payload["model"],
            "output": [item],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 8,
                "total_tokens": input_tokens + 8,
                "input_tokens_details": {"cached_tokens": 2},
                "output_tokens_details": {"reasoning_tokens": 3},
            },
        }
        body = _response_sse(response)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


result = {
    "status": "NOT_MEASURED",
    "measurement": "MODEL_SCRIPTED",
    "real_cli": True,
    "paid_or_subscription_model": False,
    "cli_sha256": hashlib.sha256(BINARY.read_bytes()).hexdigest(),
    "fixture_only_provider_handshake_remap": "openai <-> offline_fixture",
    "real_ChatGPT_auth_network_verified": False,
}
server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
clients = []
try:
    with tempfile.TemporaryDirectory(prefix="codex-plan-actual-app-server-") as temporary:
        work = Path(temporary)
        home = work / "empty-codex-home"
        home.mkdir()
        (home / "config.toml").write_text(
            "model_context_window = 258400\n"
            "[model_providers.offline_fixture]\n"
            'name = "Local scripted fixture"\n'
            f'base_url = "http://127.0.0.1:{server.server_port}/v1"\n'
            'wire_api = "responses"\nrequires_openai_auth = false\n'
            "request_max_retries = 0\nstream_max_retries = 0\n"
        )
        wrapper = work / "codex-fixture"
        wrapper.write_text(
            "#!/bin/sh\nexport CODEX_HOME="
            + shlex.quote(str(home))
            + "\nexec "
            + shlex.quote(str(BINARY))
            + ' "$@"\n'
        )
        wrapper.chmod(0o700)

        def client_for(name):
            client = CodexPlanClient(
                role="generator",
                journal_dir=work / name,
                binary=str(wrapper),
                max_input_tokens=157632,
                token_counter=Counter(),
                timeout_seconds=30,
                context_window=272000,
                context_fraction=0.7,
                output_reserve=32768,
            )
            real_rpc = client._rpc

            def remap(method, params):
                if method == "thread/start":
                    params = {**params, "modelProvider": "offline_fixture"}
                value = real_rpc(method, params)
                if value.get("modelProvider") == "offline_fixture":
                    value = {**value, "modelProvider": "openai"}
                return value

            client._rpc = remap
            clients.append(client)
            return client

        messages = [{"role": "user", "content": "Offline fixture: return done without tools."}]
        client = client_for("normal")
        response = client.complete(messages)
        assert response["content"] == "done"
        assert response["context_budget"]["input_tokens"] == 100
        assert response["context_budget"]["output_tokens"] == 8
        assert len(records) == 1
        recovered = client_for("normal")
        assert recovered.complete(messages) == response
        assert recovered._process is None and len(records) == 1
        result["normal"] = {
            "context_budget": response["context_budget"],
            "usage": response["usage"],
            "provider_requests": 1,
            "recovery_requests_added": 0,
            "native_tool_definitions": records[0]["tools_count"],
        }
        client.close()

        mode.update(name="context", requests=0)
        client = client_for("context")
        client.complete(messages)
        second = messages + [{"role": "user", "content": "Additional fixture feedback."}]
        second_response = client.complete(second)
        assert second_response["context_budget"]["input_tokens"] == 185730
        third = second + [{"role": "user", "content": "Must remain unsent."}]
        try:
            client.complete(third)
            raise AssertionError("provider context did not reject")
        except InputTokenBudgetExceeded as error:
            result["context_admission"] = error.details
        assert mode["requests"] == 2
        result["context_requests"] = 2
        assert client.complete(second) == second_response and mode["requests"] == 2
        client.close()

        mode.update(name="interrupt", requests=0)
        client = client_for("interrupt")
        stopped = queue.Queue()

        def pending_turn():
            try:
                client.complete(messages)
            except BaseException as error:
                stopped.put(error)

        thread = threading.Thread(target=pending_turn)
        thread.start()
        assert posted.wait(15), "scripted provider did not receive the turn"
        client._process.kill()  # Own fixture child, after one actual request.
        thread.join(15)
        assert not thread.is_alive()
        error = stopped.get(timeout=1)
        assert isinstance(error, UnknownOperation)
        stream = next((work / "interrupt" / "turn-events").glob("*/events.jsonl"))
        state = json.loads((stream.parent / "state.json").read_text())
        assert state["status"] == "UNKNOWN"
        assert state["sha256"] == hashlib.sha256(stream.read_bytes()).hexdigest()
        result["interrupted"] = {
            "status": state["status"],
            "raw_event_count": len(stream.read_text().splitlines()),
            "raw_sha256": state["sha256"],
            "raw_mode": oct(stream.stat().st_mode & 0o777),
            "provider_requests": mode["requests"],
        }
        again = client_for("interrupt")
        try:
            again.complete(messages)
            raise AssertionError("UNKNOWN turn was accepted")
        except UnknownOperation:
            pass
        assert again._process is None and mode["requests"] == 1
        result["interrupted"]["recovery_requests_added"] = 0
        assert not (home / "auth.json").exists()
        assert all(record["tools_count"] == 0 for record in records)
        result["status"] = "PASS"
        result["provider_requests"] = len(records)
except BaseException as error:
    result.update(
        status="FAILED",
        exception=type(error).__name__,
        error_code=getattr(error, "code", None),
        cause_code=getattr(error.__cause__, "code", None),
        provider_requests=len(records),
    )
    result["error_message"] = str(error)
finally:
    release.set()
    for client in clients:
        client.close()
    server.shutdown()
    server.server_close()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "actual-app-server-local-provider.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2))
