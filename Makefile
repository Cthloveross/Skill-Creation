.PHONY: setup test tau-official-test lint check clean

PYTHON ?= python
VENV ?= .venv
APPWORLD_TESTS := experiments/appworld/preliminary/tests
TAU_TESTS := experiments/tau-knowledge/preliminary/tests
TEST_PATHS := tests $(APPWORLD_TESTS) $(TAU_TESTS)
TAU_OFFICIAL_PYTHON := experiments/tau-knowledge/preliminary/data/upstream/tau2-bench/.venv/bin/python

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -e '.[dev]'

test:
	$(VENV)/bin/python -m pytest -q $(TEST_PATHS)
	$(MAKE) tau-official-test

tau-official-test:
	@if [ -x "$(TAU_OFFICIAL_PYTHON)" ]; then \
		PYTHONPATH="$(CURDIR)/src" "$(TAU_OFFICIAL_PYTHON)" -m unittest discover \
			-s "$(TAU_TESTS)" -p 'test_official_runtime.py' -v; \
	else \
		echo "SKIP tau official-runtime tests: run tau bootstrap first"; \
	fi

lint:
	$(VENV)/bin/ruff check src $(TEST_PATHS)
	$(VENV)/bin/ruff format --check src $(TEST_PATHS)

check: test lint
	$(VENV)/bin/python -m compileall -q src $(TEST_PATHS)
	$(VENV)/bin/r2sp validate-config --config experiments/appworld/preliminary/configs/experiment_plan.yaml

clean:
	find src $(TEST_PATHS) -type d -name __pycache__ -prune -exec rm -r {} +
	rm -rf .pytest_cache .ruff_cache build dist src/*.egg-info
