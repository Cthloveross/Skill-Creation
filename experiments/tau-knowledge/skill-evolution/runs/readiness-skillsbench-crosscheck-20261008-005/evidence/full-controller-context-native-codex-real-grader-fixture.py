"""Real native controller, adapter oracle, Codex CLI, local provider, and official grader."""

import os
import base64
import hashlib
import io
import json
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from tau_skill_evolution.artifacts import SkillBundle, load_base, load_bundle
from tau_skill_evolution.author_verifier import author_module, author_source
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.evaluation import evaluate_versions
from tau_skill_evolution.journal import Journal
from tau_skill_evolution.model import GenerationConfig, InputTokenBudgetExceeded, OpenAICompatibleClient
from tau_skill_evolution.skillsbench import SkillsBenchAdapter
from tau_skill_evolution.skillsbench_evolution import run_author_evolution
from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner
from tau_skill_evolution.spec import ExperimentSpec

EVIDENCE = Path(__file__).resolve().parent
MODE = os.environ.get("TAU_NATIVE_CONTEXT_FIXTURE", "observed")
assert MODE in {"observed", "predispatch"}
ROOT = Path(tempfile.mkdtemp(prefix="native-full-codex-", dir="/tmp"))
INPUT = EXPERIMENT_ROOT / "runs/readiness-skillsbench-native-controller-20261008-001/evidence/full-controller-input-fixture"
base, original = load_base(INPUT / "base"), load_bundle(INPUT / "initial")
files = dict(original.files)
files["SKILL.md"] = files["SKILL.md"].replace("name: current\n", "name: evo-current\n", 1)
files["evals/evals.json"] = '{"evals": [{"prompt": "Read the supplied public script"}]}\n'
files["assets/template.txt"] = "package-asset-v1\n"
files["scripts/check-assets.sh"] = '#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\ncat "$ROOT/assets/template.txt"\n'
initial = SkillBundle(files)
values = yaml.safe_load((EXPERIMENT_ROOT / "configs/skillsbench.yaml").read_text())
values["source"]["runtime_lock"] = "runtime/skillsbench-docker-dialogue-parser-v4-lock.json"
values["runtime"]["codex"]["binary"] = "/home/tc442/.local/skillsbench-codex-0.160.1/codex"
fixture_key = "TAU_NATIVE_ADAPTER_CODEX_SCRIPTED_KEY"
os.environ[fixture_key] = "FAKE_LOCAL_FIXTURE_KEY_NOT_AN_AWS_CREDENTIAL"
os.environ.pop(fixture_key + "_FILE", None)
class LocalSpec(ExperimentSpec):
    @property
    def provider_settings(self):
        return {**super().provider_settings, "api_base": f"http://127.0.0.1:{server.server_port}/execution", "api_key_env": fixture_key}
spec = LocalSpec(EXPERIMENT_ROOT / "configs/skillsbench.yaml", values)
adapter = SkillsBenchAdapter(spec, "dialogue-parser", demo=False, counter=lambda s: len(s) // 4,
                            artifact_root=ROOT / "artifacts", model_journal_dir=ROOT / "models")
journal = Journal(ROOT / "journal", identity={"type": "real_native_adapter_codex_grader_fixture"})
evidence = {
    "scenario": "native_context_adapter_codex_real_grader", "context_mode": MODE, "paid_model_calls": 0, "real_model_scores": "NOT_MEASURED",
    "model_source": "MODEL_SCRIPTED", "official_grader": "REAL_PINNED_TASK_GRADER",
    "fixture_base_hash": base.base_hash, "fixture_source_initial_hash": original.bundle_hash,
    "fixture_initial_hash": initial.bundle_hash,
    "fixture_adaptation": "Explicit offline frontmatter and text attachment fixture; no S0 model call is represented.",
    "source_commit": author_source()["commit"], "root": str(ROOT),
    "max_episodes": 120, "max_surrogate_retries": 15, "max_oracles": 5,
    "budget_scope": "Original configured 120/r15/K5; scripted local responses, no model score measured",
}
SOURCE = EXPERIMENT_ROOT / "src/tau_skill_evolution"
SOURCE_NAMES = ("artifacts.py", "container.py", "author_controller.py", "author_verifier.py", "skillsbench_evolution.py", "skillsbench.py", "skillsbench_runtime.py", "codex_runtime.py", "codex_provider.py", "codex_plan.py", "author/VERIFIER_SOURCE.json")
evidence["source_hashes_at_start"] = {n: hashlib.sha256((SOURCE / n).read_bytes()).hexdigest() for n in SOURCE_NAMES}
evidence["fixture_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
containers, core_calls, fresh_records, cleanup_calls = [], {}, [], {}
execution_posts, real_grader_calls, execution_catalogs, fresh_proofs = 0, 0, [], []


def write(path, text):
    return "printf %s " + shlex.quote(base64.b64encode(text.encode()).decode()) + " | base64 -d > " + shlex.quote(path)


def wheel():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        contents = {"tau_native_fixture.py": "VALUE=7\n",
                    "tau_native_fixture-0.0.1.dist-info/METADATA": "Metadata-Version: 2.1\nName: tau-native-fixture\nVersion: 0.0.1\n",
                    "tau_native_fixture-0.0.1.dist-info/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
        contents["tau_native_fixture-0.0.1.dist-info/RECORD"] = "".join(p + ",,\n" for p in contents)
        for p, content in contents.items():
            z.writestr(p, content)
    return base64.b64encode(out.getvalue()).decode()


setup = "set -e; printf %s " + shlex.quote(wheel()) + " | base64 -d > /tmp/tau_native_fixture-0.0.1-py3-none-any.whl; "
setup += "python -m pip install --no-index --no-deps /tmp/tau_native_fixture-0.0.1-py3-none-any.whl; "
setup += write("/root/native_service.py", "from http.server import BaseHTTPRequestHandler,HTTPServer\nclass H(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(b'live-native-service')\nHTTPServer(('127.0.0.1',19764),H).serve_forever()\n")
setup += "; nohup python /root/native_service.py </dev/null >/root/native_service.log 2>&1 & sleep .4; "
setup += "mkdir -p /work/candidate/evals /work/candidate/assets; "
setup += write("/work/candidate/evals/evals.json", files["evals/evals.json"]) + "; "
setup += write("/work/candidate/assets/template.txt", files["assets/template.txt"]) + "; "
setup += write("/work/candidate/scripts/check-assets.sh", files["scripts/check-assets.sh"]) + "; "
setup += "python -m py_compile /work/candidate/scripts/solution.py; "
setup += "test -n \"$(find /work/candidate/scripts/__pycache__ -name '*.pyc' -print -quit)\"; "
setup += "test \"$(sh /app/environment/skills/evo-current/scripts/check-assets.sh)\" = package-asset-v1; "
setup += "printf '{}\\n' | python /app/environment/skills/evo-current/scripts/solution.py; printf bad > /root/native-fixture-output.txt; "
progress = "\n".join("- [x] P" + str(n) + ": complete" for n in range(1, 7)) + "\n"
setup += write("/root/progress.md", progress)
repair = "set -e; printf good > /root/native-fixture-output.txt; printf '\\nOffline package fixture: reusable repair sealed.\\n' >> /work/candidate/SKILL.md; "
repair += "printf '{}\\n' | python /app/environment/skills/evo-current/scripts/solution.py; "
repair += write("/root/progress.md", progress)
suite = """import json
from pathlib import Path
import urllib.request
import tau_native_fixture

def test_persistent_installed_dependency_and_service():
    assert tau_native_fixture.VALUE == 7
    assert urllib.request.urlopen('http://127.0.0.1:19764/',timeout=3).read() == b'live-native-service'

def test_public_outputs():
    assert Path('/root/native-fixture-output.txt').read_text() == 'good'
    graph=json.loads(Path('/app/dialogue.json').read_text())
    assert isinstance(graph['nodes'],list) and graph['nodes']
"""
commands = {"generator": [setup, repair], "verifier": [
    "mkdir -p /root/verifier; " + write("/root/verifier/test_outputs.py", suite),
    write("/root/verifier/diagnosis.md", "The public fixture output is incomplete. Complete its public requirement without changing the locked checks.") ]}
cursor = {"generator": 0, "verifier": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        global execution_posts
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/execution/responses":
            execution_posts += 1
            assert execution_posts <= 18, "unexpected extra real CLI scripted request"
            catalog = payload.get("tools") or [t for i in payload.get("input", []) if isinstance(i,dict) and i.get("type")=="additional_tools" for t in i["tools"]]
            execution_catalogs.append([{k:t.get(k) for k in ("type","name")} for t in catalog])
            if execution_posts % 2:
                command = fresh_task_command()
                item = {"type":"function_call", "id":f"fc_native_{execution_posts}", "call_id":f"native_{execution_posts}", "name":"exec_command", "arguments":json.dumps({"cmd":command,"yield_time_ms":1000,"max_output_tokens":2000}), "status":"completed"}
                if any(t.get("name")=="functions" for t in catalog):
                    item = {"type":"custom_tool_call", "id":f"custom_native_{execution_posts}", "call_id":f"native_{execution_posts}", "namespace":"functions", "name":"exec", "input":"text(await tools.exec_command("+item["arguments"]+"));", "status":"completed"}
            else:
                item = {"type":"message", "id":f"msg_native_{execution_posts}", "role":"assistant", "status":"completed", "content":[{"type":"output_text","text":"Scripted local execution completed.","annotations":[]}]}
            response = json.dumps({"id":f"resp_native_{execution_posts}","object":"response","model":values["provider"]["model"],"status":"completed","output":[item],"usage":{"input_tokens":10,"output_tokens":10,"total_tokens":20,"input_tokens_details":{"cached_tokens":0}}}).encode()
            self.send_response(200); self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(response)));self.end_headers();self.wfile.write(response);return
        role = self.path.lstrip("/")
        n = cursor[role]
        cursor[role] += 1
        if n >= 12:
            self.send_error(500, "Unexpected additional fixture request")
            return
        n = min(n, len(commands[role])-1)
        content = json.dumps({"analysis": "Offline package transport fixture", "plan": "Execute public fixture requirements",
                              "commands": [{"keystrokes": commands[role][n], "duration": 0.1}], "task_complete": True})
        response = json.dumps({"id": f"localhost-package-{role}-{n}", "status": "completed", "output": [
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": content}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()


def model(role):
    def opener(request, *, timeout):
        return urllib.request.urlopen(urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/{role}", data=request.data,
            headers={"Content-Type": "application/json"}), timeout=timeout)
    class ScriptedClient(OpenAICompatibleClient):
        def complete_journaled(self, *args, **kwargs):
            if role == "generator" and MODE == "predispatch" and cursor[role] >= 1:
                raise InputTokenBudgetExceeded(160000, 157632)
            result = super().complete_journaled(*args, **kwargs)
            if role == "generator" and MODE == "observed" and cursor[role] >= 2:
                result["context_budget"] = {"context_window":258400,"input_tokens":185730,"output_tokens":2096,"reserve_tokens":32768}
            return result
    return ScriptedClient("https://bedrock-mantle.us-east-1.api.aws",
                                  config=GenerationConfig(model="openai.gpt-5.4", transport="bedrock-responses", max_output_tokens=None), opener=opener, timeout_seconds=60)


def observe_cleanup(runner):
    original_stop = runner._stop_episode
    def stop():
        container = runner.container_name
        if container is not None:
            cleanup_calls[container] = cleanup_calls.get(container, 0) + 1
        return original_stop()
    runner._stop_episode = stop


def fresh_task_command():
    expected = {p:hashlib.sha256(c.encode()).hexdigest() for p,c in dict(current_selected_package()).items()}
    proof = "from pathlib import Path; import hashlib,json,importlib.util; root=Path('/app/environment/skills/evo-current'); expected="+repr(expected)+"; "
    proof += "p={'full_package_hashes_match':all(hashlib.sha256((root/k).read_bytes()).hexdigest()==v for k,v in expected.items()), 'private_tests_absent_during_execution':not Path('/tests/test.sh').exists(), 'learning_state_absent':not Path('/root/native-fixture-output.txt').exists() and importlib.util.find_spec('tau_native_fixture') is None}; "
    proof += "assert all(p.values()),p; Path('/app/native-codex-public-proof.json').write_text(json.dumps(p)); print(json.dumps(p))"
    return "set -e; python3 -c " + shlex.quote(proof) + "; test \"$(sh /app/environment/skills/evo-current/scripts/check-assets.sh)\" = package-asset-v1; printf '{}\\n' | python3 /app/environment/skills/evo-current/scripts/solution.py"


def current_selected_package():
    # Read only the already installed public package copy, never model/provider logs.
    package = ROOT / 'learning/work/candidate'
    if package.is_dir():
        return {p.relative_to(package).as_posix():p.read_text() for p in package.rglob('*') if p.is_file() and p.suffix not in {'.pyc','.pyo'} and '__pycache__' not in p.parts and p.name!='manifest.json'}
    return dict(initial.files)


original_start = adapter.runner._start_episode
original_grade = adapter.runner.grade
original_snapshot = adapter._snapshot
def start_episode(episode):
    original_start(episode)
    containers.append(adapter.runner.container_name)
def grade_episode(episode):
    global real_grader_calls
    real_grader_calls += 1
    return original_grade(episode)
def snapshot_episode(episode):
    value = original_snapshot(episode)
    files_root = Path(value['public_artifacts_dir'])
    proof = files_root / 'app/native-codex-public-proof.json'
    assert proof.is_file(), 'Native Codex execution did not create the public proof'
    fresh_proofs.append({**json.loads(proof.read_text()), 'public_snapshot_hash':value['public_artifacts_hash']})
    return value
adapter.runner._start_episode = start_episode
adapter.runner.grade = grade_episode
adapter._snapshot = snapshot_episode
observe_cleanup(adapter.runner)


native = author_module("agents.terminus_2.harbor_terminus_2_evolution").HarborTerminus2Evolution
core_codes = {getattr(native, n).__code__: n for n in ("run", "_check_episode_exit", "_read_progress_checklist", "_maybe_save_best_snapshot", "_rollback_host_skills")}


def profile(frame, event, arg):
    if event == "call" and frame.f_code in core_codes:
        name = core_codes[frame.f_code]
        core_calls[name] = core_calls.get(name, 0) + 1




try:
    deadline = time.time() + 7200
    with adapter.evolution_session(initial, base.public_inputs, base, journal=journal,
                                   workspace=ROOT / "learning", deadline=deadline) as session:
        observe_cleanup(session.runner)
        learning_id = session.runner.container_name
        containers.append(learning_id)
        sys.setprofile(profile)
        try:
            result = run_author_evolution(session, initial, base, model("generator"), model("verifier"),
                journal=journal, root=ROOT, token_counter=lambda s: len(s) // 4,
                settings={"max_input_tokens": 157632, "context_window": 272000, "max_episodes": evidence["max_episodes"]},
                deadline=deadline, adapter_prompt="Offline fixture only. Verify public outputs and shared dependency/service. No hidden grader is supplied.")
        finally:
            sys.setprofile(None)
        assert result.stop_reason == "token_budget", result.stop_reason
        assert result.author_counters["normal_oracle_interventions"] == 0
        assert result.author_counters["surrogate_retries"] == 1
        assert cursor["generator"] == (2 if MODE == "observed" else 1), cursor
        assert result.author_counters["generator_model_attempts"] == 2
        assert result.author_counters["generator_responses"] == cursor["generator"]
        assert len(result.versions) == (2 if MODE == "observed" else 1)
        assert result.verifications[0]["pass_rate"] == 0.5
        selected = next(b for b in result.versions if b.bundle_hash == result.final_bundle_hash)
        assert all(p in selected.files for p in ("evals/evals.json", "assets/template.txt", "scripts/check-assets.sh"))
        assert not any(Path(p).suffix in {".pyc", ".pyo"} for p in selected.files)
        assert result.oracle_calls == 1
        assert result.oracle_history[0]["phase"] == "post_final"
        assert result.oracle_history[0]["status"] == "MEASURED"
        assert execution_posts >= 2 and real_grader_calls >= 1
        oracle_requests = execution_posts
        independent = adapter.evaluate(selected)
        assert independent["status"] == "MEASURED", independent
        assert execution_posts >= oracle_requests + 2
        independent_record = {k: independent.get(k) for k in ("status", "utility", "reward", "official_checks", "execution_termination_reason")}
        assert fresh_proofs and all(item["full_package_hashes_match"] and item["private_tests_absent_during_execution"] and item["learning_state_absent"] for item in fresh_proofs)
        evidence.update(status="PASS", result=result.to_dict(), independent_evaluation=independent_record,
                        fresh_package_checks=fresh_proofs, real_official_grader_calls=real_grader_calls,
                        scripted_Codex_requests=execution_posts, execution_provider_tool_catalogs=execution_catalogs,
                        code_path="run_author_evolution -> native async run -> actual adapter.oracle -> actual execute_codex -> pinned Codex CLI -> localhost Responses -> actual official grade", core_calls=core_calls,
                        raw_controller_sha256=hashlib.sha256(Path(sys.modules[native.__module__].__file__).read_bytes()).hexdigest(),
                        local_model_requests=cursor, learning_container_id=learning_id,
                        shared_dependency_and_service=True, fixed_suite_reused=True,
                        candidate_legal_attachments_and_cache_exercised=True,
                        oracle_best_independent_full_hash_match=True,
                        generator_verifier_separate_clients=True, fresh_environment_separation=True)
except BaseException as exc:
    evidence.update(status="FAIL", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc(),
                    core_calls=core_calls, local_model_requests=cursor, containers=containers)
    raise
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    evidence["container_residuals"] = [c for c in containers if subprocess.run(["docker", "inspect", c], capture_output=True).returncode == 0]
    evidence["cleanup_calls"] = cleanup_calls
    evidence["unique_cleanup_verified"] = all(cleanup_calls.get(c) == 1 for c in containers)
    evidence["cleanup_verified"] = not evidence["container_residuals"] and evidence["unique_cleanup_verified"]
    evidence["source_hashes_at_finish"] = {n: hashlib.sha256((SOURCE / n).read_bytes()).hexdigest() for n in SOURCE_NAMES}
    evidence["source_unchanged_during_execution"] = evidence["source_hashes_at_start"] == evidence["source_hashes_at_finish"]
    evidence["limitations"] = [
        "Generator, Verifier, and native Codex provider responses are MODEL_SCRIPTED localhost fixtures; this is not a real model utility measurement.",
        "SkillsBenchAdapter.oracle, execute_codex, pinned native CLI, Docker task environment, and pinned official grader are real and unmocked; actual grader reward may be zero.",
        "Initial text attachments and name were prepared outside inference as explicit fixture inputs; no model S0 creation or fee was incurred.",
    ]
    if evidence.get("status") == "PASS" and (not evidence["cleanup_verified"] or not evidence["source_unchanged_during_execution"]):
        evidence["status"] = "FAIL"
        evidence["error"] = "cleanup/source-stability verification failed"
    output = EVIDENCE / ("full-controller-context-" + MODE + "-private.json")
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    output.chmod(0o600)
    print(json.dumps({k: evidence[k] for k in ("scenario", "status", "paid_model_calls", "official_grader", "cleanup_verified", "source_unchanged_during_execution")}, indent=2))
    assert evidence["status"] == "PASS", output
