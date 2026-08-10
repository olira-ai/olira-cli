"""Shared fixtures for CLI tests.

Network calls are mocked via olira_cli.http._transport (httpx.MockTransport) —
no real HTTP, no respx dependency. The credentials file is redirected into a
tmp_path per test so tests never touch a developer's real ~/.olira.
"""

from __future__ import annotations

import json
import os
import sys

import httpx
import pytest

import olira_cli.credentials as credentials_module
import olira_cli.http as http_module
from olira_cli import cli, output

_VALID_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjk5OTk5OTk5OTl9.sig"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("OLIRA_API_KEY", "OLIRA_API_URL", "OLIRA_PROJECT", "NO_COLOR"):
        monkeypatch.delenv(var, raising=False)
    yield
    output.set_mode(False)


@pytest.fixture(autouse=True)
def reset_transport():
    yield
    http_module._transport = None


@pytest.fixture
def creds_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(credentials_module, "CREDENTIALS_FILE", path)
    monkeypatch.setattr(credentials_module, "CREDENTIALS_DIR", tmp_path)

    def _write(**overrides):
        base = {
            "access_token": _VALID_JWT,
            "api_server": "https://app-api.dev.olira.ai/app-api",
            "mcp_server": "https://mcp-patient-state.dev.olira.ai",
            "identity": "test@example.com",
            "organization": "Test Org",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        base.update(overrides)
        path.write_text(json.dumps(base))
        os.chmod(path, 0o600)
        return base

    return _write


@pytest.fixture
def no_creds(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setattr(credentials_module, "CREDENTIALS_FILE", path)
    monkeypatch.setattr(credentials_module, "CREDENTIALS_DIR", tmp_path)


@pytest.fixture
def no_tty(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)


@pytest.fixture
def refuse_input(monkeypatch):
    """Fail the test immediately if any code path calls input() — proves no prompt fired."""

    def _boom(*args, **kwargs):
        raise AssertionError("input() was called — a prompt fired when it should not have")

    monkeypatch.setattr("builtins.input", _boom)


@pytest.fixture
def run_cli(monkeypatch, capsys):
    def _run(argv: list[str], handler=None):
        if handler is not None:
            http_module._transport = httpx.MockTransport(handler)
        monkeypatch.setattr(sys, "argv", ["olira", *argv])
        code = cli.main()
        out, err = capsys.readouterr()
        return code, out, err

    return _run


def json_envelope(stdout: str) -> dict:
    """Parse the final line of stdout as the CLI's JSON envelope."""
    lines = [line for line in stdout.strip().splitlines() if line.strip()]
    assert lines, "expected at least one line of JSON output"
    return json.loads(lines[-1])


def ndjson_events(stdout: str) -> list[dict]:
    """Parse every line but the last as an NDJSON watch event."""
    lines = [line for line in stdout.strip().splitlines() if line.strip()]
    return [json.loads(line) for line in lines[:-1]]
