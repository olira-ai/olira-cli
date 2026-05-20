#!/usr/bin/env bash
# Run `uv` for this package without inheriting Olira-wide CodeArtifact index settings.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec env -u UV_INDEX_URL -u UV_EXTRA_INDEX_URL -u PIP_INDEX_URL -u PIP_EXTRA_INDEX_URL uv "$@"
