.DEFAULT_GOAL := all

.PHONY: .uv  # Check that uv is installed
.uv:
	@uv --version || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: .pre-commit  # Check that pre-commit is installed
.pre-commit:
	@pre-commit -V || echo 'Please install pre-commit: https://pre-commit.com/'

.PHONY: install  # Install the package, dependencies, and pre-commit for local development
install: .uv .pre-commit
	uv sync --frozen
	pre-commit install --install-hooks
	pre-commit install --hook-type pre-push

.PHONY: format  # Format and auto-fix the code
format:
	uv run ruff format
	uv run ruff check --fix

.PHONY: lint  # Check formatting and lint without modifying files
lint:
	uv run ruff check
	uv run ruff format --check --diff

.PHONY: typecheck  # Run static type checking
typecheck:
	uv run pyright

.PHONY: test  # Run the test suite
test:
	uv run pytest

.PHONY: testcov  # Run tests and generate an HTML coverage report
testcov:
	uv run pytest --cov-report=html

.PHONY: all  # Run format, lint, typecheck, and test
all: format lint typecheck test
