import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution import retrieval, spec

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/start_embedding.py"


@pytest.mark.parametrize(
    ("arguments", "expected_config", "expected_gpu"),
    [
        ([], None, "configured-gpu"),
        (["--config", "skillsbench.yaml"], "skillsbench.yaml", "configured-gpu"),
        (["--config", "skillsbench.yaml", "--gpu", "2"], "skillsbench.yaml", "2"),
    ],
)
def test_embedding_start_uses_selected_config_and_gpu(
    monkeypatch, arguments, expected_config, expected_gpu
):
    selected, dispatched = [], []
    fixture = SimpleNamespace(values={"embedding": {"gpu_uuid": "configured-gpu"}})

    def load(*args):
        selected.append(args[0] if args else None)
        return fixture

    monkeypatch.setattr(spec, "load_spec", load)
    monkeypatch.setattr(
        retrieval, "embedding_argv", lambda value: ["pinned-vllm", "serve", "pinned-model"]
    )
    monkeypatch.setattr(
        os, "execvpe", lambda executable, argv, env: dispatched.append((executable, argv, env))
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *arguments])
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert selected == [expected_config]
    assert dispatched[0][0:2] == ("pinned-vllm", ["pinned-vllm", "serve", "pinned-model"])
    assert dispatched[0][2]["CUDA_VISIBLE_DEVICES"] == expected_gpu
