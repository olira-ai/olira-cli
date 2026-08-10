"""Watch loop: NDJSON events, --timeout, transient-error retry, terminal states, Ctrl-C."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import json_envelope, ndjson_events


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    """The watch loop sleeps 5-30s between polls and up to 8s on retry backoff — skip all of it."""
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def _sequence_handler(jobs: list[dict]):
    calls = {"n": 0}

    def _h(request: httpx.Request) -> httpx.Response:
        i = min(calls["n"], len(jobs) - 1)
        calls["n"] += 1
        return httpx.Response(200, json=jobs[i])

    return _h


def test_watch_completed_emits_progress_and_final_envelope(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    jobs = [
        {"job_id": "j1", "status": "replaying", "stage": "replay", "progress_pct": 10.0},
        {"job_id": "j1", "status": "replaying", "stage": "replay", "progress_pct": 60.0},
        {"job_id": "j1", "status": "completed", "stage": "done", "progress_pct": 100.0},
    ]
    code, out, _ = run_cli(["--json", "ingest", "status", "j1", "--watch"], handler=_sequence_handler(jobs))
    assert code == 0
    events = ndjson_events(out)
    assert any(e["event"] == "progress" for e in events)
    env = json_envelope(out)
    assert env["ok"] is True
    assert env["data"]["job"]["status"] == "completed"


def test_watch_failed_job_exits_6(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    jobs = [{"job_id": "j1", "status": "failed", "stage": "replay", "progress_pct": 40.0}]
    code, out, _ = run_cli(["--json", "ingest", "status", "j1", "--watch"], handler=_sequence_handler(jobs))
    assert code == 6
    env = json_envelope(out)
    assert env["error"]["code"] == "JOB_FAILED"
    assert env["error"]["details"]["job"]["status"] == "failed"


def test_watch_completed_with_errors_exits_0(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    jobs = [{"job_id": "j1", "status": "completed_with_errors", "stage": "done", "progress_pct": 100.0}]
    code, out, _ = run_cli(["--json", "ingest", "status", "j1", "--watch"], handler=_sequence_handler(jobs))
    assert code == 0
    env = json_envelope(out)
    assert env["data"]["job"]["status"] == "completed_with_errors"


def test_watch_timeout_exits_8(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    monkeypatch.setattr("time.monotonic", _monotonic_stepper())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"job_id": "j1", "status": "replaying", "stage": "x", "progress_pct": 1.0})

    code, out, _ = run_cli(["--json", "ingest", "status", "j1", "--watch", "--timeout", "1"], handler=handler)
    assert code == 8
    env = json_envelope(out)
    assert env["error"]["code"] == "WATCH_TIMEOUT"


def _monotonic_stepper():
    state = {"t": 0.0}

    def _now():
        state["t"] += 10.0
        return state["t"]

    return _now


def test_watch_retries_transient_5xx_then_succeeds(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"detail": "transient"})
        return httpx.Response(200, json={"job_id": "j1", "status": "completed", "stage": "done", "progress_pct": 100.0})

    code, out, err = run_cli(["--json", "ingest", "status", "j1", "--watch"], handler=handler)
    assert code == 0
    assert calls["n"] >= 2


def test_watch_gives_up_after_repeated_5xx(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "down"})

    code, out, _ = run_cli(["--json", "ingest", "status", "j1", "--watch"], handler=handler)
    assert code == 7
    env = json_envelope(out)
    assert env["error"]["code"] == "SERVER_ERROR"


def test_watch_ctrl_c_exits_130(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise KeyboardInterrupt()

    code, out, _ = run_cli(["--json", "ingest", "status", "j1", "--watch"], handler=handler)
    assert code == 130
