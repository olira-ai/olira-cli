# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
