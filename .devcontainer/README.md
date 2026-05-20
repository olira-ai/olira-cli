# Olira CLI devcontainer

Standalone Python development environment for the Olira CLI package.

## Setup

Open this folder in VS Code or Cursor and choose **Reopen in Container**. The post-create command runs:

```bash
bash scripts/uv.sh sync --frozen --extra dev
```

Dependencies come from PyPI only (`[tool.uv] index-url` in `pyproject.toml`).

## Commands

From the integrated terminal:

```bash
bash scripts/pre-pr.sh
bash scripts/uv.sh run olira --help
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for full development notes, including internal `--env` flags available in source builds.
