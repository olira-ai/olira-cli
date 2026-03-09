# Olira CLI Reference

The **Olira CLI** (`olira`) lets you authenticate with the Olira platform, manage API keys, and configure MCP access for tools like Cursor — all from the terminal without opening a browser.

---

## Installation

### macOS / Linux — Homebrew (recommended)

```bash
brew install olira-ai/tap/olira
```

### Shell script

```bash
curl -fsSL https://install.olira.ai | sh
```

### Manual

Download the binary for your platform from GitHub Releases, mark it executable, and move it to a directory on your `$PATH`:

```bash
chmod +x olira-macos-arm64
mv olira-macos-arm64 /usr/local/bin/olira
```

**Available binaries:** `olira-macos-arm64`, `olira-macos-x86_64`, `olira-linux-x86_64`.

Binaries are self-contained — no Python installation required.

> **Important:** Run the CLI on your host machine, not inside a devcontainer. The login callback server runs on `localhost:9876` and must be reachable by your browser.

### Verify

```bash
olira --version
```

---

## Quick start

```bash
# 1. Log in via browser
olira login

# 2. Confirm identity
olira status

# 3. Configure Cursor (run from your project root or any directory with .cursor/)
olira configure cursor

# 4. (Optional) Create a long-lived API key for non-expiring access
olira keys create --name "Cursor MCP"
```

---

## Commands

- [`olira login`](#olira-login)
- [`olira status`](#olira-status)
- [`olira token`](#olira-token)
- [`olira logout`](#olira-logout)
- [`olira keys create`](#olira-keys-create)
- [`olira keys list`](#olira-keys-list)
- [`olira keys revoke`](#olira-keys-revoke)
- [`olira configure cursor`](#olira-configure-cursor)

---

### `olira login`

Opens a browser window to authenticate with your Olira account. Starts a local callback server, waits for the OAuth2 redirect, and stores credentials at `~/.olira/credentials.json`.

```bash
olira login
```

The browser sign-in page supports two authentication methods:

- **Google** — click "Continue with Google" to sign in with your Google account. Google sign-in acts as a single step (no separate MFA prompt).
- **Email + password with MFA (TOTP)** — enter your email and password, then complete a 6-digit TOTP code from your authenticator app (Google Authenticator, Authy, or any TOTP-compatible app). MFA is required for all email/password accounts.

The session token is valid for approximately 24 hours. After it expires, run `olira login` again and then `olira configure cursor` to refresh the MCP token.

> **Prerequisites:** You need an Olira account before using the CLI. Sign up or log in at [console.olira.ai](https://console.olira.ai).

---

### `olira status`

Prints the currently logged-in identity, organisation, MCP server, and when the session expires. Returns exit code `1` if you are not logged in.

```bash
olira status
```

```
Logged in as Jane Doe (Acme Health)
MCP Server: https://mcp-patient-state.olira.ai
Token expires: 2026-03-07T10:00:00Z
```

Use this to confirm a login succeeded or to check whether your session is still valid.

---

### `olira token`

Prints the raw access token to stdout. Useful for scripting or piping into other tools.

```bash
olira token
```

```
FLAGS
  --quiet    Suppress the expiry warning that is printed to stderr
```

**Examples:**

```bash
# Print the token (prints an expiry warning to stderr if near expiry)
olira token

# Suppress the warning — clean output for piping
olira token --quiet

# Capture the token into a shell variable
TOKEN=$(olira token --quiet)
```

---

### `olira logout`

Deletes `~/.olira/credentials.json` and removes the `olira-patient-state` entry from both your project-level `.cursor/mcp.json` and the global `~/.cursor/mcp.json`.

```bash
olira logout
```

---

### `olira keys create`

Creates a new API key for your organisation. Runs interactively by default — prompts for a name and presents a scope selection menu. Pass `--name` and `--scopes` together to skip all prompts (useful for scripting).

```bash
olira keys create [--name <name>] [--scopes SCOPE [SCOPE ...]]
```

```
FLAGS
  --name <name>              Key name — skips the name prompt
  --scopes SCOPE [SCOPE ...]  One or more scopes — skips the scope picker
```

**Examples:**

```bash
# Fully interactive — prompts for name and scopes
olira keys create

# Provide a name; still prompts for scopes
olira keys create --name "Production Backend"

# Non-interactive — for scripts and CI
olira keys create --name "CI Pipeline" --scopes sdk:event-log api:manage-patients
```

The key is printed once and **not displayed again** — copy it immediately. Keys never expire but can be revoked at any time.

See [Scopes](#scopes) for the full list of available scopes.

---

### `olira keys list`

Lists all API keys for your organisation in a table with columns `NAME`, `CREATED`, `LAST USED`, `STATUS`, and `SCOPES`.

```bash
olira keys list
```

---

### `olira keys revoke`

Permanently revokes a key by name or ID. Prompts for confirmation before proceeding.

```bash
olira keys revoke <name-or-id>
```

**Examples:**

```bash
olira keys revoke "CI Pipeline"
olira keys revoke abc123id
```

Revocation is immediate and irreversible. Any service using the revoked key will begin receiving `401 Unauthorized` responses.

---

### `olira configure cursor`

Writes the MCP Patient State server entry into a `mcp.json` file so that Cursor can connect to it. Uses your current session token as the Bearer credential.

```bash
olira configure cursor
```

The command resolves the target `mcp.json` in this order:

1. `.cursor/mcp.json` in the current working directory (project-level)
2. `~/.cursor/mcp.json` (global)
3. Prompts you for a path if neither is found (press Enter to create `~/.cursor/mcp.json`)

Run this command from your project root to configure Cursor for that project only, or from any other directory to update the global config.

**What it writes:**

```json
{
  "mcpServers": {
    "olira-patient-state": {
      "url": "https://mcp-patient-state.olira.ai/mcp",
      "headers": {
        "Authorization": "Bearer <access_token>"
      }
    }
  }
}
```

> **Token expiry:** Session tokens last ~24 hours. After re-running `olira login`, run `olira configure cursor` again to refresh the token in `mcp.json`. For a non-expiring credential, create an API key with the `mcp:patient-state` scope and manually replace the Bearer value in `mcp.json` with it.

---

## Scopes

Scopes are assigned to API keys at creation time. Request only the scopes your key needs.

| Scope | What it grants |
|---|---|
| `mcp:patient-state` | Read patient state via the MCP Patient State server |
| `mcp:integration` | Olira Integration MCP *(coming soon)* |
| `sdk:event-log` | Log health events on behalf of patients via the Olira SDK |
| `sdk:patient-token` | Mint short-lived, patient-locked JWTs for SDK use |
| `api:manage-patients` | Create, read, update, and deactivate patient records via REST |
| `api:org-config` | Read and update organisation platform configuration via REST |

For a key that only needs to access patient state through Cursor or an AI tool, `mcp:patient-state` is sufficient.

---

## Credentials file

After a successful `olira login`, credentials are stored at `~/.olira/credentials.json` with permissions `0600` (owner read/write only). The file looks like this:

```json
{
  "access_token": "eyJ...",
  "mcp_server": "https://mcp-patient-state.olira.ai",
  "api_server": "https://app-api.prod.olira.ai/app-api",
  "console_url": "https://console.olira.ai",
  "env": "prod",
  "identity": "Jane Doe",
  "organization": "Acme Health",
  "expires_at": "2026-03-07T10:00:00Z"
}
```

The CLI warns on stderr if the file permissions are more permissive than `0600`. API keys are never stored locally — they live only in the Olira platform and are shown once at creation time.

`olira logout` deletes this file and cleans up MCP config entries.

---

## Exit codes

| Exit code | Meaning |
|---|---|
| `0` | Success |
| `1` | Error (message printed to stderr) |

All commands print errors to `stderr` and data output to `stdout`, so it is safe to pipe `olira token --quiet` or redirect output without capturing error messages.

---

## Common workflows

### Set up a new integration (first time)

```bash
# Install
brew install olira-ai/tap/olira

# Authenticate
olira login

# Configure Cursor from your project root
cd /path/to/my-project
olira configure cursor

# Create a durable API key for your backend service
olira keys create --name "My Backend" --scopes sdk:event-log api:manage-patients
# → Copy the printed key into your service as OLIRA_API_KEY
```

### Refresh after session expiry

```bash
olira login
olira configure cursor
```

### Create a non-expiring key for Cursor

```bash
olira keys create --name "Cursor MCP" --scopes mcp:patient-state
# Copy the key
# In .cursor/mcp.json, replace the Bearer value with the printed key
```

### Audit and rotate keys

```bash
# See all keys and their last-used timestamps
olira keys list

# Revoke a key that is no longer needed
olira keys revoke "Old Key"

# Create a replacement
olira keys create --name "New Key" --scopes sdk:event-log
```

### Non-interactive setup in CI

```bash
# Log in is not needed for API keys — they are created by an operator and passed as env vars.
# To verify credentials in a CI environment that already has a token:
olira status
```
