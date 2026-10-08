"""Execute pinned controller branches and compare their decisions with our engine.

The fixture contains byte-preserved cap/post-run source excerpts, not a rewritten
oracle. Task execution and snapshot I/O are stubs; the original branch code runs.
"""

import asyncio
import hashlib
import json
import logging
import math
import shutil
import textwrap
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_author_evolution import Session, bundle, run


class ReleasedController:
    def __init__(self, normal_count, retries, rewards, best=None, invalid_schema=False):
        self._host_intervention_count = normal_count
        self._surrogate_retry_count = retries
        self._max_host_interventions = 5
        self._max_surrogate_retries = 15
        self._gt_oracle_model = None
        self._model_name = "local-fixture"
        self._instruction = "public task"
        self._exit_reason = "execution_done"
        self._best_gt_snapshot = self.score(best) if best is not None else None
        if self._best_gt_snapshot:
            self._best_gt_snapshot.update(skills_dir="best-snapshot", intervention_number=1)
        self._skill_schema_validation_history = []
        self.rewards = deque(rewards)
        self.calls = []
        self.rollbacks = []
        self.invalid_schema = invalid_schema
        self.last_pass = False
        self._intervention_history = []

    @staticmethod
    def score(reward):
        return {
            "passed": reward == 1,
            "reward": reward,
            "pass_rate": reward,
            "tests_passed": int(reward * 100),
            "total_tests": 100,
        }

    def _recorded_best_gt_result(self):
        return self._best_gt_snapshot

    async def _record_intervention(self, environment, **kwargs):
        value = {**kwargs, "gt_result": None}
        self._intervention_history.append(value)
        return value

    async def _export_evolved_skills_to_host(self, environment):
        return "current-snapshot"

    async def _audit_exported_evolved_skills(self, *args, **kwargs):
        return []

    async def _run_gt_oracle_check(self, *args, oracle_label, **kwargs):
        self.calls.append(oracle_label)
        value = self.score(self.rewards.popleft())
        self.last_pass = value["passed"]
        return value

    async def _maybe_save_best_snapshot(self, environment, value, intervention_number):
        if self._best_gt_snapshot is None or value["reward"] > self._best_gt_snapshot["reward"]:
            self._best_gt_snapshot = {
                **value,
                "skills_dir": "best-snapshot",
                "intervention_number": intervention_number,
            }

    async def _find_evolved_skill_manifests(self, environment):
        return ["current/SKILL.md"]

    async def _validate_evolved_skill_schema(self, environment):
        return ["invalid name"] if self.invalid_schema else []

    def _did_last_oracle_pass(self):
        return self.last_pass

    def _rollback_host_skills(self, environment, skills_dir):
        self.rollbacks.append(skills_dir)

    def _extract_task_name(self, environment):
        return "fixture"

    def _write_oracle_stop_signal(self, *args, **kwargs):
        pass


def released_branch(name):
    fixture = json.loads((Path(__file__).parent / "fixtures/author-selection.json").read_text())
    assert fixture["commit"] == "4380d4bff673dd6e1d58e5babeb2aaa0fe527119"
    block = fixture["blocks"][name]
    assert hashlib.sha256(block["source"].encode()).hexdigest() == block["sha256"]
    globals_ = {
        "logger": logging.getLogger(__name__),
        "_evo_print": lambda *a: None,
        "shutil": shutil,
        "datetime": datetime,
        "UTC": UTC,
        "ClaudeCodeProviderError": type("ProviderError", (Exception,), {}),
        "EpisodeExitResult": lambda **kwargs: SimpleNamespace(**kwargs),
        "math": math,
    }
    exec(
        "from __future__ import annotations\n"
        + textwrap.dedent(fixture["blocks"]["reward"]["source"]),
        globals_,
    )
    ReleasedController._gt_full_score_and_reward = staticmethod(
        globals_["_gt_full_score_and_reward"]
    )
    if name == "post_final":
        prefix = (
            "    main_intervention_count = self._host_intervention_count\n"
            "    gt_oracle_result = None\n"
        )
        suffix = "\n    return gt_oracle_result\n"
    else:
        prefix = suffix = ""
    body = textwrap.indent(textwrap.dedent(block["source"]), "    ")
    exec("async def branch(self, environment):\n" + prefix + body + suffix, globals_)
    return globals_["branch"]


@pytest.mark.parametrize("normal_count,retries,score", [(0, 15, 0.25), (4, 15, 0.35), (0, 15, 1.0)])
def test_r15_cap_and_post_final_requests_match_released_branches(normal_count, retries, score):
    earlier = 0.4 if normal_count else None
    source = ReleasedController(normal_count, retries, [score, 0.2], earlier)
    cap = asyncio.run(released_branch("cap")(source, None))
    retained = asyncio.run(released_branch("post_final")(source, None))
    checks = [True] * normal_count + [False] * 15
    rewards = ([0.4, 0.3, 0.2, 0.1] if normal_count else []) + [score]
    if score != 1:
        rewards.append(0.2)
    result, _, _, local_calls = run(checks, rewards)
    assert cap.should_exit
    assert len(source.calls) == len(local_calls) - normal_count
    assert result.author_terminal_result["resolved_reward"] == retained["reward"]
    assert (result.stop_reason == "oracle_success") == retained["passed"]


def test_normal_k5_reuses_best_and_rolls_back_without_sixth_gt():
    source = ReleasedController(5, 0, [], best=0.75)
    asyncio.run(released_branch("cap")(source, None))
    retained = asyncio.run(released_branch("post_final")(source, None))
    result, _, session, calls = run([True] * 5, [0.25, 0.75, 0.42, 0.75, 0.2])
    assert not source.calls and len(calls) == 5
    assert source.rollbacks and session.rollbacks
    assert result.author_terminal_result["resolved_reward"] == retained["reward"] == 0.75


def test_schema_gate_has_priority_over_best_score_and_rollback():
    source = ReleasedController(5, 0, [], best=0.75, invalid_schema=True)
    retained = asyncio.run(released_branch("post_final")(source, None))
    session = Session()

    def invalid_revision(parent):
        session.invalid_schema = True
        return bundle("invalid", parent.bundle_hash)

    result, _, _, calls = run([True], [0.75], session=session, revisions=invalid_revision)
    assert retained["source"] == "skill_schema_gate"
    assert not source.calls and not source.rollbacks
    assert result.selection_reason == "skill_schema_gate"
    assert len(calls) == 1 and not session.rollbacks
