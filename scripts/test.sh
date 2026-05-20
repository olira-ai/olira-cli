#!/bin/bash

set -e

echo "Running tests with coverage..."
bash scripts/uv.sh run pytest tests/ --tb=short --durations=10 --cov=src --cov-report=xml --cov-report=html

echo "All tests passed"
