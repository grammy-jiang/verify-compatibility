.PHONY: install test lint format typecheck build check

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy

build:
	python -m build

check: lint typecheck test build
