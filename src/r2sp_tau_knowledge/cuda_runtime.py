"""Attest actual CUDA initialization before starting an owned model service."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def cuda_environment(driver_versions: list[str]) -> dict[str, str]:
    """Use the dedicated image's supported compatibility path only for R570."""
    if not driver_versions or len(set(driver_versions)) != 1:
        raise RuntimeError("allocated GPUs have inconsistent or missing driver versions")
    try:
        branch = int(driver_versions[0].split(".")[0])
    except ValueError as exc:
        raise RuntimeError("invalid NVIDIA driver version") from exc
    if branch == 570:
        return {
            "APPTAINERENV_VLLM_ENABLE_CUDA_COMPATIBILITY": "1",
            "APPTAINERENV_VLLM_CUDA_COMPATIBILITY_PATH": "/usr/local/cuda-13.0/compat",
            "APPTAINERENV_LD_LIBRARY_PATH": (
                "/usr/local/cuda-13.0/compat:/usr/local/cuda/lib64:/.singularity.d/libs"
            ),
        }
    return {}


def attest_cuda(
    *,
    apptainer: Path,
    image: Path,
    visible: str,
    environment: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    drivers = subprocess.run(
        [
            "nvidia-smi",
            "--id",
            visible,
            "--query-gpu=driver_version",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    versions = [line.strip() for line in drivers.stdout.splitlines() if line.strip()]
    count = len(visible.split(","))
    if len(versions) != count:
        raise RuntimeError("driver inventory does not match the GPU allocation")
    overrides = cuda_environment(versions)
    env = {
        **environment,
        **overrides,
        "CUDA_VISIBLE_DEVICES": visible,
        "APPTAINERENV_CUDA_VISIBLE_DEVICES": visible,
    }
    probe = (
        "import json,pathlib,torch; "
        "torch.cuda.init(); "
        "values=[float(torch.ones(1,device=f'cuda:{i}').sum().item()) "
        "for i in range(torch.cuda.device_count())]; "
        "print(json.dumps({'device_count':torch.cuda.device_count(),'values':values,"
        "'torch_version':torch.__version__,'cuda_version':torch.version.cuda,"
        "'loaded_libcuda':sorted({line.split()[-1] for line in "
        "pathlib.Path('/proc/self/maps').read_text().splitlines() "
        "if '/libcuda.so' in line})},sort_keys=True))"
    )
    completed = subprocess.run(
        [str(apptainer), "exec", "--cleanenv", "--nv", str(image), "python3", "-c", probe],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    report = json.loads(completed.stdout)
    if report.get("device_count") != count or report.get("values") != [1.0] * count:
        raise RuntimeError("allocated CUDA devices failed the tensor operation probe")
    if not report.get("loaded_libcuda"):
        raise RuntimeError("CUDA probe did not attest a loaded driver library")
    report.update(driver_versions=versions, compatibility_environment=overrides)
    return report, overrides
