#!/usr/bin/env python3
"""Start only the pinned Dense embedding service, in the foreground."""

import argparse
import os

from tau_skill_evolution.retrieval import embedding_argv
from tau_skill_evolution.spec import load_spec

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--config", help="Experiment configuration; defaults to the current τ config.")
parser.add_argument("--gpu", help="Local GPU UUID or index; defaults to the configured device.")
args = parser.parse_args()
spec = load_spec(args.config) if args.config else load_spec()
command = embedding_argv(spec)
os.execvpe(
    command[0],
    command,
    {**os.environ, "CUDA_VISIBLE_DEVICES": args.gpu or spec.values["embedding"]["gpu_uuid"]},
)
