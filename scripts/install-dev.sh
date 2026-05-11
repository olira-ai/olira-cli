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

# Install all dependencies including dev extras.
# NOTE: `uv lock` is intentionally not run here. Use `uv sync --frozen` so installs
# match the committed uv.lock without pulling transitive upgrades that can break CI,
# devcontainers, or local builds. Run `uv lock` manually when intentionally updating
# dependencies.
echo "Installing dependencies using uv..."
uv sync --frozen --extra dev

echo "Setup complete! You can now start developing."
echo ""
echo "Available development commands:"
echo "   ./scripts/pre-pr.sh            - Run full pre-PR validation"
echo "   ./scripts/test.sh              - Run tests"
echo "   ./scripts/lint.sh              - Run linting"
echo "   ./scripts/check-version.sh     - Check version consistency"
