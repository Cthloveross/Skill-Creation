"""Offline app-server transport checks: no account or model is contacted."""

import base64
import hashlib
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution.codex_plan import CodexPlanClient, CodexPlanOpener, _inputs
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import InputTokenBudgetExceeded, ModelClientError
from tau_skill_evolution.workflow import Workflow


def fake_server(
    path: Path,
    *,
    crash: bool = False,
    failed: bool = False,
    token_usage=None,
    event_type=None,
    malformed: bool = False,
) -> str:
    program = """#!/usr/bin/python3
import json,sys
count=0
thread_count=0
thread_id=None
open(COUNT+'.args','w').write(json.dumps(sys.argv[1:]))
for line in sys.stdin:
 v=json.loads(line); method=v.get('method'); result={}
 if method=='initialized': continue
 if method in ('thread/start','thread/resume'):
  if method=='thread/start':
   thread_count+=1
   thread_id='thread' if thread_count==1 else 'thread_'+str(thread_count)
  else: thread_id=v['params']['threadId']
  result={'thread':{'id':thread_id},'model':'gpt-6.1-sol','modelProvider':'openai',
   'instructionSources':[],'runtimeWorkspaceRoots':[]}
 if method=='turn/start':
  count+=1
  open(COUNT,'a').write('turn\\n')
  if CRASH: sys.exit(1)
  result={'turn':{'id':str(count)}}
 print(json.dumps({'id':v['id'],'result':result}),flush=True)
 if method=='turn/start':
  if MALFORMED:
   print('{malformed event',flush=True)
   continue
  if EVENT_TYPE:
   print(json.dumps({'method':'item/started','params':{'threadId':thread_id,
    'turnId':str(count),'item':{'type':EVENT_TYPE}}}),flush=True)
   continue
  print(json.dumps({'method':'thread/tokenUsage/updated','params':{'threadId':thread_id,'turnId':str(count),
   'tokenUsage':TOKEN_USAGE}}),flush=True)
  print(json.dumps({'method':'item/completed','params':{'threadId':thread_id,'turnId':str(count),'item':{'type':'agentMessage',
   'phase':'final_answer','text':json.dumps({'content':'done','tool_calls':[]})}}}),flush=True)
  print(json.dumps({'method':'turn/completed','params':{'threadId':thread_id,'turn':{'id':str(count),
   'status':'failed' if FAILED else 'completed'}}}),flush=True)
"""
    path.write_text(
        f"#!/usr/bin/python3\nCOUNT={str(path.with_suffix('.count'))!r}\n"
        f"CRASH={crash!r}\nFAILED={failed!r}\nMALFORMED={malformed!r}\n"
        f"EVENT_TYPE={event_type!r}\nTOKEN_USAGE={token_usage or {'last': usage(10, 8)}!r}\n"
        + program.split("\n", 1)[1]
    )
    path.chmod(0o700)
    return str(path)


def usage(input_tokens, output_tokens):
    return {
        "inputTokens": input_tokens,
        "cachedInputTokens": 2,
        "outputTokens": output_tokens,
        "reasoningOutputTokens": 3,
        "totalTokens": input_tokens + output_tokens,
    }


class CharacterCounter:
    def count(self, messages, **kwargs):
        return sum(len(message["content"]) for message in messages)


def test_single_turn_raw_sealed_and_recovery(tmp_path):
    binary = fake_server(tmp_path / "codex")
    settings = dict(
        role="generator",
        journal_dir=tmp_path / "private",
        binary=binary,
        usage_path=tmp_path / "usage.jsonl",
    )
    client = CodexPlanClient(**settings)
    messages = [{"role": "user", "content": "create"}]
    try:
        first = client.complete(messages)
        assert first["content"] == "done"
        assert first["usage"]["output_tokens_details"]["reasoning_tokens"] == 3
    finally:
        client.close()
    recovered = CodexPlanClient(**settings)
    try:
        assert recovered.complete(messages) == first
        assert recovered._process is None
    finally:
        recovered.close()
    assert (tmp_path / "codex.count").read_text() == "turn\n"
    record = next((tmp_path / "private").glob("*/raw-response.json"))
    raw = json.loads(base64.b64decode(json.loads(record.read_text())["body_base64"]))
    assert raw["thread_id"] == "thread" and raw["turn_id"] == "1"
    assert any(e.get("method") == "turn/completed" for e in raw["events"])
    stream = next((tmp_path / "private").glob("turn-events/*/events.jsonl"))
    assert [json.loads(line) for line in stream.read_text().splitlines()] == raw["events"]
    assert json.loads((stream.parent / "state.json").read_text())["status"] == "RECEIVED"


def test_unknown_never_redispatched(tmp_path):
    binary = fake_server(tmp_path / "codex", crash=True)
    settings = dict(role="generator", journal_dir=tmp_path / "private", binary=binary)
    messages = [{"role": "user", "content": "create"}]
    first = CodexPlanClient(**settings)
    try:
        with pytest.raises(UnknownOperation):
            first.complete(messages)
    finally:
        first.close()
    again = CodexPlanClient(**settings)
    try:
        with pytest.raises(UnknownOperation):
            again.complete(messages)
        with pytest.raises(UnknownOperation):
            again.complete([{"role": "user", "content": "different request"}])
        assert again._process is None
    finally:
        again.close()
    assert (tmp_path / "codex.count").read_text() == "turn\n"


def test_delta_and_role_binding(tmp_path):
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private")
    requests = []
    events = []
    client._start = lambda: None

    def rpc(method, params):
        requests.append((method, params))
        if method == "thread/start":
            return {
                "thread": {"id": "isolated"},
                "model": "gpt-6.1-sol",
                "modelProvider": "openai",
                "instructionSources": [],
                "runtimeWorkspaceRoots": [],
            }
        if method == "thread/resume":
            return {
                "model": "gpt-6.1-sol",
                "modelProvider": "openai",
                "instructionSources": [],
                "runtimeWorkspaceRoots": [],
            }
        if method == "turn/start":
            events[:] = [
                {
                    "method": "turn/completed",
                    "params": {"threadId": "isolated", "turn": {"id": "a"}},
                }
            ]
            return {"turn": {"id": "a"}}
        return {}

    client._rpc = rpc
    client._read = lambda _: events.pop()
    original = [{"role": "user", "content": "fixed base"}]
    client._turn(client._ready({"messages": original, "tools": []}))
    client.state["messages"] = original
    client._turn(
        client._ready(
            {"messages": original + [{"role": "user", "content": "new feedback"}], "tools": []}
        )
    )
    turns = [params for method, params in requests if method == "turn/start"]
    assert len(turns) == 2
    assert json.loads(turns[1]["input"][0]["text"])["messages"] == [
        {"role": "user", "content": "new feedback"}
    ]
    assert turns[0]["environments"] == []
    frame = next(params for method, params in requests if method == "thread/start")
    assert frame["sandbox"] == "read-only"
    assert frame["dynamicTools"] == []
    assert "separate task container" in frame["baseInstructions"]
    assert "write task deliverables" in frame["baseInstructions"]
    assert "only your native host capabilities" in frame["baseInstructions"]
    with pytest.raises(ValueError, match="identity"):
        CodexPlanClient(role="verifier", journal_dir=tmp_path / "private")


def test_outer_journal_and_known_failed_turn(tmp_path):
    client = CodexPlanClient(
        role="generator",
        journal_dir=tmp_path / "private",
        binary=fake_server(tmp_path / "codex", failed=True),
    )
    journal = Journal(tmp_path / "outer")
    try:
        with pytest.raises(ModelClientError, match="did not complete"):
            client.complete_journaled(journal, "s0", {}, [{"role": "user", "content": "create"}])
    finally:
        client.close()
    assert (tmp_path / "codex.count").read_text() == "turn\n"


def test_native_relay_function_custom_and_namespaced_calls(tmp_path):
    client = CodexPlanClient(role="execution", journal_dir=tmp_path / "private")
    calls = [
        ("read", '{"path":"a"}'),
        ("apply_patch", "*** patch"),
        ("functions.exec_command", '{"cmd":"true"}'),
    ]
    client.complete = lambda *args, **kwargs: {
        "content": "ready",
        "response_id": "turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "tool_calls": [
            {"id": str(i), "function": {"name": name, "arguments": arguments}}
            for i, (name, arguments) in enumerate(calls)
        ],
    }
    payload = {
        "input": [{"role": "user", "content": "task"}],
        "tools": [
            {"type": "function", "name": "read"},
            {"type": "custom", "name": "apply_patch"},
            {
                "type": "namespace",
                "name": "functions",
                "tools": [{"type": "function", "name": "exec_command"}],
            },
        ],
    }
    opener = CodexPlanOpener(client)
    request = urllib.request.Request("http://unused/responses", data=json.dumps(payload).encode())
    with opener(request, timeout=15) as response:
        result = json.loads(response.read())
    assert result["output"][1]["type"] == "function_call"
    assert result["output"][2]["type"] == "custom_tool_call"
    assert result["output"][2]["input"] == "*** patch"
    assert result["output"][3]["namespace"] == "functions"
    assert result["output"][3]["name"] == "exec_command"
    assert client.timeout_seconds == 300


def test_startup_is_unsent_and_does_not_block_new_credential_attempt(tmp_path):
    script = tmp_path / "closed-server"
    script.write_text("#!/usr/bin/python3\nimport sys\nsys.exit(1)\n")
    script.chmod(0o700)
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private", binary=str(script))
    outer = Journal(tmp_path / "outer")
    try:
        with pytest.raises(EOFError):
            client.complete_journaled(outer, "s0", {}, [{"role": "user", "content": "create"}])
        assert outer.status("s0") == "NOT_SENT"
        assert not client.blocked_path.exists()
    finally:
        client.close()


@pytest.mark.parametrize(
    "name,raw,kind",
    [
        ("exec", "await tools.exec_command({cmd: 'pwd'})", "custom_tool_call"),
        ("wait", "{cell_id: 'cell', yield_time_ms: 1000}", "custom_tool_call"),
        ("apply_patch", "*** Begin Patch\n*** End Patch", "custom_tool_call"),
        ("exec_command", '{"cmd":"pwd"}', "function_call"),
    ],
)
def test_pinned_cli_prompt_declared_tools_without_tools_field(tmp_path, name, raw, kind):
    client = CodexPlanClient(role="execution", journal_dir=tmp_path / "private")
    client.complete = lambda *args, **kwargs: {
        "content": "",
        "response_id": "turn",
        "usage": {"input_tokens": 5, "output_tokens": 10},
        "tool_calls": [{"id": "call", "function": {"name": "functions." + name, "arguments": raw}}],
    }
    payload = {
        "input": [
            {"role": "developer", "content": "Namespace: functions"},
            {"role": "user", "content": "task"},
        ]
    }
    request = urllib.request.Request("http://unused/responses", data=json.dumps(payload).encode())
    with CodexPlanOpener(client)(request, timeout=15) as response:
        item = json.loads(response.read())["output"][0]
    assert item["type"] == kind
    assert item["namespace"] == "functions"
    assert item["name"] == name
    assert item["input" if kind == "custom_tool_call" else "arguments"] == raw


def test_model_or_host_instruction_mismatch_blocks_before_turn(tmp_path):
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private")
    client._start = lambda: None
    client._rpc = lambda *args: {
        "thread": {"id": "wrong"},
        "model": "other",
        "modelProvider": "openai",
    }
    with pytest.raises(ModelClientError, match="mismatch"):
        client._ready({"messages": []})
    client._rpc = lambda *args: {
        "thread": {"id": "wrong"},
        "model": client.model,
        "modelProvider": "openai",
        "instructionSources": ["/private/AGENTS.md"],
    }
    with pytest.raises(ModelClientError, match="unexpected host"):
        client._ready({"messages": [{"role": "user", "content": "new"}]})


def test_task_image_uses_native_input_without_host_file_access():
    source = [
        {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": "data:image/png;base64,AA==", "detail": "high"}
            ],
        }
    ]
    actual = _inputs(source, [], None)
    assert actual[1] == {"type": "image", "url": "data:image/png;base64,AA==", "detail": "high"}
    assert "base64" not in actual[0]["text"]
    assert source[0]["content"][0]["type"] == "input_image"
    with pytest.raises(ModelClientError, match="inline task"):
        _inputs([{"type": "input_image", "image_url": "file:///private/auth.json"}], [], None)
    with pytest.raises(ModelClientError, match="unsupported"):
        _inputs([{"type": "input_audio", "data": "abc"}], [], None)


def test_provider_context_rejects_small_visible_history_before_dispatch(tmp_path):
    binary = fake_server(
        tmp_path / "codex",
        token_usage={"last": usage(185730, 8000), "modelContextWindow": 258400},
    )
    client = CodexPlanClient(
        role="generator",
        journal_dir=tmp_path / "private",
        binary=binary,
        max_input_tokens=157632,
        token_counter=CharacterCounter(),
        context_window=272000,
        context_fraction=0.7,
        output_reserve=32768,
    )
    first = [{"role": "user", "content": "a"}]
    second = first + [{"role": "user", "content": "new feedback"}]
    outer = Journal(tmp_path / "outer")
    try:
        response = client.complete(first)
        assert response["context_budget"] == {
            "context_window": 258400,
            "input_tokens": 185730,
            "output_tokens": 8000,
            "reserve_tokens": 32768,
        }
        with pytest.raises(InputTokenBudgetExceeded) as caught:
            client.complete_journaled(outer, "next", {}, second)
        assert caught.value.max_input_tokens == 148112
        assert caught.value.input_tokens == 193742
        assert outer.status("next") == "NOT_SENT"
        assert client.complete(first) == response
    finally:
        client.close()
    assert (tmp_path / "codex.count").read_text() == "turn\n"
    failure = json.loads(next((tmp_path / "outer").glob("*/failure.json")).read_text())
    assert failure["context_admission"]["provider_context_tokens"] == 193730
    args = json.loads((tmp_path / "codex.count.args").read_text())
    assert "model_auto_compact_token_limit=272000" in args
    assert 'model_auto_compact_token_limit_scope="total"' in args


def test_last_usage_not_cumulative_billing_and_context_recovery(tmp_path):
    binary = fake_server(
        tmp_path / "codex",
        token_usage={
            "last": usage(100, 8),
            "total": usage(900000, 60000),
            "modelContextWindow": 10000,
        },
    )
    settings = dict(
        role="generator",
        journal_dir=tmp_path / "private",
        binary=binary,
        max_input_tokens=1000,
        token_counter=CharacterCounter(),
        context_window=12000,
        context_fraction=0.7,
        output_reserve=100,
    )
    client = CodexPlanClient(**settings)
    first = [{"role": "user", "content": "first"}]
    try:
        response = client.complete(first)
        assert response["usage"]["input_tokens"] == 900000
        assert client.context_budget()["input_tokens"] == 100
        second = first + [{"role": "user", "content": "delta"}]
        projected = client.projected_context(second)
        assert projected["visible_input_tokens"] == 10
        assert projected["provider_context_tokens"] == 108
        assert projected["delta_input_tokens"] == 5
        assert projected["observed_input_tokens"] == 113
        assert projected["reserve_tokens"] == 100
        client.complete(second)
    finally:
        client.close()
    recovered = CodexPlanClient(**settings)
    try:
        assert recovered.context_budget() == response["context_budget"]
        assert recovered.complete(first) == response
        assert recovered._process is None
    finally:
        recovered.close()
    assert (tmp_path / "codex.count").read_text() == "turn\nturn\n"


def test_missing_provider_context_keeps_visible_estimate(tmp_path):
    client = CodexPlanClient(
        role="generator",
        journal_dir=tmp_path / "private",
        max_input_tokens=10,
        token_counter=CharacterCounter(),
    )
    value = client.projected_context([{"role": "user", "content": "abc"}])
    assert value["observed_input_tokens"] == 3
    assert value["provider_context_tokens"] == 0
    assert client.context_budget()["context_window"] is None


def test_omitted_or_larger_window_does_not_relax_observed_context(tmp_path):
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private")

    def normalize(window):
        token_usage = {"last": usage(100, 8)}
        if window is not None:
            token_usage["modelContextWindow"] = window
        return client._normalize(
            200,
            json.dumps(
                {
                    "thread_id": "same-thread",
                    "turn_id": "turn",
                    "request": {"messages": []},
                    "events": [
                        {
                            "method": "thread/tokenUsage/updated",
                            "params": {
                                "threadId": "same-thread",
                                "turnId": "turn",
                                "tokenUsage": token_usage,
                            },
                        },
                        {
                            "method": "item/completed",
                            "params": {
                                "threadId": "same-thread",
                                "turnId": "turn",
                                "item": {
                                    "type": "agentMessage",
                                    "text": '{"content":"done","tool_calls":[]}',
                                },
                            },
                        },
                        {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "same-thread",
                                "turn": {"id": "turn", "status": "completed"},
                            },
                        },
                    ],
                }
            ).encode(),
        )

    assert normalize(258400)["context_budget"]["context_window"] == 258400
    assert normalize(None)["context_budget"]["context_window"] == 258400
    assert normalize(272000)["context_budget"]["context_window"] == 258400


def test_fresh_author_chat_resets_opaque_history_but_preserves_window(tmp_path):
    binary = fake_server(tmp_path / "codex")
    client = CodexPlanClient(
        role="verifier",
        journal_dir=tmp_path / "private",
        binary=binary,
        max_input_tokens=157632,
        token_counter=CharacterCounter(),
        context_window=272000,
        context_fraction=0.7,
        output_reserve=32768,
    )
    old = [{"role": "user", "content": "prior completed verifier chat"}]
    client.state = {
        "thread_id": "previous-thread",
        "messages": old,
        "total_usage": usage(900000, 60000),
        "context_budget": {
            "context_window": 258400,
            "input_tokens": 185730,
            "output_tokens": 8000,
        },
    }
    fresh = [{"role": "user", "content": "new independent author verifier chat"}]
    value = client.projected_context(fresh)
    assert value["provider_context_tokens"] == 0
    assert value["observed_input_tokens"] == len(fresh[0]["content"])
    assert value["max_input_tokens"] == 148112
    with pytest.raises(InputTokenBudgetExceeded):
        client.complete(old + [{"role": "user", "content": "continue prior chat"}])
    try:
        response = client.complete(fresh)
        assert response["context_budget"]["context_window"] == 258400
        assert response["context_budget"]["input_tokens"] == 10
        assert response["usage"]["input_tokens"] == 10
    finally:
        client.close()
    assert (tmp_path / "codex.count").read_text() == "turn\n"


@pytest.mark.parametrize(
    "event_type,expected_code",
    [
        ("contextCompaction", "codex_plan_context_compaction"),
        *[
            (kind, "codex_plan_native_tool")
            for kind in (
                "commandExecution",
                "fileChange",
                "mcpToolCall",
                "dynamicToolCall",
                "collabAgentToolCall",
                "subAgentActivity",
                "webSearch",
                "imageView",
                "imageGeneration",
                "sleep",
                "enteredReviewMode",
                "exitedReviewMode",
                "functionCallOutput",
                "hookPrompt",
            )
        ],
        (None, None),
    ],
)
def test_received_events_sealed_before_rejected_or_malformed_parse(
    tmp_path, event_type, expected_code
):
    binary = fake_server(tmp_path / "codex", event_type=event_type, malformed=event_type is None)
    settings = dict(role="generator", journal_dir=tmp_path / "private", binary=binary)
    client = CodexPlanClient(**settings)
    messages = [{"role": "user", "content": "create"}]
    try:
        with pytest.raises(UnknownOperation) as caught:
            client.complete(messages)
        if expected_code:
            assert caught.value.__cause__.code == expected_code
    finally:
        client.close()
    stream = next((tmp_path / "private").glob("turn-events/*/events.jsonl"))
    assert stream.stat().st_mode & 0o777 == 0o600
    assert (
        event_type in stream.read_text() if event_type else "{malformed event" in stream.read_text()
    )
    metadata = json.loads((stream.parent / "state.json").read_text())
    assert metadata["status"] == "UNKNOWN"
    assert metadata["turn_id"] == "1"
    assert metadata["sha256"] == hashlib.sha256(stream.read_bytes()).hexdigest()
    recovered = CodexPlanClient(**settings)
    try:
        with pytest.raises(UnknownOperation):
            recovered.complete(messages)
        assert recovered._process is None
    finally:
        recovered.close()
    assert (tmp_path / "codex.count").read_text() == "turn\n"


def test_distinct_operations_with_same_prompt_have_separate_threads_and_streams(tmp_path):
    client = CodexPlanClient(
        role="verifier", journal_dir=tmp_path / "private", binary=fake_server(tmp_path / "codex")
    )
    journal = Journal(tmp_path / "outer")
    messages = [{"role": "user", "content": "same initial verifier prompt"}]
    try:
        first = client.complete_journaled(journal, "generation-1", {}, messages)
        second = client.complete_journaled(journal, "generation-2", {}, messages)
        assert first["response_id"] != second["response_id"]
        assert client.complete_journaled(journal, "generation-1", {}, messages) == first
    finally:
        client.close()
    assert (tmp_path / "codex.count").read_text() == "turn\nturn\n"
    streams = list((tmp_path / "private" / "turn-events").glob("*/events.jsonl"))
    assert len(streams) == 2
    states = [json.loads((p.parent / "state.json").read_text()) for p in streams]
    assert {s["thread_id"] for s in states} == {"thread", "thread_2"}
    assert all(s["status"] == "RECEIVED" for s in states)
    assert len({s["operation_key"] for s in states}) == 2


def matching_events(thread="current", turn="current-turn"):
    coordinates = {"threadId": thread, "turnId": turn}
    return [
        {
            "method": "thread/tokenUsage/updated",
            "params": {**coordinates, "tokenUsage": {"last": usage(20, 8)}},
        },
        {
            "method": "item/completed",
            "params": {
                **coordinates,
                "item": {"type": "agentMessage", "text": '{"content":"current","tool_calls":[]}'},
            },
        },
        {
            "method": "turn/completed",
            "params": {"threadId": thread, "turn": {"id": turn, "status": "completed"}},
        },
    ]


@pytest.mark.parametrize("thread,turn", [("prior", "current-turn"), ("current", "prior-turn")])
@pytest.mark.parametrize("kind", ["usage", "final", "failed"])
def test_stale_thread_or_turn_events_do_not_pollute_current_result(tmp_path, thread, turn, kind):
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private")
    stale = matching_events(thread, turn)
    if kind == "usage":
        event = stale[0]
        event["params"]["tokenUsage"]["last"] = usage(185730, 1000)
    elif kind == "final":
        event = stale[1]
        event["params"]["item"]["text"] = '{"content":"stale","tool_calls":[]}'
    else:
        event = stale[2]
        event["params"]["turn"].update(
            status="failed", error={"codexErrorInfo": "usageLimitExceeded"}
        )
    raw = {
        "thread_id": "current",
        "turn_id": "current-turn",
        "request": {"messages": []},
        "events": [*matching_events(), event],
    }
    response = client._normalize(200, json.dumps(raw).encode())
    assert response["content"] == "current"
    assert response["context_budget"]["input_tokens"] == 20
    assert response["usage"]["input_tokens"] == 20
    assert not client.blocked_path.exists()


def test_current_completion_is_required_and_foreign_thread_does_not_end_turn(tmp_path):
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private")
    events = matching_events()[:2] + matching_events("prior", "current-turn")[2:]
    raw = {
        "thread_id": "current",
        "turn_id": "current-turn",
        "request": {"messages": []},
        "events": events,
    }
    with pytest.raises(ModelClientError, match="completion"):
        client._normalize(200, json.dumps(raw).encode())
    client.state = {"thread_id": "current", "messages": []}
    client._rpc = lambda *args: {"turn": {"id": "current-turn"}}
    pending = [matching_events("prior", "current-turn")[2], matching_events()[2]]

    def read(_deadline):
        event = pending.pop(0)
        client._events.append(event)
        return event

    client._read = read
    _, body = client._turn({"messages": []})
    assert len(json.loads(body)["events"]) == 2
    assert not pending


@pytest.mark.parametrize("external", [True, False])
def test_raw_response_recovery_usage_is_one_logical_operation(tmp_path, external):
    settings = dict(
        role="generator",
        journal_dir=tmp_path / "private",
        binary=fake_server(tmp_path / "codex"),
        usage_path=tmp_path / "usage.jsonl",
    )
    client = CodexPlanClient(**settings)
    journal = Journal(tmp_path / "outer") if external else client.journal
    seal = journal._seal
    journal._seal = lambda *args: (_ for _ in ()).throw(RuntimeError("fixture_crash_before_seal"))
    messages = [{"role": "user", "content": "create"}]

    def complete():
        return (
            client.complete_journaled(journal, "s0", {}, messages)
            if external
            else client.complete(messages)
        )

    try:
        with pytest.raises(RuntimeError, match="fixture_crash_before_seal"):
            complete()
        journal._seal = seal
        assert complete()["content"] == "done"
    finally:
        client.close()
    rows = [json.loads(line) for line in (tmp_path / "usage.jsonl").read_text().splitlines()]
    assert len(rows) == 2  # Both deterministic parses are auditable.
    assert rows[0]["operation_key"] == rows[1]["operation_key"]
    summary = Workflow._usage_summary(SimpleNamespace(root=tmp_path))
    assert summary["total"]["requests"] == 1
    assert summary["total"]["input_tokens"] == 10
    assert (tmp_path / "codex.count").read_text() == "turn\n"


@pytest.mark.parametrize("value", ["invalid envelope", None])
def test_invalid_outer_json_is_a_transport_error(tmp_path, value):
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private")
    events = matching_events()
    events[1]["params"]["item"]["text"] = value
    raw = {
        "thread_id": "current",
        "turn_id": "current-turn",
        "request": {"messages": []},
        "events": events,
    }
    with pytest.raises(ModelClientError) as caught:
        client._normalize(200, json.dumps(raw).encode())
    assert caught.value.code == "codex_plan_response_invalid"


@pytest.mark.parametrize("field", ["last", "total", "prior"])
@pytest.mark.parametrize("malformed", [True, "20", -1, "missing", "not an object"])
def test_all_usage_fields_validate_before_billing_subtraction(tmp_path, field, malformed):
    client = CodexPlanClient(role="generator", journal_dir=tmp_path / "private")
    events = matching_events()
    events[0]["params"]["tokenUsage"]["total"] = usage(20, 8)
    raw = {
        "thread_id": "current",
        "turn_id": "current-turn",
        "request": {"messages": []},
        "events": events,
    }
    value = usage(20, 8)
    if malformed == "missing":
        del value["inputTokens"]
    elif malformed == "not an object":
        value = []
    else:
        value["inputTokens"] = malformed
    if field == "prior":
        if malformed == "missing":
            value["inputTokens"] = "invalid"  # Empty first-turn prior remains legitimate.
        raw["prior_usage"] = value
    else:
        events[0]["params"]["tokenUsage"][field] = value
    with pytest.raises(ModelClientError) as caught:
        client._normalize(200, json.dumps(raw).encode())
    assert caught.value.code == "codex_plan_response_invalid"
