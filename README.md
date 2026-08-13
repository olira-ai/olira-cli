# Olira CLI

Command-line tool for authenticating with Olira, configuring MCP (Model Context Protocol) access for tools like Cursor, and managing historical data ingestion — usable by humans and coding agents alike.

Full command reference: [docs.olira.ai/cli](https://docs.olira.ai/cli)

> **Using Cursor, Claude Code, Codex, or another coding agent?** This CLI is
> built for that: every command is safe to run headlessly (nothing ever
> hangs on a prompt) and supports `--json` output. Run
> `olira init agent` once in your repo and your agent will know how to
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
| `olira init agent` | Write agent-facing docs into the current repo: `AGENTS.md` plus five focused skills (ingest, logging, query, setup, actions) for Claude Code and/or Cursor/Codex. |
| `olira keys create` | Create an API key (interactive wizard). Use `--name` and `--scopes` to skip prompts. |
| `olira keys list` | List API keys for your organization, including their scopes. |
| `olira keys revoke <name-or-id>` | Permanently revoke an API key. Use `--yes` to skip the confirmation prompt. |
| `olira validate <file>.jsonl` | Validate a historical-data file locally before uploading. |
| `olira ingest upload <file>.jsonl` | Upload a validated file and create an ingestion job. |
| `olira patients list` / `get <id>` | Query patients (read-only). |
| `olira state stable\|modules\|views\|logs\|events\|memories <patient_id>` | Query a patient's clinical state (read-only). |
| `olira cohorts list` / `get <id>` / `templates <id>` | Query cohorts (read-only). |
| `olira projects list` / `get <id_or_slug>` | Query projects (read-only; org-wide key). |
| `olira integrations catalog\|list\|get\|data-points` | Query EHR integrations (read-only). |
| `olira actions create-destination\|list-destinations\|get-destination\|update-destination\|delete-destination\|rotate-destination-secret` | Manage outbound-action webhook/email destinations. |
| `olira actions list-deliveries\|get-delivery\|redeliver-delivery` | Inspect and redeliver from the delivery ledger. |
| `olira log-types list` / `get <subtype>` | Query the platform's log-type catalog, including full payload schemas (read-only). |

Every command accepts `--json` for machine-readable output — see
[Using the CLI from a coding agent](#using-the-cli-from-a-coding-agent) and
the [full reference](https://docs.olira.ai/cli) for the JSON envelope and
exit-code contract.

## Using the CLI from a coding agent

There are two independent things you might want an agent to do, and two
commands for them:

**Teach your agent to drive this CLI**
(validate/upload historical data, manage keys, read job status, register
webhook/email destinations) — plus how to verify delivery signatures in its
own receiving server, which is SDK guidance, not a CLI operation — run once,
in the repo the agent works in:

```bash
olira init agent
```

This writes `AGENTS.md` plus **five focused skills** — `olira-ingest`
(bulk historical files), `olira-logging` (instrumenting your code to log
live events via the SDK), `olira-query`, `olira-setup`, `olira-actions`
(outbound-action destinations and deliveries) — as
`.claude/skills/<name>/SKILL.md` for Claude Code and
`.agents/skills/<name>/SKILL.md` for Cursor and Codex, which both discover
skills from that shared, vendor-neutral location (`--cursor` and `--codex`
write the identical files there — pass either). Split by workflow rather
than one monolith because the ingestion state machine is genuinely complex
and a "list patients" task shouldn't have to load it: each skill covers
only its own commands (auth, exit codes, and the JSON envelope — needed by
everything — live once in `AGENTS.md`, which most agents load
unconditionally). Safe to re-run; it updates in place rather than
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
| `sdk:event-log` | Log health events and upload passive signal Parquet (`send_signals`) via the Olira SDK; also gates `olira log-types` discovery |
| `sdk:patient-token` | Mint short-lived, patient-locked JWTs for SDK use |
| `api:manage-patients` | Create, read, update, and deactivate patient records via REST |
| `api:org-config` | Read and update organisation platform configuration via REST |
| `sdk:state-read` | Read patient state — stable data, event modules, summaries, logs, events, memories |
| `sdk:historical-ingest` | Upload and manage bulk historical data ingestion jobs via the Olira SDK |
| `sdk:integrations` | Manage EHR integrations — catalog, connect/disconnect, data-point subscriptions, sync status (control-plane only, no write-back) |
| `sdk:integration-write` | Honor the `write_back` flag on logged events for EHR write-back |
| `api:manage-projects` | Create, list, rename, and deprecate projects; requires an org-wide key |
| `sdk:actions` | Manage outbound-action destinations and their signing secrets; read/redeliver delivery history |

This list matches [docs.olira.ai/cli/scopes](https://docs.olira.ai/cli/scopes) — treat that page as canonical if the two ever disagree.

## Credentials

Credentials are stored in `~/.olira/credentials.json` with permissions `600`. The file contains your access token and identity — keep it secure.

Tokens expire after ~24 hours. Re-run `olira login` to refresh; if you still have an active browser session with the Console it completes in a few seconds without requiring you to sign in again.

API keys never expire and are not stored locally — they live in the platform and can be revoked with `olira keys revoke`.

Two credential types exist and are not interchangeable: `olira ingest *`,
`olira validate --check-org`, the read-only query commands (`patients`,
`state`, `cohorts`, `projects`, `integrations`, `log-types`), and
`olira actions *` all need an API key
(`OLIRA_API_KEY` or `--api-key`); `olira keys *` and `olira configure cursor`
need a browser login instead. `olira configure claude`/`olira configure
codex` need neither — they write a config that references an env var
without ever touching a real credential. See the [full
reference](https://docs.olira.ai/cli) for details.

## Examples

The [`examples/`](examples/) folder has runnable end-to-end scripts
(ingest a file, query a patient's clinical state, check EHR integration
health) and [`examples/using-olira-with-agents.md`](examples/using-olira-with-agents.md) —
a guide to setting up a coding agent (Cursor, Claude Code, Codex, or any
other) to drive this CLI on your behalf.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, validation, and internal build notes.
