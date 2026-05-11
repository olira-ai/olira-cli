> **Maintained by:** Olira Engineering  
> **Published at:** `olira.ai/api-docs` → CLI tab  
> **Status:** **BETA** — CLI commands and flags may change between releases.

# Olira CLI

The Olira CLI is a lightweight developer tool for authenticating with the Olira
platform, managing API keys, configuring MCP access for AI clients, and uploading
historical patient data. It is the recommended way to create the API keys consumed
by the [Python SDK](https://olira.ai/api-docs), write your Bearer token into Cursor
so the [MCP Patient State server](https://olira.ai/api-docs) is available to your AI
agents, and manage bulk historical data ingestion jobs from the command line.

**Version:** `0.3.5`


## Related docs

| Doc | What it covers | Why you need it |
| --- | -------------- | --------------- |
| **MCP Patient State** (`olira.ai/api-docs` → MCP tab) | Tools for querying patient health state from AI agents | The MCP server is what your agent calls once the CLI has configured your credentials |
| **Python SDK** (`olira.ai/api-docs` → Python SDK tab) | `olira.log()`, `olira.get_patient_token()`, patient management, historical ingestion | Use keys created by the CLI to authenticate the SDK |


## Installation

```bash
pip install olira-cli
```

Or with `uv`:

```bash
uv add olira-cli
```

Verify:

```bash
olira --help
```


## Quick start

```bash
# 1. Log in via browser
olira login

# 2. Create an API key
olira keys create --name "my-integration" --scopes sdk:event-log api:manage-patients

# 3. Configure Cursor (writes ~/.cursor/mcp.json)
olira configure cursor
```

For historical data ingestion:

```bash
# Validate a file before uploading
olira validate patients_and_logs.jsonl

# Upload and monitor progress
olira ingest upload patients_and_logs.jsonl --watch
```


## Commands

### `olira login`

Log in via browser

**Internal-build flags** (hidden in production `--help`):

| Flag            | Description                               |
| --------------- | ----------------------------------------- |
| `--env`         | _(internal build only)_                   |
| `--mcp-server`  | _(internal build only)_                   |
| `--console-url` | _(internal build only)_                   |
| `--port`        | (default: `9876`) _(internal build only)_ |

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

| Flag       | Description                                                                                                                                                                                                    |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--name`   | Key name (skips the interactive prompt).                                                                                                                                                                       |
| `--scopes` | Scopes to grant (space-separated). Skips the interactive picker. Valid: `mcp:patient-state`, `mcp:integration`, `sdk:event-log`, `sdk:patient-token`, `api:manage-patients`, `api:org-config`, `sdk:state-read`, `sdk:historical-ingest`. |

### `olira keys list`

List API keys for your organization

### `olira keys revoke`

Permanently revoke an API key

| Flag  | Description              |
| ----- | ------------------------ |
| `key` | Key name or ID to revoke |

### `olira configure`

Write MCP client config

| Flag     | Description                                          |
| -------- | ---------------------------------------------------- |
| `client` | Target client (cursor; claude-code planned) `cursor` |

---

### `olira validate`

Validate a `.jsonl` file locally before uploading. Checks every record for
correct structure, known event types, PII in `patient_id`, and whether log
records reference patients that appear earlier in the file (or already exist in
your org when `--check-org` is passed). Exits `0` if clean, `1` if any errors
are found.

```bash
olira validate data.jsonl
olira validate data.jsonl --check-org          # cross-check patient IDs against live org
olira validate data.jsonl --skip-order-check   # skip the patient-before-log ordering check
```

| Flag                 | Description                                                                              |
| -------------------- | ---------------------------------------------------------------------------------------- |
| `file`               | Path to the `.jsonl` file to validate                                                    |
| `--check-org`        | Fetch your org's patients and warn if any log `patient_id` is not found _(requires login)_ |
| `--skip-order-check` | Skip the check that patients are declared before logs that reference them                |

**What is checked:**

| Check | Description |
| ----- | ----------- |
| JSON syntax | Every line must be valid JSON |
| Record type | `type` must be `"patient"` or `"log"` |
| Patient anchor rule | Patient records must have at least one of: `external_identifiers`, `email`, `phone_number`, `first_name`, `last_name`, or `date_of_birth` |
| Required log fields | Logs must have `event_type`, `patient_id`, and `timestamp` |
| Timestamp format | `timestamp` must be a valid ISO 8601 datetime (e.g. `2025-01-15T09:00:00Z`) |
| Event type | `event_type` must be a value from the Olira event type catalog |
| PII in patient\_id | `patient_id` must not look like an email, US phone number, or SSN |
| Patient ordering | Logs should reference patients declared earlier in the file (warning, not error) |

---

### `olira ingest`

Upload and manage historical data ingestion jobs. All subcommands require a
key with `sdk:historical-ingest` scope (or an active console session).

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
```

| Flag                | Description                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------- |
| `file`              | Path to the `.jsonl` file to upload                                                      |
| `--no-confirm`      | Skip the review stage and run the full pipeline automatically                            |
| `--no-backfill`     | Skip Stage 5 (AI view generation) after graph replay. Data is fully imported and queryable but Console views are not populated. |
| `--summary-types`   | AI summary types to generate (space-separated, e.g. `emotional_state_snapshot`)         |
| `--idempotency-key` | Unique key for this upload. Resubmitting the same key while a job is active returns the existing job instead of creating a new one. Auto-generated if omitted. |
| `--watch`           | Tail progress after upload until the job reaches `AWAITING_CONFIRMATION` or a terminal status |

#### `olira ingest list`

List ingestion jobs for your org, newest first.

```bash
olira ingest list
olira ingest list --page 2
olira ingest list --page-size 20
```

| Flag          | Description                          |
| ------------- | ------------------------------------ |
| `--status`    | Filter by status (e.g. `failed`, `completed`, `completed_with_errors`, `awaiting_confirmation`) |
| `--page`      | Page number (default: `1`)           |
| `--page-size` | Jobs per page (default: `10`)        |

#### `olira ingest status`

Show the current status and detail for a single job.

```bash
olira ingest status <job_id>
olira ingest status <job_id> --watch
```

| Flag      | Description                                                              |
| --------- | ------------------------------------------------------------------------ |
| `job_id`  | The job ID returned by `ingest upload`                                   |
| `--watch` | Tail progress until the job reaches `AWAITING_CONFIRMATION` or terminal  |

#### `olira ingest confirm`

Confirm a job at `AWAITING_CONFIRMATION` to start Phase 2 (graph replay + AI backfill).

```bash
olira ingest confirm <job_id>
olira ingest confirm <job_id> --summary-types emotional_state_snapshot
olira ingest confirm <job_id> --watch
```

| Flag              | Description                                                  |
| ----------------- | ------------------------------------------------------------ |
| `job_id`          | The job ID to confirm                                        |
| `--summary-types` | Set AI summary types before confirming (space-separated)     |
| `--no-backfill`   | Skip Stage 5 (AI view generation) before confirming          |
| `--watch`         | Tail progress after confirming until the job reaches terminal |

#### `olira ingest cancel`

Cancel an ingestion job. Jobs in `AWAITING_CONFIRMATION` are cancelled immediately.
Jobs in `REPLAYING` or `BACKFILLING` are stopped cooperatively after the current
patient completes.

```bash
olira ingest cancel <job_id>
olira ingest cancel <job_id> --yes   # skip confirmation prompt
```

| Flag     | Description                         |
| -------- | ----------------------------------- |
| `job_id` | The job ID to cancel                |
| `--yes`  | Skip the interactive confirmation prompt |

#### `olira ingest retry-backfill`

Retry a failed view backfill on a `COMPLETED_WITH_ERRORS` job. Patient and log data
are fully intact — only view materialisation failed. Transitions the job back to
`BACKFILLING`.

```bash
olira ingest retry-backfill <job_id>
olira ingest retry-backfill <job_id> --watch
```

| Flag      | Description                                              |
| --------- | -------------------------------------------------------- |
| `job_id`  | The job ID to retry                                      |
| `--watch` | Tail progress until the backfill completes or fails      |


## Scopes

Scopes are granted at API key creation and cannot be changed afterwards.
Each scope grants access to one set of Olira endpoints.

| Scope                    | Description                                                                        |
| ------------------------ | ---------------------------------------------------------------------------------- |
| `mcp:patient-state`      | Query patient state via the MCP Patient State server                               |
| `mcp:integration`        | Olira Integration MCP (coming soon)                                                |
| `sdk:event-log`          | Log health events on behalf of patients via the Olira SDK                          |
| `sdk:patient-token`      | Mint short-lived, patient-locked JWTs for SDK use                                  |
| `api:manage-patients`    | Create, read, update, and deactivate patient records via REST                      |
| `api:org-config`         | Read and update organisation platform configuration via REST                       |
| `sdk:state-read`         | Read patient state — stable data, event modules, summaries, logs, events, memories |
| `sdk:historical-ingest`  | Upload and manage bulk historical data ingestion jobs                              |

Use `olira keys create --scopes mcp:patient-state sdk:event-log ...` to grant specific
scopes non-interactively, or omit `--scopes` to use the interactive picker.


## Credentials file

Login credentials are stored in `~/.olira/credentials.json`. The file contains:

| Field          | Description                               |
| -------------- | ----------------------------------------- |
| `access_token` | Short-lived Auth0 JWT used for API calls  |
| `api_server`   | Base URL for the Olira API                |
| `mcp_server`   | Base URL for the MCP Patient State server |
| `expires_at`   | ISO 8601 expiry time of the access token  |

The file is created on first login and updated on every subsequent login.
Tokens expire; re-run `olira login` to refresh.

> **Note:** `olira configure cursor` writes your current token directly into
> `.cursor/mcp.json`. When the token expires, re-run `olira configure cursor`
> or replace the token with a long-lived API key.


## Exit codes

| Code | Meaning                                                                     |
| ---- | --------------------------------------------------------------------------- |
| `0`  | Success                                                                     |
| `1`  | Error (authentication failure, API error, validation error, user cancelled) |


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
curl -H "Authorization: Bearer $TOKEN" https://api.prod.olira.ai/member/me
```

### Upload historical data with review

```bash
# 1. Create a key with the ingestion scope
olira keys create --name "ingestion" --scopes sdk:historical-ingest

# 2. Validate your file locally first
olira validate patients_and_logs.jsonl

# 3. Upload — job pauses at AWAITING_CONFIRMATION
olira ingest upload patients_and_logs.jsonl --watch

# 4. Review the summary, then confirm to start AI processing
olira ingest confirm <job_id> --summary-types emotional_state_snapshot --watch
```

### Upload without a review step

```bash
olira ingest upload patients_and_logs.jsonl --no-confirm --watch
```

### Check job status and event type breakdown

```bash
olira ingest status <job_id>
```

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
