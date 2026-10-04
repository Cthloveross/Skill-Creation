from copy import deepcopy

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.evaluation import (
    case_views,
    completion_steps,
    evaluate_versions,
    not_measured,
    report_cases,
)


def test_each_content_version_evaluated_once_package_only():
    initial = SkillBundle({"SKILL.md": "initial"})
    updated = SkillBundle({"SKILL.md": "updated"}, parent_hash=initial.bundle_hash)
    calls = []

    def evaluate(bundle):
        calls.append(bundle)
        return {"utility": True, "asr": False, "official_result": {"reward": 1}}

    evaluations = evaluate_versions([initial, initial, updated], evaluate)
    assert calls == [initial, updated] and len(evaluations) == 2
    case = {
        "task_id": "t1",
        "condition": "poison-5",
        "evolution": {
            "versions": [initial.to_dict(), updated.to_dict()],
            "final_bundle_hash": updated.bundle_hash,
            "stop_reason": "oracle_success",
        },
        "evaluations": evaluations,
    }
    assert case_views(case)["frozen"] is evaluations[initial.bundle_hash]
    assert case_views(case)["evolved"] is evaluations[updated.bundle_hash]


def test_missing_measurements_null_and_full_task_denominator():
    bundle = SkillBundle({"SKILL.md": "s"})
    measured = evaluate_versions([bundle], lambda b: {"utility": True, "asr": False})
    cases = [
        {
            "task_id": "t1",
            "condition": "poison-5",
            "versions": [bundle.to_dict()],
            "evaluations": measured,
        },
        {"task_id": "t2", "condition": "poison-5", "creation_failure": "invalid_package"},
    ]
    report = report_cases(cases)
    arm = next(
        row for row in report["arms"] if row["condition"] == "poison-5" and row["arm"] == "evolved"
    )
    assert arm["task_denominator"] == 97 and arm["measured_count"] == 1
    assert arm["not_measured_count"] == 96 and arm["end_to_end_utility"] == 1 / 97
    assert arm["actual_chains"] == 1
    assert case_views(cases[1])["evolved"]["utility"] is None
    assert case_views(cases[1])["evolved"]["asr"] is None
    assert case_views(cases[1])["evolved"]["status"] == "NOT_MEASURED"


def test_failed_evaluation_not_disguised_as_measured_zero():
    bundle = SkillBundle({"SKILL.md": "s"})

    def evaluator(_):
        raise RuntimeError("worker failed")

    result = evaluate_versions([bundle], evaluator)[bundle.bundle_hash]
    assert (
        result["status"] == "NOT_MEASURED" and result["utility"] is None and result["asr"] is None
    )
    assert not_measured()["utility"] is None


def test_early_stop_reports_actual_versions_only():
    bundle = SkillBundle({"SKILL.md": "s"})
    report = report_cases(
        [
            {
                "condition": "benign",
                "task_id": "t1",
                "evolution": {
                    "versions": [bundle.to_dict()],
                    "final_bundle_hash": bundle.bundle_hash,
                    "stop_reason": "oracle_success",
                },
                "evaluations": {},
            }
        ]
    )
    assert len(report["versions"]) == 1
    assert report["versions"][0]["status"] == "NOT_MEASURED"


def test_round_summaries_use_existing_chains_without_padding_or_imputed_scores():
    early = SkillBundle({"SKILL.md": "early success"})
    initial = SkillBundle({"SKILL.md": "second initial"})
    revised = SkillBundle({"SKILL.md": "second revised"}, parent_hash=initial.bundle_hash)
    cases = [
        {
            "condition": "poison-5",
            "task_id": "early",
            "evolution": {
                "versions": [early.to_dict()],
                "final_bundle_hash": early.bundle_hash,
                "stop_reason": "oracle_success",
            },
            "evaluations": evaluate_versions([early], lambda _: {"utility": True, "asr": False}),
        },
        {
            "condition": "poison-5",
            "task_id": "revised",
            "evolution": {
                "versions": [initial.to_dict(), revised.to_dict()],
                "final_bundle_hash": revised.bundle_hash,
                "stop_reason": "revision_budget_exhausted",
            },
            "evaluations": evaluate_versions([initial], lambda _: {"utility": False, "asr": True}),
        },
        {"condition": "poison-5", "task_id": "failed", "creation_failure": "invalid_package"},
    ]
    report = report_cases(cases)
    assert len(report["rounds"]) == 2
    first, second = report["rounds"]
    assert first["version"] == 0 and first["actual_chains"] == first["measured_count"] == 2
    assert first["measured_utility"] == first["measured_asr"] == 0.5
    assert first["stop_counts"] == {"oracle_success": 1}
    assert second["version"] == 1 and second["actual_chains"] == 1
    assert second["measured_count"] == 0 and second["not_measured_count"] == 1
    assert second["measured_utility"] is None and second["measured_asr"] is None
    assert second["stop_counts"] == {"revision_budget_exhausted": 1}
    assert len(report["versions"]) == 3


def _action_check(name, actor, matched):
    return {
        "action": {
            "action_id": name,
            "requestor": actor,
            "name": name,
            "arguments": {"user_id": "public-user"},
            "info": None,
            "compare_args": ["user_id"],
        },
        "action_match": matched,
        "action_reward": 1.0 if matched else 0.0,
        "tool_type": None,
    }


def test_reference_action_rate_keeps_actors_and_excludes_other_reward_denominators():
    bundle = SkillBundle({"SKILL.md": "s"})
    reward_info = {
        "reward": 0.0,
        "reward_basis": ["DB"],
        "db_check": {"db_match": False, "db_reward": 0.0},
        "env_assertions": [{"met": False}],
        "action_checks": [
            _action_check("read_account", "assistant", True),
            _action_check("grant_permission", "user", False),
            _action_check("communicate_result", "assistant", True),
        ],
        "communicate_checks": [{"info": "required information", "met": False}],
        "nl_assertions": [{"met": False}],
    }
    original = deepcopy(reward_info)
    evaluations = evaluate_versions(
        [bundle], lambda _: {"utility": False, "asr": False, "reward_info": reward_info}
    )
    measurement = evaluations[bundle.bundle_hash]
    steps = measurement["completion_steps"]
    assert steps["status"] == "MEASURED"
    assert (steps["matched"], steps["expected"], steps["rate"]) == (2, 3, 2 / 3)
    assert steps["source"] == "reward_info.action_checks"
    assert steps["steps"][1] == {
        "action": "grant_permission",
        "actor": "user",
        "arguments": {"user_id": "public-user"},
        "matched": False,
    }
    assert measurement["utility"] is False
    assert measurement["metrics"]["reward_info"] == reward_info == original


@pytest.mark.parametrize(
    "reward_info",
    [None, {"db_check": {"db_match": True}}, {"action_checks": None}, {"action_checks": []}],
)
def test_missing_or_empty_reference_checks_are_not_measured(reward_info):
    steps = completion_steps({"reward_info": reward_info})
    assert steps["status"] == "NOT_MEASURED"
    assert steps["matched"] is steps["expected"] is steps["rate"] is None
    assert steps["steps"] == []


@pytest.mark.parametrize("matched", [1, 0, "true", None])
def test_reference_matches_require_real_boolean_results(matched):
    steps = completion_steps(
        {"reward_info": {"action_checks": [_action_check("read", "assistant", matched)]}}
    )
    assert steps["status"] == "NOT_MEASURED" and steps["rate"] is None
    assert steps["reason"] == "invalid_action_checks"


def test_report_derives_reference_rate_without_mutating_sealed_measurements():
    first = SkillBundle({"SKILL.md": "old evaluation"})
    second = SkillBundle({"SKILL.md": "new evaluation"}, parent_hash=first.bundle_hash)
    evaluations = {
        first.bundle_hash: {
            "status": "MEASURED",
            "utility": False,
            "asr": False,
            "metrics": {"utility": False, "asr": False},
        },
        second.bundle_hash: {
            "status": "MEASURED",
            "utility": True,
            "asr": False,
            "metrics": {
                "reward_info": {
                    "reward_basis": ["DB"],
                    "action_checks": [_action_check("reference_write", "assistant", False)],
                }
            },
        },
    }
    original = deepcopy(evaluations)
    report = report_cases(
        [
            {
                "task_id": "t1",
                "condition": "benign",
                "versions": [first, second],
                "evaluations": evaluations,
            }
        ]
    )
    old, new = report["versions"]
    assert old["completion_steps"]["status"] == "NOT_MEASURED"
    assert new["completion_steps"]["rate"] == 0.0 and new["utility"] is True
    assert evaluations == original


def test_skillsbench_reward_without_asr_is_measured_and_uses_85_denominator():
    initial = SkillBundle({"SKILL.md": "file task"})
    evaluations = evaluate_versions(
        [initial],
        lambda _: {
            "utility": 0.0,
            "reward": 0.5,
            "asr": None,
            "asr_status": "NOT_APPLICABLE",
            "official_checks": {"passed": 1, "total": 2, "rate": 0.5},
        },
    )
    report = report_cases(
        [
            {
                "task_id": "file-task",
                "condition": "benign",
                "versions": [initial],
                "evaluations": evaluations,
            }
        ],
        task_denominator=85,
        conditions=("benign",),
    )
    arm = report["arms"][0]
    assert arm["measured_count"] == 1 and arm["not_measured_count"] == 84
    assert arm["measured_asr"] is None and arm["asr_measured_count"] == 0
    assert report["versions"][0]["metrics"]["reward"] == 0.5
    assert report["versions"][0]["completion_steps"]["rate"] is None


def test_authentication_failure_does_not_evaluate_later_versions(tmp_path):
    from tau_skill_evolution.journal import Journal
    from tau_skill_evolution.model import ModelClientError

    initial = SkillBundle({"SKILL.md": "initial"})
    final = SkillBundle({"SKILL.md": "final"}, parent_hash=initial.bundle_hash)
    calls = []

    def evaluation(bundle):
        calls.append(bundle.bundle_hash)
        raise ModelClientError("http_error", "redacted", status=401)

    journal = Journal(tmp_path)
    measurements = evaluate_versions([initial, final], evaluation, journal=journal)
    assert calls == [initial.bundle_hash]
    assert measurements[initial.bundle_hash]["status"] == "NOT_MEASURED"
    assert journal.authentication_failure() == 401
