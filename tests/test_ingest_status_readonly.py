"""ingest status must never mutate a job, even when awaiting confirmation with missing slots."""

from __future__ import annotations

import httpx

from tests.conftest import json_envelope

_AWAITING_JOB = {
    "job_id": "job-1",
    "status": "awaiting_confirmation",
    "stage": "review",
    "progress_pct": 100.0,
    "missing_template_slots": {"patient-1": ["clinical_note"]},
}


def test_status_only_sends_get_requests(run_cli, no_creds, monkeypatch, refuse_input):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET", f"status must never send {request.method}"
        return httpx.Response(200, json=_AWAITING_JOB)

    code, out, _ = run_cli(["--json", "ingest", "status", "job-1"], handler=handler)
    assert code == 0
    env = json_envelope(out)
    assert env["data"]["job"]["status"] == "awaiting_confirmation"


def test_status_never_prompts_even_with_tty(run_cli, no_creds, monkeypatch, refuse_input):
    """Regression: cmd_status used to route into the interactive confirm handler."""
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json=_AWAITING_JOB)

    code, out, _ = run_cli(["ingest", "status", "job-1"], handler=handler)
    assert code == 0
    assert "awaiting" in out.lower() or "confirmation" in out.lower()
