"""HTTP status -> exit code mapping, including the api.py revoke-traceback regression."""

from __future__ import annotations

import httpx

from tests.conftest import json_envelope


def _handler(status: int, body=None, json_body: bool = True):
    def _h(request: httpx.Request) -> httpx.Response:
        if json_body:
            return httpx.Response(status, json=body or {"detail": "boom"})
        return httpx.Response(status, text="not json")

    return _h


def test_401_maps_to_auth_error(run_cli, creds_file):
    creds_file()
    code, out, err = run_cli(["--json", "keys", "list"], handler=_handler(401))
    assert code == 3
    env = json_envelope(out)
    assert env["ok"] is False
    assert env["error"]["code"] == "AUTH_REQUIRED"
    assert env["error"]["http_status"] == 401


def test_404_maps_to_not_found(run_cli, creds_file, monkeypatch):
    creds_file()
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "ingest", "status", "job-123"], handler=_handler(404))
    assert code == 4
    env = json_envelope(out)
    assert env["error"]["code"] == "NOT_FOUND"


def test_500_maps_to_network_error(run_cli, creds_file, monkeypatch):
    creds_file()
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "ingest", "list"], handler=_handler(500))
    assert code == 7
    env = json_envelope(out)
    assert env["error"]["code"] == "SERVER_ERROR"


def test_revoke_never_tracebacks_on_http_error(run_cli, creds_file):
    """Regression: api.py's revoke used to leave the list-fetch outside any try/except."""
    creds_file()
    code, out, err = run_cli(["--json", "keys", "revoke", "some-key", "--yes"], handler=_handler(500))
    assert code == 7
    assert "Traceback" not in err
    assert "Traceback" not in out
    env = json_envelope(out)
    assert env["ok"] is False


def test_non_json_error_body_does_not_crash(run_cli, creds_file):
    """from_http_error guards response.json() — a non-JSON body must not itself raise."""
    creds_file()
    code, out, err = run_cli(["--json", "keys", "list"], handler=_handler(500, json_body=False))
    assert code == 7
    assert "Traceback" not in err
    json_envelope(out)


def test_json_flag_works_in_both_positions(run_cli, no_creds):
    code1, out1, _ = run_cli(["--json", "status"])
    code2, out2, _ = run_cli(["status", "--json"])
    assert code1 == code2 == 3
    env1 = json_envelope(out1)
    env2 = json_envelope(out2)
    assert env1["ok"] is env2["ok"] is False
