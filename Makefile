.PHONY: help install lint type test all

help:
	@echo "Targets: install, lint, type, test, all"

install:
	uv pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

type:
	mypy rst_to_md

test:
	pytest -q --cov=rst_to_md --cov-report=term-missing

all: lint type test
