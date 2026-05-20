# Contributing to Olira CLI

## Development setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/olira-ai/olira-cli.git
cd olira-cli
bash scripts/uv.sh sync --frozen --extra dev
```

Run the CLI from source:

```bash
bash scripts/uv.sh run olira --help
```

Or activate the virtualenv:

```bash
source .venv/bin/activate
olira --help
```

> Run the CLI on your **host machine**, not inside a devcontainer. The login flow starts a local callback server (`localhost:9876`) that must be reachable by your browser.

## Validation

```bash
bash scripts/pre-pr.sh
```

Individual steps:

```bash
bash scripts/lint.sh
bash scripts/test.sh
bash scripts/check-version.sh
```

## Internal builds and `--env`

Source builds set `_INTERNAL_BUILD = True` in `src/olira_cli/__init__.py`, which exposes internal flags in `--help`:

- `--env dev|stage|prod|local` — target a non-production Olira environment
- `--mcp-server`, `--console-url`, `--port` — override URLs for local development

Release binaries (Homebrew, GitHub Releases) flip `_INTERNAL_BUILD` to `False` during CI so these flags are hidden from customer `--help` output.

| `--env` | Console | MCP Server | API |
|---------|---------|------------|-----|
| `local` | http://localhost:3000 | http://localhost:8084 | http://localhost:8080/app-api |
| `dev` | https://console.dev.olira.ai | https://mcp-patient-state.dev.olira.ai | https://app-api.dev.olira.ai/app-api |
| `stage` | https://console.stage.olira.ai | https://mcp-patient-state.stage.olira.ai | https://app-api.stage.olira.ai/app-api |
| `prod` | https://console.olira.ai | https://mcp-patient-state.olira.ai | https://app-api.prod.olira.ai/app-api |

Examples (source builds only):

```bash
olira login --env dev
olira login --env local
```

## Monorepo development

While the CLI lives in the Olira Platform monorepo, use the same commands from `packages/olira-cli/`. Internal publishing notes are archived at `docs/internal/olira-cli-publishing.md` in the monorepo.
