.PHONY: setup skillsbench-prepare test lint check clean

PYTHON ?= python3
UV ?= uv
VENV ?= .venv
EXPERIMENT := experiments/tau-knowledge/skill-evolution

setup:
	UV_PROJECT_ENVIRONMENT=$(VENV) $(UV) sync --frozen --all-extras --python $(PYTHON)

skillsbench-prepare:
	GPU="$(or $(GPU),0)" PREP_JOBS="$(or $(PREP_JOBS),8)" bash $(EXPERIMENT)/runs/skillsbench/full-85-v8-handoff/operator.sh bootstrap

test:
	$(VENV)/bin/python -m pytest -q

lint:
	$(VENV)/bin/ruff check $(EXPERIMENT)/src $(EXPERIMENT)/tests $(EXPERIMENT)/scripts
	$(VENV)/bin/ruff format --check $(EXPERIMENT)/src $(EXPERIMENT)/tests $(EXPERIMENT)/scripts

check: test lint
	$(VENV)/bin/python -m compileall -q $(EXPERIMENT)/src $(EXPERIMENT)/tests $(EXPERIMENT)/scripts
	$(VENV)/bin/python -c 'from tau_skill_evolution.spec import DEFAULT_CONFIG, load_spec; load_spec(); load_spec(DEFAULT_CONFIG.parent / "skillsbench.yaml")'

clean:
	find $(EXPERIMENT)/src $(EXPERIMENT)/tests -type d -name __pycache__ -prune -exec rm -r {} +
	rm -rf .pytest_cache .ruff_cache build dist $(EXPERIMENT)/src/*.egg-info
