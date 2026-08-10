# Olira CLI

Command-line tool for authenticating with Olira, configuring MCP (Model Context Protocol) access for tools like Cursor, and managing historical data ingestion — usable by humans and coding agents alike.

Full command reference: [docs.olira.ai/cli](https://docs.olira.ai/cli)

> **Using Cursor, Claude Code, Codex, or another coding agent?** This CLI is
> built for that: every command is safe to run headlessly (nothing ever
> hangs on a prompt) and supports `--json` output. Run
> `olira configure agents` once in your repo and your agent will know how to
> drive it correctly — see [Using the CLI from a coding
> agent](#using-the-cli-from-a-coding-agent) below.

## Installation

**macOS / Linux — Homebrew (recommended):**

```bash
brew install olira-ai/tap/olira
```

**macOS / Linux — Shell script:**

```bash
curl -fsSL https://install.olira.ai | sh
```

**Manual** — download the binary for your platform from [GitHub Releases](https://github.com/olira-ai/olira-cli/releases), make it executable, and move it to your `$PATH`:

```bash
chmod +x olira-macos-arm64
mv olira-macos-arm64 /usr/local/bin/olira
```

Verify:

```bash
olira --version
```

> **Note:** Run the CLI on your **host machine**, not inside a devcontainer. The login flow starts a local callback server (`localhost:9876`) that must be reachable by your browser.

## Quick start

**If a coding agent is running these commands**, skip this section — it's
the human, interactive flow (`olira login` opens a real browser and will
refuse to run headlessly). Go to [Using the CLI from a coding
agent](#using-the-cli-from-a-coding-agent) instead: an agent authenticates
with an API key via `OLIRA_API_KEY`, not by logging in.

1. **Log in** — opens a browser to complete authentication:

   ```bash
   olira login
   ```

   The browser sign-in page supports **Google** (single-step) and **email/password with TOTP MFA**. Use whichever method matches your Olira account.

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
   olira keys create
   ```

   Follow the prompts — you'll be asked for a key name and then presented with a scope picker. Copy the key when shown — it is not displayed again. Paste it directly into `mcp.json` as the Bearer token. API keys never expire and survive `olira logout`.

   You can also skip the prompts for scripting:

   ```bash
   olira keys create --name "CI Pipeline" --scopes api:manage-patients sdk:patient-token
   ```

## Commands

| Command | Description |
|---------|-------------|
| `olira login` | Log in via browser. |
| `olira token` | Print the stored access token to stdout. Use `--quiet` to suppress the expiry warning. |
| `olira status` | Show current identity, organization, MCP server, and token expiry. |
| `olira logout` | Remove `~/.olira/credentials.json` and wipe `olira-patient-state` from all `mcp.json` files. |
| `olira configure cursor` | Write the MCP server entry into `mcp.json` with your current login token. Prefers `.cursor/` in the current directory. |
| `olira configure claude` | Write a project-scoped MCP server entry into `.mcp.json` for Claude Code. No login needed — references an env var, never a literal token. |
| `olira configure codex` | Same, for Codex CLI (`.codex/config.toml`). |
| `olira configure agents` | Write agent-facing docs (`AGENTS.md`, a Claude Code skill, a Cursor rule) into the current repo. |
| `olira keys create` | Create an API key (interactive wizard). Use `--name` and `--scopes` to skip prompts. |
| `olira keys list` | List API keys for your organization, including their scopes. |
| `olira keys revoke <name-or-id>` | Permanently revoke an API key. Use `--yes` to skip the confirmation prompt. |
| `olira validate <file>.jsonl` | Validate a historical-data file locally before uploading. |
| `olira ingest upload <file>.jsonl` | Upload a validated file and create an ingestion job. |

Every command accepts `--json` for machine-readable output — see
[Using the CLI from a coding agent](#using-the-cli-from-a-coding-agent) and
the [full reference](https://docs.olira.ai/cli) for the JSON envelope and
exit-code contract.

## Using the CLI from a coding agent

There are two independent things you might want an agent to do, and two
commands for them:

**Teach your agent to drive this CLI** (validate/upload historical data,
manage keys, read job status) — run once, in the repo the agent works in:

```bash
olira configure agents
```

This writes `AGENTS.md`, `.claude/skills/olira/SKILL.md`, and
`.cursor/rules/olira.mdc` describing how to authenticate (`OLIRA_API_KEY`,
not `olira login`), the `--json` envelope and exit codes, the ingestion job
state machine, the JSONL schema, and a failure playbook — everything an
agent needs to drive `olira ingest`/`olira validate` correctly without
further instructions. Safe to re-run; it updates in place rather than
duplicating content.

**Connect your agent directly to the Olira MCP server** (so it can query
patient state as a tool, not by shelling out to the CLI):

```bash
olira configure cursor   # embeds your current login token into .cursor/mcp.json
olira configure claude    # writes .mcp.json for Claude Code
olira configure codex     # writes .codex/config.toml for Codex CLI
```

`configure claude`/`configure codex` need no login at all — just run them.
Both write a config that's safe to commit: instead of a literal token, the
`Authorization` header (or `bearer_token_env_var`, for Codex) references an
environment variable — `OLIRA_API_KEY` by default — that your agent's
environment must have set to an API key with `mcp:patient-state` scope.

## API key scopes

When creating an API key you will be prompted to select one or more scopes:

| Scope | Description |
|-------|-------------|
| `mcp:patient-state` | Query patient state via the MCP Patient State server |
| `sdk:event-log` | Log health events and upload passive signal Parquet (`send_signals`) via the Olira SDK |
| `sdk:patient-token` | Mint short-lived, patient-locked JWTs for SDK use |
| `api:manage-patients` | Create, read, update, and deactivate patient records via REST |
| `api:org-config` | Read and update organisation platform configuration via REST |
| `sdk:state-read` | Read patient state — stable data, event modules, summaries, logs, events, memories |
| `sdk:historical-ingest` | Upload and manage bulk historical data ingestion jobs via the Olira SDK |
| `sdk:integrations` | Manage EHR integrations — catalog, connect/disconnect, data-point subscriptions, sync status (control-plane only, no write-back) |
| `sdk:integration-write` | Honor the `write_back` flag on logged events for EHR write-back |
| `api:manage-projects` | Create, list, rename, and deprecate projects; requires an org-wide key |

This list matches [docs.olira.ai/cli/scopes](https://docs.olira.ai/cli/scopes) — treat that page as canonical if the two ever disagree.

## Credentials

Credentials are stored in `~/.olira/credentials.json` with permissions `600`. The file contains your access token and identity — keep it secure.

Tokens expire after ~24 hours. Re-run `olira login` to refresh; if you still have an active browser session with the Console it completes in a few seconds without requiring you to sign in again.

API keys never expire and are not stored locally — they live in the platform and can be revoked with `olira keys revoke`.

Two credential types exist and are not interchangeable: `olira ingest *` and
`olira validate --check-org` need an API key (`OLIRA_API_KEY` or `--api-key`);
`olira keys *` and `olira configure cursor` need a browser login instead.
`olira configure claude`/`olira configure codex` need neither — they write a
config that references an env var without ever touching a real credential.
See the [full reference](https://docs.olira.ai/cli) for details.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, validation, and internal build notes.
