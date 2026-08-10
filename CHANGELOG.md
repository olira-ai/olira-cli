# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-08-10

Agent-first rework: every command is now safe to drive headlessly (no command
can hang on a prompt) and can emit machine-readable JSON. Existing human
usage is unaffected except where noted under Changed.

### Added

- `--json` on every command (root or subcommand position). One JSON envelope
  on stdout: `{"ok", "command", "cli_version", "data"|"error", "warnings"}`.
  `--watch` streams NDJSON progress/heartbeat events, ending in the envelope.
- `--api-key` flag (in addition to `OLIRA_API_KEY`) accepted by every
  SDK-backed command (`ingest *`, `validate --check-org`).
- `olira --version`.
- Typed exit codes: `2` usage, `3` auth, `4` not found, `5` validation, `6`
  wrong state / interactive input required, `7` network/server, `8` watch
  timeout, `130` interrupted. See CLI_DOCUMENTATION.md for the full table.
- `--yes` on `olira keys revoke` and `--dir` on `olira configure cursor` —
  every interactive prompt now has a non-interactive bypass.
- `--timeout` on all `--watch` commands; a heartbeat line/event every 60s
  during long polls; automatic retry with backoff on transient network/5xx
  errors mid-watch instead of aborting immediately.
- `--project` / `OLIRA_PROJECT` on `ingest *` and `validate --check-org`, so
  org-wide API keys can target a non-default project.
- `olira configure agents [--target all|agents-md|claude|cursor] [--dir]` —
  writes `AGENTS.md`, `.claude/skills/olira/SKILL.md`, and
  `.cursor/rules/olira.mdc` into a repo so coding agents can discover and use
  the CLI correctly (auth model, exit codes, ingestion state machine, JSONL
  schema, recipes, failure playbook). Idempotent; safe to re-run.
- Credential-class-aware auth resolution: `ingest`/`validate --check-org`
  require an API key and `keys`/`configure cursor` require a browser login;
  using the wrong one now fails fast with a specific remediation instead of
  an opaque 401 from the server.

### Changed

- **Ctrl-C during `--watch` now exits 130** (was 0) — scripts previously
  couldn't distinguish an interrupted watch from a completed job.
- **`olira ingest status` is now strictly read-only.** It no longer routes
  into the interactive confirmation prompt when a job is awaiting
  confirmation with missing template slots; it only reads and reports.
- **`olira ingest confirm` without `--init-templates`/`--no-backfill` in a
  non-interactive context now exits 6** (was 1), with `error.code:
  "CONFIRMATION_REQUIRED"`.
- `olira validate --check-org` and `olira ingest *` now require an API key
  (see credential-class-aware auth above) instead of silently sending a
  stored browser-login JWT that the server would reject.

### Fixed

- `olira keys revoke` no longer prints a raw Python traceback when the
  key-list lookup hits an HTTP error.
- Corrected the internal fallback API base URL used when `OLIRA_API_KEY` is
  set with no prior `olira login` (`https://api.prod.olira.ai` was wrong;
  now `https://app-api.prod.olira.ai/app-api`).
- `olira status`'s "Not logged in" message now goes to stderr (was stdout).
- `olira validate`'s colored output now honors `NO_COLOR` and non-TTY stdout.

## [1.1.1] - 2026-07-29

### Fixed

- Dead docs link (`olira.ai/api-docs`) replaced with `docs.olira.ai` in `pyproject.toml`'s
  `Documentation` URL, `README.md`, and `CLI_DOCUMENTATION.md` (OLI-2053).

## [1.1.0] - 2026-05-26

### Added

- Interactive prompt at `AWAITING_CONFIRMATION` when patients are missing view template slots: initialize templates, skip backfill, proceed anyway, or cancel.
- `--init-templates` on `olira ingest upload` and `olira ingest confirm` for non-interactive confirm with `initialize_missing_templates=true`.
- `olira ingest status` (and `--watch`) now shows "Cancellation requested…" when `cancel_requested` is true and the job is still actively processing, matching the Console badge.

### Changed

- `olira ingest status`, `upload --watch`, and `confirm` surface `missing_template_slot` entries under **Warnings** (separate from **Errors**) when printing job detail.

## [1.0.4] - 2026-05-21

### Added

- `.github/CODEOWNERS` — PRs now require approval from `@olira-ai/engineering`.

## [1.0.3] - 2026-05-20

### Fixed

- Remove `git push --delete origin $TAG` from release workflow to prevent tag deletion before GitHub Release creation.

### Added

- `workflow_dispatch` trigger on the release workflow for manual runs from the GitHub UI.

## [1.0.2] - 2026-05-20

### Changed

- Drop macOS x86_64 binary — arm64 binary runs natively on Apple Silicon and via Rosetta 2 on Intel Macs.

## [1.0.1] - 2026-05-20

### Fixed

- Add `pyinstaller` to `release` extras so the binary release workflow can build binaries.
- Bump GitHub Actions (`actions/checkout`, `actions/setup-python`, `astral-sh/setup-uv`, `actions/upload-artifact`, `actions/download-artifact`) to Node.js 24-compatible versions.

## [1.0.0] - 2026-05-20

### Added

- Initial public release of the Olira CLI for authentication, MCP configuration, API key management, JSONL validation, and historical data ingestion.
