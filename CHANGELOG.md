# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-05-12

### Changed

- Aligned nomenclature with Console

## [0.4.0] - 2026-05-11

### Added

- **`olira validate`** (`validate.py`): Local JSONL validation before uploading. Checks JSON syntax, record types, required fields, known event types (full `OliraLogType` catalog), PII in `patient_id` (email, phone, SSN), and patient-before-log ordering. `--check-org` cross-checks patient IDs against live org patients via the API. `--skip-order-check` bypasses the ordering warning.
- **`olira ingest`** command group (`ingest.py`): Full historical data ingestion workflow from the CLI:
  - `upload <file>` — presigned S3 URL → upload → create job; `--no-confirm`, `--summary-types`, `--idempotency-key`, `--watch`
  - `list` — paginated job table with `--page` / `--page-size`
  - `status <job_id>` — job detail with event type breakdown; `--watch` to tail
  - `confirm <job_id>` — confirm at `AWAITING_CONFIRMATION`; optional `--summary-types` patch + `--watch`
  - `cancel <job_id>` — cancel with interactive prompt; `--yes` to skip
- **`sdk:historical-ingest` scope** added to `VALID_SCOPES` in `api.py` — appears in the interactive key creation picker and `--scopes` help text.
- **`CLI_DOCUMENTATION.md`** updated with full reference for `validate`, `ingest`, and the new scope.
- **E2E test** (`scripts/e2e/cli_ingest_e2e.py`): 11-section subprocess-based test covering the full ingestion CLI workflow; config example at `scripts/e2e/cli_ingest.config.example.json`.
- **`.gitignore`**: `scripts/e2e/cli_ingest.config.json` ignored so API keys are never committed.

## [0.3.5] - 2026-05-01

### Changed

- **`sdk:state-read` scope description**: wording aligned with logs/events terminology (summaries, logs, events, memories).

## [0.3.4] - 2026-04-29

### Added

- New API Scope `sdk:state-read`. Docs updated

## [0.3.3] - 2026-03-19

### Changed

- **`CLI_DOCUMENTATION.md`**: Updated end-user reference documentation to reflect current command behaviour, flags, and workflows.

## [0.3.2] - 2026-03-09

### Added

- **`NO_ACCOUNT_HTML`** (`auth.py`): dedicated dark-mode error page shown in the browser when a Google sign-in user has no Olira org record — matches Console dark theme (`#1a1a1a` background, `#242424` cards) and mirrors the "No account found" layout in `AuthGuard.tsx` with two action cards (create org / join team)

### Changed

- **`ERROR_HTML`** (`auth.py`): redesigned to use Console dark-mode palette (replacing alarming red gradient) — neutral dark background, amber warning icon, clean card layout
- **`/done` callback handler** (`auth.py`): now parses `error` and `error_description` query params forwarded from the fragment bridge; passes them through to the CLI result so `olira login` prints a clear error message (e.g. "no account linked to organisation") instead of the generic "no_token" fallback
- **`CLI_DOCUMENTATION.md`**, **`README.md`**: updated `olira login` section to document Google (single-step) and email/password+TOTP MFA as the two supported sign-in methods

## [0.3.1] - 2026-03-06

### Changed

- Updated all GitHub references from `raiahealth` to `olira-ai` org across docs, Homebrew formula, install script, and `pyproject.toml` URLs.

### Added

- `CLI_DOCUMENTATION.md` — end-user reference covering all commands, flags, scopes, credentials file, and common workflows.

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
