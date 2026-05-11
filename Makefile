.PHONY: test build clean install

# Default Python interpreter; override with `make PYTHON=python3.13 test`.
PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

install:
	$(PIP) install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -q

build:
	$(PYTHON) -m build

clean:
	rm -rf claude_workflow.egg-info src/claude_workflow.egg-info
	rm -rf build/ dist/
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
