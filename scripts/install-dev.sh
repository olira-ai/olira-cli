#!/bin/bash

# Installation script for olira-cli development

set -e

echo "Setting up olira-cli for development..."

# Check if uv is available, if not try to install it
if ! command -v uv &> /dev/null; then
    echo "uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    if ! command -v uv &> /dev/null; then
        echo "Failed to install uv. Please install it manually:"
        echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
fi

# olira-cli only depends on public PyPI packages (httpx etc.) — no CodeArtifact needed.
# If a CODE_ARTIFACT_TOKEN is already set in the environment (e.g. from a parent install
# script), we honour it; otherwise we fall back to plain PyPI.
if [ -n "$CODE_ARTIFACT_TOKEN" ]; then
    export UV_INDEX_URL="https://aws:${CODE_ARTIFACT_TOKEN}@raia-health-891612581662.d.codeartifact.us-east-1.amazonaws.com/pypi/olira-private-dev/simple/"
    echo "CodeArtifact token detected — using private index."
else
    export UV_INDEX_URL="https://pypi.org/simple"
    echo "No CodeArtifact token — using PyPI."
fi

# Install all dependencies including dev extras
echo "Installing dependencies using uv..."
uv sync --extra dev

echo "Setup complete! You can now start developing."
echo ""
echo "Available development commands:"
echo "   ./scripts/pre-pr.sh            - Run full pre-PR validation"
echo "   ./scripts/test.sh              - Run tests"
echo "   ./scripts/lint.sh              - Run linting"
echo "   ./scripts/check-version.sh     - Check version consistency"
