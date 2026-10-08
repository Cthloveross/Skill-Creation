import base64
import hashlib
import io
import json
import shlex
import subprocess
import sys
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
from tau_skill_evolution.journal import Journal
from tau_skill_evolution.model import GenerationConfig, OpenAICompatibleClient
from tau_skill_evolution.skillsbench import SkillsBenchAdapter
from tau_skill_evolution.skillsbench_evolution import run_author_evolution
from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner
from tau_skill_evolution.spec import ExperimentSpec


ROOT = Path('/tmp/coevo-full-controller-docker-proof-006')
ROOT.mkdir(exist_ok=False)
OLD = EXPERIMENT_ROOT / 'runs/skillsbench/codex-quota-five-20261007-003/matrix/cells/dialogue-parser/benign'
base, initial = load_base(OLD / 'base'), load_bundle(OLD / 'initial')
source_fixture_hash = initial.bundle_hash
files = dict(initial.files)
files['SKILL.md'] = files['SKILL.md'].replace('name: current\n', 'name: evo-current\n', 1)
initial = SkillBundle(files)
values = yaml.safe_load((EXPERIMENT_ROOT / 'configs/skillsbench.yaml').read_text())
values['source']['runtime_lock'] = 'runtime/skillsbench-docker-dialogue-parser-v4-lock.json'
spec = ExperimentSpec(EXPERIMENT_ROOT / 'configs/skillsbench.yaml', values)
adapter = SkillsBenchAdapter(spec, 'dialogue-parser', demo=False, counter=lambda s: len(s)//4,
                            artifact_root=ROOT/'artifacts', model_journal_dir=ROOT/'models')
journal = Journal(ROOT/'journal', identity={'type':'real_docker_local_mock_author_controller', 'task':'dialogue-parser'})
evidence = {'paid_model_calls':0, 'real_model_scores':'NOT_MEASURED', 'official_reward':'MOCK_ONLY',
            'fixture_base_hash':base.base_hash, 'fixture_initial_hash':initial.bundle_hash,
            'fixture_source_hash':source_fixture_hash, 'fixture_adaptation':'Explicit offline frontmatter name adaptation; not a model result.',
            'source_commit':author_source()['commit'], 'root':str(ROOT)}
SOURCE = EXPERIMENT_ROOT / 'src/tau_skill_evolution'
evidence['source_hashes_at_start'] = {
    name: hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
    for name in ('author_controller.py','author_verifier.py','skillsbench_evolution.py','author/VERIFIER_SOURCE.json')
}
evidence['fixture_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
containers, requests, core_calls = [], [], {}


def write(path, text):
    return 'printf %s ' + shlex.quote(base64.b64encode(text.encode()).decode()) + ' | base64 -d > ' + shlex.quote(path)


def wheel():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        files={'tau_native_fixture.py':'VALUE=7\n',
               'tau_native_fixture-0.0.1.dist-info/METADATA':'Metadata-Version: 2.1\nName: tau-native-fixture\nVersion: 0.0.1\n',
               'tau_native_fixture-0.0.1.dist-info/WHEEL':'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
        files['tau_native_fixture-0.0.1.dist-info/RECORD']=''.join(p+',,\n' for p in files)
        for p,v in files.items(): z.writestr(p,v)
    return base64.b64encode(out.getvalue()).decode()


setup = 'set -e; ' + ('printf %s '+shlex.quote(wheel())+' | base64 -d > /tmp/tau_native_fixture-0.0.1-py3-none-any.whl; ')
setup += 'python -m pip install --no-index --no-deps /tmp/tau_native_fixture-0.0.1-py3-none-any.whl; '
setup += write('/root/native_service.py', "from http.server import BaseHTTPRequestHandler,HTTPServer\nclass H(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(b'live-native-service')\nHTTPServer(('127.0.0.1',19764),H).serve_forever()\n")
setup += '; nohup python /root/native_service.py </dev/null >/root/native_service.log 2>&1 & sleep .4; '
setup += "printf '{}\\n' | python /app/environment/skills/evo-current/scripts/solution.py; "
setup += "printf bad > /root/native-fixture-output.txt; "
setup += write('/root/progress.md','\n'.join('- [x] P'+str(n)+': complete' for n in range(1,7))+'\n')
repair = "set -e; printf good > /root/native-fixture-output.txt; printf '\\nOffline transport fixture: reusable package changed.\\n' >> /work/candidate/SKILL.md; "
repair += "printf '{}\\n' | python /app/environment/skills/evo-current/scripts/solution.py"
repair += '; ' + write('/root/progress.md','\n'.join('- [x] P'+str(n)+': complete' for n in range(1,7))+'\n')
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
commands={'generator':[setup,repair], 'verifier':[
    'mkdir -p /root/verifier; '+write('/root/verifier/test_outputs.py',suite),
    write('/root/verifier/diagnosis.md','The public fixture output is incomplete. Complete its public requirement without changing the locked checks.')]}
cursor={'generator':0,'verifier':0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        role=self.path.lstrip('/')
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        requests.append({'role':role,'payload':payload})
        n=cursor[role];cursor[role]+=1
        if n>=len(commands[role]):
            self.send_error(500,'Unexpected additional fixture request');return
        content=json.dumps({'analysis':'Offline native transport fixture','plan':'Execute current public obligations',
                            'commands':[{'keystrokes':commands[role][n],'duration':.1}], 'task_complete':True})
        response=json.dumps({'id':f'localhost-native-{role}-{n}','status':'completed','output':[
            {'type':'message','role':'assistant','content':[{'type':'output_text','text':content}]}],
            'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)


server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()


def model(role):
    def opener(request,*,timeout):
        return urllib.request.urlopen(urllib.request.Request(
            f'http://127.0.0.1:{server.server_port}/{role}',data=request.data,
            headers={'Content-Type':'application/json'}),timeout=timeout)
    return OpenAICompatibleClient('https://bedrock-mantle.us-east-1.api.aws',
        config=GenerationConfig(max_output_tokens=None),opener=opener,timeout_seconds=60)


native=author_module('agents.terminus_2.harbor_terminus_2_evolution').HarborTerminus2Evolution
core_codes={getattr(native,n).__code__:n for n in ('run','_check_episode_exit','_read_progress_checklist')}


def profile(frame,event,arg):
    if event=='call' and frame.f_code in core_codes:
        name=core_codes[frame.f_code];core_calls[name]=core_calls.get(name,0)+1


try:
    deadline=time.time()+420
    with adapter.evolution_session(initial,base.public_inputs,base,journal=journal,
                                   workspace=ROOT/'learning',deadline=deadline) as session:
        learning_id=session.runner.container_name;containers.append(learning_id)
        def oracle(bundle,*,phase='normal'):
            assert session.runner.container_name==learning_id and session.runner.public_open
            fresh=SkillsBenchRunner(EXPERIMENT_ROOT,'dialogue-parser',demo=False,
                       runtime_lock_path=EXPERIMENT_ROOT/values['source']['runtime_lock'])
            with fresh.episode(bundle) as episode:
                containers.append(fresh.container_name)
                assert fresh.container_name!=learning_id
                result=fresh._exec(['/bin/bash','-c',"set -e; test ! -e /root/native-fixture-output.txt; python -c \"import importlib.util; assert importlib.util.find_spec('tau_native_fixture') is None\"; printf '{}\\n' | python /bundle/scripts/solution.py"],public=True)
                assert result.returncode==0 and not result.failure,result.stderr.decode()
                assert episode.files==dict(bundle.files)
            return {'status':'MEASURED','passed':True,'canonical_reward':1.0,'resolved_reward':1.0,
                    'reward':1.0,'tests_passed':1,'total_tests':1,'test_details':[{'name':'MOCK_ONLY','status':'passed'}],
                    'bundle_hash':bundle.bundle_hash,'parent_hash':bundle.parent_hash,'phase':phase,
                    'execution_id':containers[-1],'score_source':'local_mock_not_official_grader'}
        adapter.oracle=oracle
        sys.setprofile(profile)
        try:
            result=run_author_evolution(session,initial,base,model('generator'),model('verifier'),
                journal=journal,root=ROOT,token_counter=lambda s:len(s)//4,
                settings={'max_input_tokens':200000,'context_window':272000,'max_episodes':8},
                deadline=deadline,adapter_prompt='Offline fixture only. Verify actual public outputs and shared dependency/service. No hidden grader is supplied.')
        finally: sys.setprofile(None)
        assert result.stop_reason=='gt_oracle_pass',result.to_dict()
        assert result.author_counters.get('normal_oracles',result.author_counters.get('normal_oracle_interventions'))==1
        assert result.author_counters['surrogate_retries']==1
        assert len(result.versions)==2
        assert len(result.oracle_history)==1
        assert cursor=={'generator':2,'verifier':2},cursor
        evidence.update(status='PASS',result=result.to_dict(),core_calls=core_calls,
                        raw_controller_sha256=hashlib.sha256(Path(sys.modules[native.__module__].__file__).read_bytes()).hexdigest(),
                        local_model_requests=cursor,learning_container_id=learning_id,
                        fresh_container_ids=containers[1:],shared_dependency_and_service=True,
                        fixed_suite_reused=True,task_container_not_cleaned_by_verifier=True,
                        generator_verifier_separate_clients=True,fresh_environment_separation=True)
except BaseException as exc:
    evidence.update(status='FAIL',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc(),
                    core_calls=core_calls,local_model_requests=cursor,containers=containers)
    raise
finally:
    server.shutdown();server.server_close();thread.join(timeout=5)
    evidence['container_residuals']=[c for c in containers if subprocess.run(['docker','inspect',c],capture_output=True).returncode==0]
    evidence['cleanup_verified']=not evidence['container_residuals']
    evidence['source_hashes_at_finish'] = {
        name: hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
        for name in evidence['source_hashes_at_start']
    }
    evidence['source_unchanged_during_execution'] = evidence['source_hashes_at_start'] == evidence['source_hashes_at_finish']
    evidence['limitations'] = [
        'Scripted localhost model and mocked official reward; no real model capability or official task success was measured.',
        'The GT callback used a separate fresh real Docker Runner and sealed package, with mocked score.',
        'This fixture uses maximum 8 episodes and 420 seconds; budget exhaustion requires separate offline cases.',
        'Original published run and _check_episode_exit methods executed, with local task transport/evidence I/O hooks.'
    ]
    Path('/tmp/coevo-full-controller-docker-proof.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
