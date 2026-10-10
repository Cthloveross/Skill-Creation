"""Fresh five-task API trial with read-only input discovery. Run from the repository root."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import threading
import time
import traceback

from tau_skill_evolution.artifacts import atomic_json
from tau_skill_evolution.cli import load_env, run_locks
from tau_skill_evolution.model import authentication_status
from tau_skill_evolution.spec import load_spec
from tau_skill_evolution.workflow import Workflow

PACK = Path(__file__).resolve().parent
RUN = PACK / "matrix"
TASKS = (
    "dialogue-parser", "3d-scan-calc", "adaptive-cruise-control",
    "dapt-intrusion-detection", "pddl-tpp-planning",
)
STOP = threading.Event()
SPEC = load_spec(PACK / "config.yaml")
load_env(Path(__file__).resolve().parents[6] / "key.env")


def task_run(task):
    status = {"task": task, "started_at": time.time(), "status": "RUNNING"}
    destination = PACK / "status" / f"{task}.json"
    atomic_json(destination, status)
    if STOP.is_set():
        status["status"] = "NOT_STARTED_PROVIDER_UNAVAILABLE"
        atomic_json(destination, status)
        return status
    try:
        cell = ((task, "benign"),)
        with run_locks(RUN, cell):
            workflow = Workflow(SPEC, RUN, runtime="docker", interim_report=False)
            print(f"{task}: NoSkill started", flush=True)
            workflow.evaluate_no_skill(cell)
            print(f"{task}: create/evolve/evaluate started", flush=True)
            workflow.run(cell)
        status["status"] = "STAGES_FINISHED"
    except BaseException as error:
        status.update(status="FAILED", error_type=type(error).__name__,
                      error_code=getattr(error, "code", None),
                      authentication_status=authentication_status(error))
        (PACK / "status" / f"{task}.error.log").write_text(traceback.format_exc())
        if authentication_status(error) is not None:
            STOP.set()
    finally:
        status["finished_at"] = time.time()
        atomic_json(destination, status)
    print(json.dumps(status), flush=True)
    return status


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = [future.result() for future in as_completed(
            [pool.submit(task_run, task) for task in TASKS])]
    with run_locks(RUN, ()):
        Workflow(SPEC, RUN, runtime="docker").report()
    atomic_json(PACK / "launcher-results.json", results)
