# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
