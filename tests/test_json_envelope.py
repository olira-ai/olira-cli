"""One JSON envelope on stdout per invocation; human mode is unaffected."""

from __future__ import annotations

import httpx

from tests.conftest import json_envelope


def _ok_handler(body: dict):
    def _h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return _h


def test_status_json_envelope_shape(run_cli, creds_file):
    creds_file(identity="alice@example.com", organization="Acme")
    code, out, err = run_cli(["status", "--json"])
    assert code == 0
    assert err == ""
    env = json_envelope(out)
    assert env["ok"] is True
    assert env["command"] == "status"
    assert "cli_version" in env
    assert env["data"]["identity"] == "alice@example.com"
    assert env["data"]["organization"] == "Acme"


def test_status_human_mode_prints_prose_not_json(run_cli, creds_file):
    creds_file(identity="alice@example.com", organization="Acme")
    code, out, _ = run_cli(["status"])
    assert code == 0
    assert "Logged in as alice@example.com (Acme)" in out
    assert "{" not in out


def test_keys_list_json_passthrough(run_cli, creds_file):
    creds_file()
    keys = [{"name": "k1", "scopes": ["sdk:event-log"], "is_active": True}]
    code, out, _ = run_cli(["--json", "keys", "list"], handler=_ok_handler({"data": keys}))
    assert code == 0
    env = json_envelope(out)
    assert env["data"]["keys"] == keys


def test_token_json_shape(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["token", "--json", "--quiet"])
    assert code == 0
    env = json_envelope(out)
    assert set(env["data"]) == {"access_token", "expires_at", "expired"}
    assert env["data"]["expired"] is False


def test_token_human_mode_prints_bare_token(run_cli, creds_file):
    creds = creds_file()
    code, out, _ = run_cli(["token", "--quiet"])
    assert code == 0
    assert out == creds["access_token"]
