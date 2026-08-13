---
name: olira-setup
description: Authenticate, manage API keys, and configure MCP client access (Cursor, Claude Code, Codex) with the Olira CLI.
---

# Olira CLI — Auth & Setup

Installed as `olira` (verify with `olira --version`; this doc matches v{{VERSION}}).

## Two credential classes — not interchangeable

- **API key** (`OLIRA_API_KEY=olira_...`) — required by `olira ingest *`, `olira validate --check-org`, and every read-only query command (`patients`/`state`/`cohorts`/`projects`/`integrations`). A browser login is rejected for these.
- **Browser login** (`olira login`) — required by `olira keys *` and `olira configure cursor`. An API key is rejected for these. Never run `olira login` yourself; it opens a real browser and refuses to run headlessly. Ask the human to run it, or to hand you an API key instead.

## Scopes

Grant only what a key needs — least privilege, one scope per capability:

| Scope | Grants |
|---|---|
| `sdk:historical-ingest` | Upload/manage bulk historical ingestion jobs (`olira ingest *`) |
| `api:manage-patients` | Create, read, update, soft-delete patients; also needed to query them |
| `sdk:event-log` | Log events and upload passive signal Parquet (`send_signals`) |
| `sdk:state-read` | Read patient state, summaries, event logs (`olira state *`) |
| `sdk:patient-token` | Mint short-lived patient-scoped JWTs |
| `sdk:integrations` | Manage/query EHR integrations — catalog, connect/disconnect, sync status (control-plane only) |
| `sdk:integration-write` | Honor `write_back` on logged events for EHR write-back |
| `sdk:actions` | Manage outbound-action destinations and their signing secrets; read/redeliver delivery history (see `olira-actions`) |
| `api:manage-projects` | Manage/query projects (org-wide keys only) |
| `mcp:patient-state` | Query patient state via the MCP server (used by `configure claude`/`configure codex`, not by the CLI's own commands) |

## Key management (needs browser login)

```bash
olira keys create --name "my-agent" --scopes sdk:historical-ingest api:manage-patients
olira keys list --json
olira keys revoke <name-or-id> --yes
```

## MCP client configuration

Two independent things, don't confuse them:

- **`olira init agent`** writes the skills you're reading now (`olira-ingest`/`olira-query`/`olira-setup`/`olira-actions`) plus `AGENTS.md` — teaches an agent to drive the CLI's commands and use the outbound-actions SDK.
- **`olira configure cursor` / `configure claude` / `configure codex`** connect that client's *own* MCP tool access to Olira's MCP server (for querying patient state as a tool, not by shelling out to the CLI). `configure cursor` needs a browser login and embeds the current token; `configure claude`/`configure codex` need no auth to run and never write a secret to disk — both reference an env var (`OLIRA_API_KEY` by default, override with `--api-key-env`) that must be exported wherever that client actually runs, scoped to `mcp:patient-state`.

## Golden rules for this workflow

- Never run `olira login` yourself — it opens a real browser and will refuse to run headlessly (exit 6). If `OLIRA_API_KEY` isn't set, ask the human to create one with `olira keys create`, or to log in themselves first if you need `keys *`/`configure cursor` (browser-login-only commands).
- `keys create`/`keys revoke` bypass their interactive prompts with `--name`/`--scopes` and `--yes` respectively — pass them up front rather than relying on a TTY.
