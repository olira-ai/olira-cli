# Olira CLI

Command-line tool for authenticating with Olira and configuring MCP (Model Context Protocol) access for tools like Cursor.

## Installation

**macOS / Linux — Homebrew (recommended):**

```bash
brew install raia-health/tap/olira
```

**macOS / Linux — Shell script:**

```bash
curl -fsSL https://install.olira.ai | sh
```

**Manual** — download the binary for your platform from [GitHub Releases](https://github.com/raia-health/olira-platform/releases), make it executable, and move it to your `$PATH`:

```bash
chmod +x olira-macos-arm64
mv olira-macos-arm64 /usr/local/bin/olira
```

Verify:

```bash
olira --version
```

**Monorepo / development install** (host terminal, outside a devcontainer):

```bash
cd packages/olira-cli
bash scripts/install-dev.sh
source .venv/bin/activate
```

> **Note:** Run the CLI on your **host machine**, not inside a devcontainer. The login flow starts a local callback server (`localhost:9100`) that must be reachable by your browser. Inside a devcontainer the browser redirect cannot reach the container's localhost.

## Quick start

1. **Log in** — opens a browser to complete authentication:

   ```bash
   olira login --env prod
   ```

   For non-production environments:

   ```bash
   olira login --env dev
   olira login --env stage
   ```

   For a fully local setup (Console + MCP running locally):

   ```bash
   olira login --env local
   # defaults: Console http://localhost:3000, MCP http://localhost:8084
   ```

2. **Check status:**

   ```bash
   olira status
   ```

3. **Configure Cursor** to use the MCP server:

   ```bash
   olira configure cursor
   ```

   Run this from the **project root** — the command looks for a `.cursor/` directory in the current working directory first, then falls back to `~/.cursor/`, and prompts for a path if neither exists.

   Your current token is written directly into `mcp.json` — no environment variable needed. Re-run this command when your token expires (~24h). For a non-expiring credential, use an API key (see below).

4. **Log out** — removes all local credentials and cleans up `mcp.json`:

   ```bash
   olira logout
   ```

   This deletes `~/.olira/credentials.json` and removes the `olira-patient-state` entry from both the project-level `.cursor/mcp.json` (current directory) and the global `~/.cursor/mcp.json`.

5. **(Optional) Create an API key** for Cursor or automation (CI, scripts):

   ```bash
   olira keys create --name "Cursor"
   ```

   Copy the key when shown — it is not displayed again. Paste it directly into `mcp.json` as the Bearer token. API keys never expire and survive `olira logout`.

## Commands

| Command | Description |
|---------|-------------|
| `olira login --env <env>` | Log in via browser. `--env` is required (`dev`, `stage`, `prod`, `local`). |
| `olira token` | Print the stored access token to stdout. Use `--quiet` to suppress the expiry warning. |
| `olira status` | Show current identity, organization, MCP server, and token expiry. |
| `olira logout` | Remove `~/.olira/credentials.json` and wipe `olira-patient-state` from all `mcp.json` files. |
| `olira configure cursor` | Write the MCP server entry into `mcp.json`. Prefers `.cursor/` in the current directory. |
| `olira keys create --name "Label"` | Create an API key (org admin only). Shown once — copy immediately. |
| `olira keys list` | List API keys for your organization. |
| `olira keys revoke <name-or-id>` | Permanently revoke an API key. |

## Credentials

Credentials are stored in `~/.olira/credentials.json` with permissions `600`. The file contains your access token and identity — keep it secure.

Tokens expire after ~24 hours. Re-run `olira login` to refresh; if you still have an active browser session with the Console it completes in a few seconds.

API keys never expire and are not stored locally — they live in the platform and can be revoked with `olira keys revoke`.

## Environment URLs

| `--env` | Console | MCP Server | API |
|---------|---------|------------|-----|
| `local` | http://localhost:3000 | http://localhost:8084 | http://localhost:8080/app-api |
| `dev` | https://console.dev.olira.ai | https://mcp-patient-state.dev.olira.ai | https://app-api.dev.olira.ai/app-api |
| `stage` | https://console.stage.olira.ai | https://mcp-patient-state.stage.olira.ai | https://app-api.stage.olira.ai/app-api |
| `prod` | https://console.olira.ai | https://mcp-patient-state.olira.ai | https://app-api.prod.olira.ai/app-api |

## Publishing

See [PUBLISHING.md](PUBLISHING.md) for the full distribution guide — how `olira-cli` is published to CodeArtifact and PyPI, the metapackage setup, the `_INTERNAL_BUILD` flag, and release checklist.

## Development

From the package directory (`packages/olira-cli`):

```bash
bash scripts/install-dev.sh    # set up venv and install dependencies
bash scripts/lint.sh           # ruff format, ruff check, mypy
bash scripts/test.sh           # pytest with coverage
bash scripts/pre-pr.sh         # version check + lint + test
```

You can also open the package in VS Code (or the devcontainer) and use **Run Task** → `lint`, `test`, or `pre-pr`. Install pre-commit hooks with `pre-commit install` to run checks automatically before each commit.
