#!/bin/bash

set -e

echo "Checking code formatting..."
uv run ruff format . --check --exclude scratch,docs,scripts

echo "Running Ruff linting..."
uv run ruff check . --exclude scratch,docs,scripts

echo "Running type checking..."
uv run mypy src/olira_cli/

echo "All linting checks passed"
