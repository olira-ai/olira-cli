> **Maintained by:** Olira Engineering  
> **Published at:** `olira.ai/api-docs` → CLI tab

# Olira CLI

The Olira CLI is a lightweight developer tool for authenticating with the Olira
platform, managing API keys, and configuring MCP access for AI clients. It is
the recommended way to create the API keys consumed by the
[Python SDK](https://olira.ai/api-docs) and to write the Bearer token into your
Cursor config so the [MCP Patient State server](https://olira.ai/api-docs) is
available to your AI agents.

**Version:** `0.3.2`

---

## Related docs

| Doc | What it covers | Why you need it |
| --- | -------------- | --------------- |
| **MCP Patient State** (`olira.ai/api-docs` → MCP tab) | Tools for querying patient health state from AI agents | The MCP server is what your agent calls once the CLI has configured your credentials |
| **Python SDK** (`olira.ai/api-docs` → Python SDK tab) | `olira.log()`, `olira.get_patient_token()`, patient management | Use keys created by the CLI to authenticate the SDK; SDK mints Patient Tokens for MCP patient-facing agents |

---

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

---

## Quick start

```bash
# 1. Log in via browser
olira login

# 2. Create an API key
olira keys create --name "my-integration" --scopes sdk:event-log api:manage-patients

# 3. Configure Cursor (writes ~/.cursor/mcp.json)
olira configure cursor
```

---

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

| Flag       | Description                                                                                                                                                                              |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--name`   | Key name (skips the interactive prompt).                                                                                                                                                 |
| `--scopes` | Scopes to grant (space-separated). Skips the interactive picker. Valid: mcp:patient-state, mcp:integration, sdk:event-log, sdk:patient-token, api:manage-patients, api:org-config. `...` |

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

## Scopes

Scopes are granted at API key creation and cannot be changed afterwards.
Each scope grants access to one set of Olira endpoints. The table below shows
which product each scope unlocks — see the linked docs for what you can do once
you have the key.

| Scope                 | Description                                                   |
| --------------------- | ------------------------------------------------------------- |
| `mcp:patient-state`   | Query patient state via the MCP Patient State server          |
| `mcp:integration`     | Olira Integration MCP (coming soon)                           |
| `sdk:event-log`       | Log health events on behalf of patients via the Olira SDK     |
| `sdk:patient-token`   | Mint short-lived, patient-locked JWTs for SDK use             |
| `api:manage-patients` | Create, read, update, and deactivate patient records via REST |
| `api:org-config`      | Read and update organisation platform configuration via REST  |

Use `olira keys create --scopes mcp:patient-state mcp:integration ...` to grant specific scopes
non-interactively, or omit `--scopes` to use the interactive picker.

---

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

---

## Exit codes

| Code | Meaning                                                                     |
| ---- | --------------------------------------------------------------------------- |
| `0`  | Success                                                                     |
| `1`  | Error (authentication failure, API error, validation error, user cancelled) |

---

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
