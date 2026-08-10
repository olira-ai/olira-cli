> **Maintained by:** Olira Engineering  
> **Published at:** [docs.olira.ai](https://docs.olira.ai) → CLI tab  
> **Version:** `1.2.0`

# Olira CLI

The Olira CLI is a lightweight developer tool for authenticating with the Olira
platform, managing API keys, configuring MCP access for AI clients, and uploading
historical patient data. It is the recommended way to create the API keys consumed
by the [Python SDK](https://docs.olira.ai), write your Bearer token into Cursor
so the [MCP Patient State server](https://docs.olira.ai) is available to your AI
agents, and manage bulk historical data ingestion jobs from the command line.

## Related docs

| Doc                                               | What it covers                                                                       | Why you need it                                                                      |
| ------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| **MCP Patient State** (`docs.olira.ai` → MCP tab) | Tools for querying patient health state from AI agents                               | The MCP server is what your agent calls once the CLI has configured your credentials |
| **Python SDK** (`docs.olira.ai` → Python SDK tab) | `olira.log()`, `olira.get_patient_token()`, patient management, historical ingestion | Use keys created by the CLI to authenticate the SDK                                  |

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

> **Note:** Run the CLI on your **host machine**, not inside a devcontainer or remote container. The login flow starts a local callback server (`localhost:9876`) that must be reachable by your browser.

## Quick start

```bash
# 1. Log in via browser (Google or email/password + TOTP MFA)
olira login

# 2. Create an API key
olira keys create --name "my-integration" --scopes sdk:event-log api:manage-patients

# 3. Configure Cursor (writes .cursor/mcp.json in the current directory, or ~/.cursor/)
olira configure cursor
```

For historical data ingestion:

```bash
# Validate a file before uploading
olira validate patients_and_logs.jsonl

# Upload and monitor progress
olira ingest upload patients_and_logs.jsonl --watch
```

## Non-interactive & agent use

Every command works headlessly — no command will hang waiting on a prompt.
This is also what powers `olira configure agents` (below).

- Pass **`--json`** (root or subcommand position, e.g. `olira --json ingest list` or `olira ingest list --json`) for a single JSON envelope on stdout: `{"ok": true|false, "command": "...", "cli_version": "...", "data": {...} | "error": {...}, "warnings": [...]}`. `--watch` additionally streams NDJSON `progress`/`heartbeat` events before the final envelope line.
- Auth for scripts/CI/agents: set **`OLIRA_API_KEY=olira_...`** (or pass `--api-key`) instead of `olira login`. See [Environment variables](#environment-variables) and [Credential types](#credential-types) below — `ingest`/`validate --check-org` need an API key; `keys`/`configure cursor` need a browser login and cannot use one.
- Every place that would otherwise prompt has a flag that answers it up front: `--yes` (`keys revoke`, `ingest cancel`), `--name`/`--scopes` (`keys create`), `--dir` (`configure cursor`), `--init-templates`/`--no-backfill` (`ingest confirm`). Without the flag and without a TTY, the command fails fast (exit `6`, `PROMPT_REQUIRED`) naming the flag to add — it never hangs.
- Pass **`--timeout SECONDS`** with `--watch` on long-running ingest commands; without it, watching a job that never reaches a terminal state polls forever.
- **`olira configure agents`** writes `AGENTS.md`, a Claude Code skill, and a Cursor rule into the current repo describing all of the above plus the ingestion state machine, JSONL schema, and a failure playbook — point a coding agent at a repo with these files and it can drive the CLI correctly without additional instructions.

### Environment variables

| Variable          | Used by                              | Purpose                                                                 |
| ------------------ | ------------------------------------- | ------------------------------------------------------------------------ |
| `OLIRA_API_KEY`    | `ingest *`, `validate --check-org`    | API key, in place of `--api-key` or an interactive login                |
| `OLIRA_API_URL`    | any command resolving credentials     | Override the app-api base URL (rarely needed; normally derived)         |
| `OLIRA_PROJECT`    | `ingest *`, `validate --check-org`    | Default `--project` when targeting a non-default project (org-wide keys)|
| `NO_COLOR`         | `validate`                            | Disable ANSI colors in human-mode output                                |

### Credential types

Two credential types exist and are **not** interchangeable:

| Command group                              | Needs                                   | Will NOT accept                     |
| ------------------------------------------- | ---------------------------------------- | ------------------------------------ |
| `olira ingest *`, `olira validate --check-org` | An API key (`OLIRA_API_KEY` / `--api-key`) | A browser-login session               |
| `olira keys *`, `olira configure cursor`    | A browser login (`olira login`)          | An API key                            |

Using the wrong one fails fast with a specific error (exit `3`) rather than
an opaque 401 from the server.

### JSON envelope

```json
{"ok": true, "command": "ingest.status", "cli_version": "1.2.0", "data": {"job_id": "...", "status": "replaying", "...": "..."}, "warnings": []}
```

```json
{"ok": false, "command": "keys.revoke", "cli_version": "1.2.0",
 "error": {"code": "PROMPT_REQUIRED", "message": "Revoking a key requires an interactive terminal.",
           "remediation": "Re-run with --yes.", "http_status": null, "details": {}}}
```

`data` mirrors the underlying API response — there is no separate JSON schema to learn beyond what's documented per command below.

## Commands

### `olira login`

Log in via browser. The Console sign-in page supports **Google** (single-step) and **email/password with TOTP MFA** — use whichever method matches your Olira account.

### `olira token`

Print access token to stdout for piping

| Flag      | Description                                |
| --------- | ------------------------------------------ |
| `--quiet` | Suppress expiry warning to stderr _(flag)_ |

### `olira status`

Show current login and token expiry

### `olira logout`

Remove stored credentials

### `olira keys`

Manage API keys (org admin only)

### `olira keys create`

Create a new API key

| Flag       | Description                                                                                                                                                                                                                               |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--name`   | Key name (skips the interactive prompt).                                                                                                                                                                                                  |
| `--scopes` | Scopes to grant (space-separated). Skips the interactive picker. Valid: `mcp:patient-state`, `sdk:event-log`, `sdk:patient-token`, `api:manage-patients`, `api:org-config`, `sdk:state-read`, `sdk:historical-ingest`, `sdk:integrations`, `sdk:integration-write`, `api:manage-projects`. |

### `olira keys list`

List API keys for your organization

### `olira keys revoke`

Permanently revoke an API key

| Flag    | Description                              |
| ------- | ----------------------------------------- |
| `key`   | Key name or ID to revoke                  |
| `--yes` | Skip the interactive confirmation prompt  |

### `olira configure cursor`

Write the MCP server entry into `mcp.json`. Prefers `.cursor/` in the current directory, falling back to `~/.cursor/`. Requires a browser login (`olira login`) — the current session token is embedded directly in `mcp.json`.

| Flag    | Description                                                                  |
| ------- | ----------------------------------------------------------------------------- |
| `--dir` | Path to the `.cursor` directory to write to (skips discovery and any prompt) |

### `olira configure claude` / `olira configure codex`

Write a project-scoped MCP server entry for Claude Code (`.mcp.json`) or
Codex CLI (`.codex/config.toml`). Unlike `configure cursor`, **neither
requires auth to run** and **neither ever writes a secret to disk** — both
of these config files are meant to be committed to git and shared with a
team, so the `Authorization` header (Claude) / `bearer_token_env_var`
(Codex) references an environment variable instead of a literal token. The
human still needs to export that variable with a real API key scoped to
`mcp:patient-state` before the MCP connection will authenticate.

```bash
olira configure claude                       # writes .mcp.json, referencing OLIRA_API_KEY
olira configure codex                        # writes .codex/config.toml, same pattern
olira configure claude --api-key-env MY_TOKEN # reference a different env var name
```

| Flag             | Description                                                                     |
| ---------------- | --------------------------------------------------------------------------------- |
| `--api-key-env`  | Env var name the client should read the bearer token from (default: `OLIRA_API_KEY`) |
| `--dir`          | Directory to write into (default: current directory)                             |

Both merge into the existing config file without disturbing other configured
MCP servers or unrelated settings, and are idempotent — re-running with the
same arguments reports `unchanged`.

### `olira configure agents`

Write agent-facing docs into the current repo — `AGENTS.md`, a Claude Code
skill (`.claude/skills/olira/SKILL.md`), and a Cursor rule
(`.cursor/rules/olira.mdc`) — covering auth, the JSON envelope and exit
codes, the ingestion state machine, the JSONL schema, copy-paste recipes,
and a failure playbook. Idempotent: re-running updates a managed block in
`AGENTS.md` and overwrites the other two files only if their content
changed; never prompts.

```bash
olira configure agents
olira configure agents --target claude
olira configure agents --dir ./my-integration
```

| Flag       | Description                                                                    |
| ---------- | -------------------------------------------------------------------------------- |
| `--target` | Which doc(s) to write: `all` (default), `agents-md`, `claude`, or `cursor`       |
| `--dir`    | Directory to write into (default: current directory)                            |

---

### `olira validate`

Validate a `.jsonl` file locally before uploading. Checks every record for
correct structure, known log types, PII in `patient_id`, and whether log
records reference patients that appear earlier in the file (or already exist in
your org when `--check-org` is passed). Exits `0` if clean, `5` if any errors
are found (structured under `error.details.errors` in `--json` mode).

```bash
olira validate data.jsonl
olira validate data.jsonl --check-org          # cross-check patient IDs against live org (needs an API key)
olira validate data.jsonl --skip-order-check   # skip the patient-before-log ordering check
olira validate data.jsonl --json               # machine-readable output
```

| Flag                 | Description                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------ |
| `file`               | Path to the `.jsonl` file to validate                                                            |
| `--check-org`        | Fetch your org's patients and warn if any log `patient_id` is not found _(requires an API key)_ |
| `--skip-order-check` | Skip the check that patients are declared before logs that reference them                        |
| `--project`          | Project id or slug to scope `--check-org` against (org-wide keys only; default: org's default project) |

**What is checked:**

| Check               | Description                                                                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| JSON syntax         | Every line must be valid JSON                                                                                                             |
| Record type         | `type` must be `"patient"` or `"log"`                                                                                                     |
| Patient anchor rule | Patient records must have at least one of: `external_identifiers`, `email`, `phone_number`, `first_name`, `last_name`, or `date_of_birth` |
| Required log fields | Logs must have `event_type`, `patient_id`, and `timestamp`                                                                                |
| Timestamp format    | `timestamp` must be a valid ISO 8601 datetime (e.g. `2025-01-15T09:00:00Z`)                                                               |
| Log type            | `event_type` must be a value from the Olira log type catalog                                                                              |
| PII in patient_id   | `patient_id` must not look like an email, US phone number, or SSN                                                                         |
| Patient ordering    | Logs should reference patients declared earlier in the file (warning, not error)                                                          |

---

### `olira ingest`

Upload and manage historical data ingestion jobs. All subcommands require an
API key with `sdk:historical-ingest` scope (`OLIRA_API_KEY` or `--api-key`) —
a browser login (`olira login`) does not work for these commands. All
subcommands also accept `--project` (or `OLIRA_PROJECT`) to target a
non-default project when using an org-wide key.

#### Missing view template slots

Some patients may not have view slots for every template configured on your org
(for example, if `recent_highlights` was added after the patient was first created).
When that happens, the job reaches `AWAITING_CONFIRMATION` with **Warnings** in the
job detail (code `missing_template_slot`), separate from hard **Errors**.

If warnings are present and your terminal is interactive, `upload --watch`,
`status`, and `confirm` offer a choice:

1. **Initialize missing templates and continue** (recommended) — confirms with
   `initialize_missing_templates=true` so the API creates the missing slots before Phase 2.
2. **Skip view generation** — sets `skip_backfill` and confirms (replay only; views later via `retry-backfill`).
3. **Proceed anyway** — confirms normally; backfill may fail for affected patients.
4. **Cancel job**

For scripts and CI, pass `--init-templates` on `upload` or `confirm` instead of the prompt.
Without a TTY, `confirm` prints hints and exits unless you pass `--init-templates` or `--no-backfill`.

#### `olira ingest upload`

Upload a `.jsonl` file to S3 and create an ingestion job. By default the job
pauses at the review stage (`AWAITING_CONFIRMATION`) so you can inspect patient
and log counts before triggering AI processing. Pass `--no-confirm` to run
straight through to completion.

```bash
olira ingest upload data.jsonl
olira ingest upload data.jsonl --no-confirm
olira ingest upload data.jsonl --watch
olira ingest upload data.jsonl --summary-types emotional_state_snapshot clinical_note
olira ingest upload data.jsonl --idempotency-key my-unique-key-2026
olira ingest upload data.jsonl --watch --init-templates
```

| Flag                | Description                                                                                                                                                                                        |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `file`              | Path to the `.jsonl` file to upload                                                                                                                                                                |
| `--no-confirm`      | Skip the review stage and run the full pipeline automatically                                                                                                                                      |
| `--no-backfill`     | Skip Stage 5 (AI view generation) after graph replay. Data is fully imported and queryable but Console views are not populated.                                                                    |
| `--summary-types`   | view types to generate (space-separated, e.g. `emotional_state_snapshot`)                                                                                                                          |
| `--idempotency-key` | Unique key for this upload. Resubmitting the same key while a job is active returns the existing job instead of creating a new one. Auto-generated if omitted.                                     |
| `--watch`           | Tail progress after upload until the job reaches `AWAITING_CONFIRMATION` or a terminal status. At `AWAITING_CONFIRMATION`, shows job detail and may prompt (interactive TTY only) if missing template slots are detected. |
| `--timeout`         | Give up watching after this many seconds (exit `8`); the job keeps running server-side                                                                                                             |
| `--init-templates`  | At `AWAITING_CONFIRMATION`, initialize missing view slots and confirm automatically (non-interactive; no prompt).                                                                                  |
| `--project`         | Project id or slug to upload into (org-wide keys only; default: org's default project)                                                                                                             |

#### `olira ingest list`

List ingestion jobs for your org, newest first.

```bash
olira ingest list
olira ingest list --page 2
olira ingest list --page-size 20
```

| Flag          | Description                                                                                     |
| ------------- | ----------------------------------------------------------------------------------------------- |
| `--status`    | Filter by status (e.g. `failed`, `completed`, `completed_with_errors`, `awaiting_confirmation`) |
| `--page`      | Page number (default: `1`)                                                                      |
| `--page-size` | Jobs per page (default: `10`)                                                                   |
| `--project`   | Project id or slug to scope the listing to                                                      |

#### `olira ingest status`

Show the current status and detail for a single job. Job detail lists **Warnings**
(`missing_template_slot`) separately from **Errors** when applicable.
**`status` is strictly read-only** — it never prompts and never mutates the
job, even when it is `AWAITING_CONFIRMATION`; it prints the confirm/cancel
hints and returns. Use `olira ingest confirm` to act on it.

```bash
olira ingest status <job_id>
olira ingest status <job_id> --watch --timeout 90
```

`--timeout` bounds how long this call blocks, not the job's expected
duration — ingestion jobs can legitimately run far longer than any
reasonable wait. On exit `8` (`WATCH_TIMEOUT`) the job is still running;
re-check with a plain `status` call later rather than watching again with a
bigger timeout.

| Flag        | Description                                                             |
| ----------- | ------------------------------------------------------------------------- |
| `job_id`    | The job ID returned by `ingest upload`                                    |
| `--watch`   | Tail progress until the job reaches `AWAITING_CONFIRMATION` or terminal   |
| `--timeout` | Give up watching after this many seconds (exit `8`)                       |
| `--project` | Project id or slug the job belongs to                                     |

#### `olira ingest confirm`

Confirm a job at `AWAITING_CONFIRMATION` to start Phase 2 (graph replay + view backfill).

```bash
olira ingest confirm <job_id>
olira ingest confirm <job_id> --summary-types emotional_state_snapshot
olira ingest confirm <job_id> --init-templates
olira ingest confirm <job_id> --no-backfill --watch
```

When missing template slot warnings are present and stdin is a TTY (and `--json`
is not set), `confirm` shows the interactive choices before calling the API.
Use `--init-templates` or `--no-backfill` to skip the prompt; without one of
these and without a TTY, `confirm` exits `6` (`CONFIRMATION_REQUIRED`) instead
of proceeding or hanging.

| Flag               | Description                                                                                                                              |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `job_id`           | The job ID to confirm                                                                                                                    |
| `--summary-types`  | Set view types before confirming (space-separated)                                                                                       |
| `--no-backfill`    | Skip Stage 5 (AI view generation) before confirming                                                                                      |
| `--init-templates` | Initialize missing view template slots on affected patients, then confirm (non-interactive). Requires app-api with missing-slot support. |
| `--watch`          | Tail progress after confirming until the job reaches terminal                                                                            |
| `--timeout`        | Give up watching after this many seconds (exit `8`)                                                                                       |
| `--project`        | Project id or slug the job belongs to                                                                                                     |

#### `olira ingest cancel`

Cancel an ingestion job. Jobs in `AWAITING_CONFIRMATION` are cancelled immediately.
Jobs in `REPLAYING` or `BACKFILLING` are stopped cooperatively after the current
patient completes.

```bash
olira ingest cancel <job_id>
olira ingest cancel <job_id> --yes   # skip confirmation prompt
```

| Flag        | Description                              |
| ----------- | ----------------------------------------- |
| `job_id`    | The job ID to cancel                     |
| `--yes`     | Skip the interactive confirmation prompt |
| `--project` | Project id or slug the job belongs to    |

#### `olira ingest retry-backfill`

Retry a failed view backfill on a `COMPLETED_WITH_ERRORS` job. Patient and log data
are fully intact — only view materialisation failed. Transitions the job back to
`BACKFILLING`.

```bash
olira ingest retry-backfill <job_id>
olira ingest retry-backfill <job_id> --watch
```

| Flag        | Description                                         |
| ----------- | ----------------------------------------------------- |
| `job_id`    | The job ID to retry                                 |
| `--watch`   | Tail progress until the backfill completes or fails |
| `--timeout` | Give up watching after this many seconds (exit `8`) |
| `--project` | Project id or slug the job belongs to               |

## Scopes

Scopes are granted at API key creation and cannot be changed afterwards.
Each scope grants access to one set of Olira endpoints.

| Scope                   | Description                                                                        |
| ----------------------- | ---------------------------------------------------------------------------------- |
| `mcp:patient-state`     | Query patient state via the MCP Patient State server                               |
| `sdk:event-log`         | Log health events and upload passive signal Parquet (`send_signals`) via the Olira SDK |
| `sdk:patient-token`     | Mint short-lived, patient-locked JWTs for SDK use                                  |
| `api:manage-patients`   | Create, read, update, and deactivate patient records via REST                      |
| `api:org-config`        | Read and update organisation platform configuration via REST                       |
| `sdk:state-read`        | Read patient state — stable data, event modules, summaries, logs, events, memories |
| `sdk:historical-ingest` | Upload and manage bulk historical data ingestion jobs                              |
| `sdk:integrations`      | Manage EHR integrations — catalog, connect/disconnect, data-point subscriptions, sync status (control-plane only, no write-back) |
| `sdk:integration-write` | Honor the `write_back` flag on logged events for EHR write-back                   |
| `api:manage-projects`   | Create, list, rename, and deprecate projects; requires an org-wide key            |

Use `olira keys create --scopes mcp:patient-state sdk:event-log ...` to grant specific
scopes non-interactively, or omit `--scopes` to use the interactive picker.

## Credentials file

Login credentials are stored in `~/.olira/credentials.json` with file permissions `600`. The file contains:

| Field          | Description                                  |
| -------------- | -------------------------------------------- |
| `access_token` | Short-lived JWT used for API calls           |
| `api_server`   | Base URL for the Olira API                   |
| `mcp_server`   | Base URL for the MCP Patient State server    |
| `identity`     | Display name or email for the logged-in user |
| `organization` | Organisation name                            |
| `expires_at`   | ISO 8601 expiry time of the access token     |

The file is created on first login and updated on every subsequent login.
Tokens expire after ~24 hours; re-run `olira login` to refresh. If you still have an active browser session with the Console, refresh completes in a few seconds without signing in again.

API keys never expire and are not stored locally — they live in the platform and can be revoked with `olira keys revoke`.

> **Note:** `olira configure cursor` writes your current token directly into
> `.cursor/mcp.json`. When the token expires, re-run `olira configure cursor`
> or replace the token with a long-lived API key.

## Exit codes

| Code  | Meaning                                                                                          |
| ----- | ------------------------------------------------------------------------------------------------- |
| `0`   | Success — including a job that finished `completed_with_errors`; check `data.status`              |
| `1`   | Unexpected/internal error                                                                         |
| `2`   | Usage error (bad flags/arguments)                                                                  |
| `3`   | Auth — not authenticated, expired, or the wrong credential type for this command (see [Credential types](#credential-types)) |
| `4`   | Not found — job, key, or local file does not exist                                                |
| `5`   | Validation failed (`validate`, or bad `keys create --scopes`)                                     |
| `6`   | Wrong state / interactive input required — `error.remediation` (or stderr, in human mode) names the exact flag to add |
| `7`   | Network or server error                                                                           |
| `8`   | `ingest ... --watch --timeout` exceeded; the job is still running server-side                     |
| `130` | Interrupted (Ctrl-C) — including during `--watch`, where the job keeps running server-side        |

In `--json` mode, every non-zero exit also has a matching `error.code` in the envelope (e.g. `AUTH_REQUIRED`, `NOT_FOUND`, `PROMPT_REQUIRED`, `CONFIRMATION_REQUIRED`, `WATCH_TIMEOUT`) — see [JSON envelope](#json-envelope).

## Common workflows

### Create an API key non-interactively

```bash
olira login
olira keys create --name "prod-backend" --scopes sdk:event-log api:manage-patients
```

### Rotate a key

```bash
# List keys to find the name
olira keys list

# Revoke the old key
olira keys revoke my-old-key

# Create a replacement
olira keys create --name "prod-backend-v2" --scopes sdk:event-log api:manage-patients
```

### Configure Cursor with a long-lived API key

```bash
# Create an API key with mcp:patient-state scope
olira keys create --name "Cursor" --scopes mcp:patient-state

# Edit ~/.cursor/mcp.json — replace the Bearer value with your API key
# "Authorization": "Bearer YOUR_API_KEY"
```

### Print your token for shell scripting

```bash
TOKEN=$(olira token --quiet)
curl -H "Authorization: Bearer $TOKEN" https://app-api.prod.olira.ai/app-api/member/me
```

### Upload historical data with review

```bash
# 1. Create a key with the ingestion scope
olira keys create --name "ingestion" --scopes sdk:historical-ingest

# 2. Validate your file locally first
olira validate patients_and_logs.jsonl

# 3. Upload — job pauses at AWAITING_CONFIRMATION
olira ingest upload patients_and_logs.jsonl --watch

# 4. Review the summary (Warnings vs Errors), then confirm to start AI processing
olira ingest confirm <job_id> --summary-types emotional_state_snapshot --watch

# If you see missing_template_slot warnings, either use the interactive prompt
# or confirm non-interactively:
olira ingest confirm <job_id> --init-templates --watch
```

### Upload without a review step

```bash
olira ingest upload patients_and_logs.jsonl --no-confirm --watch
```

### Check job status and log type breakdown

```bash
olira ingest status <job_id>
```

Warnings for missing view template slots appear under **Warnings**, not **Errors**.
Use `olira ingest confirm <job_id> --init-templates` to fix slots and proceed without
the interactive prompt.

### Cancel a job mid-flight

```bash
olira ingest cancel <job_id>
```

### Retry a failed view backfill

If a job finishes with `COMPLETED_WITH_ERRORS`, patient data is fully intact — only
view materialisation failed. Retry without re-ingesting any data:

```bash
olira ingest retry-backfill <job_id> --watch
```

### List all jobs and paginate

```bash
olira ingest list
olira ingest list --page 2 --page-size 20
```

### Drive the CLI from a coding agent

```bash
# One-time, in the target repo — gives the agent everything below for free
olira configure agents

# The agent then runs commands like:
export OLIRA_API_KEY=olira_prod_...
olira validate data.jsonl --json
# --timeout is a short bound on how long THIS call blocks, not a guess at
# the job's real duration — ingestion can legitimately run for hours. On
# exit 8 (WATCH_TIMEOUT), report progress and re-check with a later,
# non-watching `status` call rather than re-watching with a bigger number.
olira ingest upload data.jsonl --json --watch --timeout 90
olira ingest confirm <job_id> --init-templates --json --watch --timeout 90
```

See [Non-interactive & agent use](#non-interactive--agent-use) for the full
model (JSON envelope, exit codes, credential types, and every prompt's
bypass flag).
