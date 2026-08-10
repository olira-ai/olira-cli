"""Headless safety: every command that would prompt must instead fail fast (exit 6),
naming the bypass flag, and must never actually call input() or an InquirerPy prompt.
"""

from __future__ import annotations

import httpx

from tests.conftest import json_envelope


def _ok(body: dict):
    def _h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return _h


def test_keys_revoke_without_yes_requires_tty(run_cli, creds_file, no_tty, refuse_input):
    creds_file()
    keys = [{"name": "some-key", "id": "abc123"}]
    code, out, err = run_cli(["--json", "keys", "revoke", "some-key"], handler=_ok({"data": keys}))
    assert code == 6
    env = json_envelope(out)
    assert env["error"]["code"] == "PROMPT_REQUIRED"
    assert "--yes" in env["error"]["remediation"]


def test_keys_create_without_name_requires_tty(run_cli, creds_file, no_tty, refuse_input):
    creds_file()
    code, out, _ = run_cli(["--json", "keys", "create", "--scopes", "sdk:event-log"])
    assert code == 6
    env = json_envelope(out)
    assert env["error"]["code"] == "PROMPT_REQUIRED"
    assert "--name" in env["error"]["remediation"]


def test_keys_create_without_scopes_requires_tty(run_cli, creds_file, no_tty, refuse_input):
    creds_file()
    code, out, _ = run_cli(["--json", "keys", "create", "--name", "ci"])
    assert code == 6
    env = json_envelope(out)
    assert "--scopes" in env["error"]["remediation"]


def test_ingest_cancel_without_yes_requires_tty(run_cli, no_creds, no_tty, refuse_input, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "ingest", "cancel", "job-1"])
    assert code == 6
    env = json_envelope(out)
    assert env["error"]["code"] == "PROMPT_REQUIRED"
    assert "--yes" in env["error"]["remediation"]


def test_configure_cursor_without_dir_requires_tty(run_cli, creds_file, no_tty, refuse_input, tmp_path, monkeypatch):
    creds_file()
    monkeypatch.chdir(tmp_path)
    import pathlib

    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    code, out, _ = run_cli(["--json", "configure", "cursor"])
    assert code == 6
    env = json_envelope(out)
    assert "--dir" in env["error"]["remediation"]


def test_json_mode_blocks_prompt_even_with_tty(run_cli, creds_file, monkeypatch, refuse_input):
    """A TTY present but --json set must still refuse to prompt (require_tty checks json_mode too)."""
    creds_file()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    keys = [{"name": "some-key", "id": "abc123"}]
    code, out, _ = run_cli(["--json", "keys", "revoke", "some-key"], handler=_ok({"data": keys}))
    assert code == 6
