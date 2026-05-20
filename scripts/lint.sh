#!/bin/bash

set -e

echo "Checking code formatting..."
bash scripts/uv.sh run ruff format . --check --exclude scratch,docs,scripts

echo "Running Ruff linting..."
bash scripts/uv.sh run ruff check . --exclude scratch,docs,scripts

echo "Running type checking..."
bash scripts/uv.sh run mypy src/olira_cli/

echo "All linting checks passed"
