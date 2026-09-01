.PHONY: setup test lint check clean

PYTHON ?= python
VENV ?= .venv

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -e '.[dev]'

test:
	$(VENV)/bin/python -m unittest discover -s tests -v

lint:
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/ruff format --check src tests

check: test lint
	$(VENV)/bin/python -m compileall -q src tests
	$(VENV)/bin/r2sp validate-config --config configs/experiment_plan.yaml

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -r {} +
	rm -rf .pytest_cache .ruff_cache build dist src/*.egg-info
