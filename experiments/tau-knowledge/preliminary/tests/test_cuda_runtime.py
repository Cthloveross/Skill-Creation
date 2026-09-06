import json
import subprocess
from pathlib import Path

import pytest

from r2sp_tau_knowledge.cuda_runtime import attest_cuda, cuda_environment


def test_r570_compatibility_is_set_before_the_python_process_starts():
    values = cuda_environment(["570.133.20", "570.133.20"])
    assert values["APPTAINERENV_LD_LIBRARY_PATH"].startswith("/usr/local/cuda-13.0/compat:")
    assert values["APPTAINERENV_VLLM_ENABLE_CUDA_COMPATIBILITY"] == "1"
    assert cuda_environment(["580.82.07"]) == {}
    assert cuda_environment(["590.10"]) == {}


@pytest.mark.parametrize("values", [[], ["570.1", "580.1"], ["unknown"]])
def test_inconsistent_driver_inventory_is_rejected(values):
    with pytest.raises(RuntimeError):
        cuda_environment(values)


def test_cuda_attestation_requires_a_real_tensor_operation_and_allocation_match(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == "nvidia-smi":
            return subprocess.CompletedProcess(command, 0, stdout="570.133.20\n")
        assert "torch.cuda.init()" in command[-1]
        assert "torch.ones" in command[-1]
        assert kwargs["env"]["APPTAINERENV_CUDA_VISIBLE_DEVICES"] == "GPU-allocated"
        assert kwargs["env"]["APPTAINERENV_LD_LIBRARY_PATH"].startswith(
            "/usr/local/cuda-13.0/compat:"
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {"device_count": 1, "values": [1.0], "loaded_libcuda": ["/libcuda.so.580.82.07"]}
            ),
        )

    monkeypatch.setattr(subprocess, "run", run)
    report, values = attest_cuda(
        apptainer=Path("/bin/apptainer"),
        image=Path("/image.sif"),
        visible="GPU-allocated",
        environment={"PATH": "/usr/bin:/bin"},
    )
    assert report["driver_versions"] == ["570.133.20"]
    assert values["APPTAINERENV_VLLM_ENABLE_CUDA_COMPATIBILITY"] == "1"
    assert len(calls) == 2
