# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-02-28

### Added

- **Interactive scope picker for `olira keys create`** — When `--scopes` is not provided, an InquirerPy checkbox prompt is shown listing all six valid scopes. `mcp:patient-state` is pre-selected by default. Use arrow keys to navigate, space to toggle, and enter to confirm. Ctrl-C / Ctrl-D cancels cleanly. At least one scope must be selected before the key is created.
- **`--scopes` flag for `olira keys create`** — Non-interactive escape hatch for CI and scripting. Accepts one or more space-separated scope values (e.g. `--scopes mcp:patient-state api:manage-patients`). Invalid scope strings are rejected client-side with a clear error before hitting the API.
- **Scopes column in `olira keys list`** — The list table now includes a `SCOPES` column showing the granted scopes for each key. Keys without a stored scope field (pre-dating scope support) display `mcp:patient-state` as the default.

### Changed

- `olira keys create` now always sends a `scopes` field in the creation request body, replacing the previous behaviour of sending only `{"name": ...}` and relying on the server default.

## [0.2.0] - 2026-02-24

### Added

- **`--env local`** — New environment shorthand for fully local setups. Defaults to `http://localhost:8084` (MCP), `http://localhost:3000` (Console), and `http://localhost:8080/app-api` (API). Hidden from `--help` in production builds alongside all other internal flags.
- **Member profile fetch on login** — After token validation, `olira login` calls `GET /member/me` and `GET /organization/me` on app-api to resolve the user's display name and organisation. `olira status` now shows a human-readable name and organisation instead of the raw Auth0 `sub` claim.
- **`scripts/install-dev.sh`** — New script following the monorepo pattern. Installs via `uv sync --extra dev`; uses `CODE_ARTIFACT_TOKEN` if set, otherwise falls back to PyPI (olira-cli has no private dependencies).
- **`_INTERNAL_BUILD` flag** — `src/olira_cli/__init__.py` now exports `_INTERNAL_BUILD: bool = True`. The prod CI build flips this to `False` via a `sed` pre-build step, hiding `--env`, `--mcp-server`, `--console-url`, and `--port` from customer `--help` output.

### Changed

- **`olira login` default env** — In production builds (`_INTERNAL_BUILD = False`), `olira login` with no flags defaults to `prod`. Internal builds still require `--env` or explicit URLs.
- **`olira configure cursor`** — Resolves the `.cursor/` directory in order: current working directory (project-level), then `~/.cursor/` (global), then prompts for a path. Writes the current access token directly into `mcp.json`; no environment variable required. Prints a tip to use an API key for a non-expiring credential.
- **`olira logout`** — Now also removes the `olira-patient-state` entry from both the project-level `.cursor/mcp.json` and the global `~/.cursor/mcp.json`, in addition to deleting `~/.olira/credentials.json`.
- **Login success redirect** — After capturing the token the CLI callback server issues an HTTP 302 to `{console_url}/cli-login-done` instead of serving inline HTML, so users see a natively themed confirmation page in the Console.
- **Environment API URLs** — `_derive_api_url` corrected to `https://app-api.{env}.olira.ai/app-api` (was `https://api.{env}.olira.ai`).
- **`devcontainer.json`** — `postCreateCommand` delegates to `scripts/install-dev.sh` instead of inline shell.

### Fixed

- **`BrokenPipeError` noise** — The local callback HTTP server now uses `_QuietHTTPServer` which silently drops `BrokenPipeError` in `handle_error`. These errors were harmless (browser navigates away before the write completes) but cluttered stderr.

## [0.1.0] - 2026-02-24

### Added

- **`olira login`** — Browser-based authentication via Olira Console `/cli-login`. Requires `--env dev|stage|prod` or explicit `--mcp-server` and `--console-url`. Validates token against MCP and saves credentials to `~/.olira/credentials.json` with `chmod 600`.
- **`olira token`** — Prints the current access token to stdout for piping. Always outputs the token (even if expired); use `--quiet` to suppress expiry warning to stderr.
- **`olira status`** — Shows current identity, MCP server, and token expiry. Warns if credentials file has overly open permissions.
- **`olira logout`** — Removes `~/.olira/credentials.json`.
- **`olira keys create|list|revoke`** — Manage MCP API keys via app-api (org admin only). Create returns the raw key once; list shows name, created, last used, status; revoke prompts for confirmation.
- **`olira configure cursor`** — Writes `~/.cursor/mcp.json` with `${env:OLIRA_MCP_TOKEN}` and prints the shell-profile snippet for `export OLIRA_MCP_TOKEN=$(olira token)`.
