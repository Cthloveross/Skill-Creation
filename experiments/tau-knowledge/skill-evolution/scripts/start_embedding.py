#!/usr/bin/env python3
"""Start only the pinned Dense embedding service, in the foreground."""

import os

from tau_skill_evolution.retrieval import embedding_argv
from tau_skill_evolution.spec import load_spec

spec = load_spec()
command = embedding_argv(spec)
os.execvpe(
    command[0],
    command,
    {**os.environ, "CUDA_VISIBLE_DEVICES": spec.values["embedding"]["gpu_uuid"]},
)
