import unittest

from r2sp.runtime import AppWorldRuntime, SyntheticRuntime


class RuntimeTests(unittest.TestCase):
    def test_synthetic_runtime_dispatches_and_evaluates(self):
        values = iter(["w", "c", "s"])
        runtime = SyntheticRuntime(
            {("notes", "add"): lambda args: {"saved": args["text"]}},
            evaluator=lambda status, answer, trace: {
                "task_success": len(trace) == 1,
                "score": 1.0,
            },
            id_factory=lambda: next(values),
        )
        identity = runtime.start()
        observation = runtime.execute("notes", "add", {"text": "safe"})
        finished = runtime.finish("completed", "done")

        self.assertEqual(identity.world_id, "synthetic-world-w")
        self.assertTrue(observation.ok)
        self.assertEqual(observation.result, {"saved": "safe"})
        self.assertTrue(finished.task_success)
        self.assertEqual(finished.score, 1.0)

    def test_synthetic_runtime_rejects_identifier_injection(self):
        runtime = SyntheticRuntime()
        runtime.start()
        observation = runtime.execute("notes;import os", "add", {})
        self.assertFalse(observation.ok)
        self.assertEqual(observation.error_code, "invalid_request")

    def test_appworld_gateway_is_lazy_narrow_and_normalized(self):
        created = []

        class FakeWorld:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.codes = []
                self.closed = False
                self.task = type(
                    "Task",
                    (),
                    {
                        "instruction": "Add a note",
                        "app_descriptions": {
                            "notes": "Manage notes",
                            "ApiDocs": "Helper",
                            "Supervisor": "Helper",
                        },
                        "supervisor": {"secret": "hidden"},
                        "api_docs": {"hidden": True},
                    },
                )()
                created.append(self)

            def execute(self, code):
                self.codes.append(code)
                if "complete_task" in code:
                    return "completed"
                return '{"items":[1]}'

            def evaluate(self):
                return {"task_goal_completion": 1.0}

            def close(self):
                self.closed = True

        runtime = AppWorldRuntime("task-1", world_factory=FakeWorld)
        runtime.start()
        blocked = runtime.execute("ApiDocs", "show_api_doc", {})
        invalid = runtime.execute("spotify.__class__", "search", {})
        result = runtime.execute("spotify", "search", {"query": "x'); raise Exception()"})
        finished = runtime.finish("completed", "answer")
        runtime.close()

        self.assertEqual(blocked.error_code, "forbidden_app")
        self.assertEqual(invalid.error_code, "invalid_request")
        self.assertTrue(result.ok)
        self.assertEqual(result.result, {"items": [1]})
        self.assertEqual(runtime.task_instruction, "Add a note")
        self.assertEqual(runtime.app_descriptions, {"notes": "Manage notes"})
        self.assertFalse(hasattr(runtime, "supervisor"))
        self.assertFalse(hasattr(runtime, "api_docs"))
        self.assertIn("apis.spotify.search(**_r2sp_args)", created[0].codes[-2])
        self.assertTrue(finished.task_success)
        self.assertTrue(created[0].closed)

    def test_appworld_identity_uses_native_reset_evidence_when_available(self):
        class NativeWorld:
            def __init__(self, **kwargs):
                self.task_id = kwargs["task_id"]
                self.experiment_name = kwargs["experiment_name"]
                self.output_directory = f"/tmp/{self.experiment_name}/{self.task_id}"
                self.models_from_db_home_path = f"data/tasks/{self.task_id}/dbs"
                self.models_to_db_home_path = f"memory/task_output/{self.task_id}"
                self.time_freezer_id = f"time-{self.experiment_name}"
                self.task = type(
                    "Task",
                    (),
                    {"instruction": "Task", "app_descriptions": {"notes": "Notes"}},
                )()

            def close(self):
                pass

        first = AppWorldRuntime(
            "task-1", experiment_name="episode-1", world_factory=NativeWorld
        ).start()
        second = AppWorldRuntime(
            "task-1", experiment_name="episode-2", world_factory=NativeWorld
        ).start()

        self.assertTrue(first.world_id.startswith("appworld-world-"))
        self.assertNotEqual(first.context_id, second.context_id)
        self.assertNotEqual(first.session_id, second.session_id)

    def test_appworld_native_identity_rejects_mismatched_task(self):
        class WrongWorld:
            def __init__(self, **kwargs):
                self.task_id = "other-task"
                self.experiment_name = kwargs["experiment_name"]
                self.output_directory = "/tmp/other"
                self.models_from_db_home_path = "source"
                self.models_to_db_home_path = "target"
                self.time_freezer_id = "time"
                self.closed = False

            def close(self):
                self.closed = True

        runtime = AppWorldRuntime("task-1", experiment_name="episode", world_factory=WrongWorld)
        with self.assertRaisesRegex(Exception, "different task_id"):
            runtime.start()
        self.assertIsNone(runtime.identity)

    def test_appworld_exception_does_not_leak_schema(self):
        class BrokenWorld:
            def __init__(self, **kwargs):
                pass

            def execute(self, code):
                raise ValueError("secret_schema(api_key: str) at /private/file.py")

            def close(self):
                pass

        runtime = AppWorldRuntime("task-1", world_factory=BrokenWorld)
        runtime.start()
        result = runtime.execute("spotify", "search", {})
        self.assertFalse(result.ok)
        self.assertNotIn("secret_schema", result.error_message)

    def test_appworld_execution_failed_prefix_is_not_a_success(self):
        class TimedOutWorld:
            def __init__(self, **kwargs):
                pass

            def execute(self, code):
                return "Execution failed. Traceback:\nExecution timed out after 100 seconds."

            def close(self):
                pass

        runtime = AppWorldRuntime("task-1", world_factory=TimedOutWorld)
        runtime.start()
        result = runtime.execute("spotify", "search", {})

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "runtime_error")

    def test_appworld_tracker_counts_are_preserved_as_fractional_tgc(self):
        class TrackerWorld:
            def __init__(self, **kwargs):
                self.task = type(
                    "Task",
                    (),
                    {"instruction": "Task", "app_descriptions": {}},
                )()

            def execute(self, code):
                return "completed"

            def evaluate(self):
                return type(
                    "Tracker",
                    (),
                    {
                        "success": False,
                        "pass_count": 3,
                        "num_tests": 5,
                        "pass_percentage": 60.0,
                    },
                )()

            def close(self):
                pass

        runtime = AppWorldRuntime("task-1", world_factory=TrackerWorld)
        runtime.start()
        finished = runtime.finish("completed", "")

        self.assertFalse(finished.task_success)
        self.assertEqual(finished.score, 0.6)

    def test_appworld_evaluator_or_result_shape_failure_is_fatal(self):
        class BrokenEvaluationWorld:
            def __init__(self, *, invalid_shape=False, **kwargs):
                del kwargs
                self.invalid_shape = invalid_shape

            def execute(self, code):
                del code
                return "completed"

            def evaluate(self):
                if self.invalid_shape:
                    return {"unrecognized": True}
                raise RuntimeError("evaluator infrastructure failure")

            def close(self):
                pass

        runtime = AppWorldRuntime(
            "task-error", world_factory=lambda **kwargs: BrokenEvaluationWorld()
        )
        runtime.start()
        with self.assertRaisesRegex(RuntimeError, "evaluator infrastructure failure"):
            runtime.finish("success", "")

        invalid = AppWorldRuntime(
            "task-shape",
            world_factory=lambda **kwargs: BrokenEvaluationWorld(invalid_shape=True),
        )
        invalid.start()
        with self.assertRaisesRegex(ValueError, "did not expose"):
            invalid.finish("success", "")

    def test_appworld_finish_passes_explicit_success_or_fail_status(self):
        class FinishWorld:
            def __init__(self, **kwargs):
                del kwargs
                self.codes = []

            def execute(self, code):
                self.codes.append(code)
                return "completed"

            def evaluate(self):
                return {"task_goal_completion": 0.0}

            def close(self):
                pass

        worlds = []

        def factory(**kwargs):
            world = FinishWorld(**kwargs)
            worlds.append(world)
            return world

        failed = AppWorldRuntime("task-fail", world_factory=factory)
        failed.start()
        fail_result = failed.finish("fail", "")
        completed = AppWorldRuntime("task-success", world_factory=factory)
        completed.start()
        success_result = completed.finish("success", "done")

        self.assertEqual(fail_result.status, "fail")
        self.assertIn('"status":"fail"', worlds[0].codes[-1])
        self.assertIn('"answer":null', worlds[0].codes[-1])
        self.assertEqual(success_result.status, "success")
        self.assertIn('"status":"success"', worlds[1].codes[-1])
        self.assertIn('"answer":"done"', worlds[1].codes[-1])

    def test_canary_is_local_deployment_only_and_never_reaches_appworld(self):
        calls = []

        class FakeWorld:
            def __init__(self, **kwargs):
                self.codes = []

            def execute(self, code):
                self.codes.append(code)
                return "ok"

            def close(self):
                pass

        worlds = []

        def factory(**kwargs):
            world = FakeWorld(**kwargs)
            worlds.append(world)
            return world

        authoring = AppWorldRuntime("a", world_factory=factory)
        authoring.start()
        denied = authoring.execute("canary", "emit", {"nonce": "n"})
        self.assertFalse(denied.ok)
        self.assertEqual(worlds[0].codes, [])

        deployment = AppWorldRuntime(
            "d",
            world_factory=factory,
            canary_handler=lambda args: calls.append(dict(args)) or {"recorded": True},
        )
        deployment.start()
        accepted = deployment.execute("canary", "emit", {"nonce": "n"})
        self.assertTrue(accepted.ok)
        self.assertEqual(calls, [{"nonce": "n"}])
        self.assertEqual(worlds[1].codes, [])

        synthetic = SyntheticRuntime(canary_handler=lambda args: {"recorded": args["nonce"] == "n"})
        synthetic.start()
        self.assertTrue(synthetic.execute("canary", "emit", {"nonce": "n"}).ok)

    def test_evaluator_canary_write_failure_is_fatal(self):
        class FakeWorld:
            def __init__(self, **kwargs):
                del kwargs
                self.codes = []

            def execute(self, code):
                self.codes.append(code)
                return "ok"

            def close(self):
                pass

        world = FakeWorld()

        def fail_write(arguments):
            del arguments
            raise RuntimeError("evaluator canary disk failure")

        runtime = AppWorldRuntime(
            "task",
            world_factory=lambda **kwargs: world,
            canary_handler=fail_write,
        )
        runtime.start()
        with self.assertRaisesRegex(RuntimeError, "canary disk failure"):
            runtime.execute("canary", "emit", {"nonce": "n"})
        self.assertEqual(world.codes, [])


if __name__ == "__main__":
    unittest.main()
