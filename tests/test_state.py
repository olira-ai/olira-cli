"""olira state — read-only patient clinical state queries.

Covers: path construction for the get-vs-list branch (modules/views), query
param passthrough, sdk-credential-class enforcement, and 404 mapping.
"""

from __future__ import annotations

import httpx

from tests.conftest import json_envelope


def _capturing(body):
    seen: list[httpx.Request] = []

    def _h(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    return _h, seen


def test_state_requires_api_key_not_login(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "state", "logs", "p1"])
    assert code == 3
    assert json_envelope(out)["error"]["code"] == "AUTH_REQUIRED"


def test_stable_default_and_modules_filter(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patient_id": "p1", "modules": {}})
    run_cli(["--json", "state", "stable", "p1", "--modules", "a,b"], handler=handler)
    assert seen[0].url.path.endswith("/v1/state/p1/stable")
    assert seen[0].url.params.get("modules") == "a,b"


def test_modules_list_vs_get(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    handler, seen = _capturing({"patient_id": "p1", "modules": []})
    run_cli(["--json", "state", "modules", "p1"], handler=handler)
    assert seen[0].url.path.endswith("/v1/state/p1/event-modules")

    handler2, seen2 = _capturing({"patient_id": "p1", "module_type": "symptoms", "payload": {}})
    run_cli(["--json", "state", "modules", "p1", "symptoms"], handler=handler2)
    assert seen2[0].url.path.endswith("/v1/state/p1/event-modules/symptoms")


def test_views_list_vs_get(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    handler, seen = _capturing({"patient_id": "p1", "views": []})
    run_cli(["--json", "state", "views", "p1"], handler=handler)
    assert seen[0].url.path.endswith("/v1/state/p1/views")

    handler2, seen2 = _capturing({"patient_id": "p1", "view_type": "recent_highlights", "content": {}})
    run_cli(["--json", "state", "views", "p1", "recent_highlights"], handler=handler2)
    assert seen2[0].url.path.endswith("/v1/state/p1/views/recent_highlights")


def test_view_block(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patient_id": "p1", "block_id": "b1", "content": "x"})
    run_cli(["--json", "state", "view-block", "p1", "recent_highlights", "b1"], handler=handler)
    assert seen[0].url.path.endswith("/v1/state/p1/views/recent_highlights/blocks/b1")


def test_recent_limit_passthrough(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patient_id": "p1", "entries": [], "count": 0, "total_count": 0})
    run_cli(["--json", "state", "recent", "p1", "recent_highlights", "--limit", "10"], handler=handler)
    assert seen[0].url.path.endswith("/v1/state/p1/views/recent_highlights/recent")
    assert seen[0].url.params.get("limit") == "10"


def test_logs_query_params(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patient_id": "p1", "count": 0, "logs": []})
    run_cli(
        [
            "--json",
            "state",
            "logs",
            "p1",
            "--since",
            "2025-01-01T00:00:00Z",
            "--event-types",
            "symptom_report,vitals_measurement",
            "--limit",
            "5",
            "--offset",
            "10",
        ],
        handler=handler,
    )
    q = seen[0].url.params
    assert q.get("since") == "2025-01-01T00:00:00Z"
    assert q.get("event_types") == "symptom_report,vitals_measurement"
    assert q.get("limit") == "5"
    assert q.get("offset") == "10"


def test_events_default_status(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patient_id": "p1", "count": 0, "events": []})
    run_cli(["--json", "state", "events", "p1"], handler=handler)
    assert seen[0].url.params.get("status") == "complete"


def test_memories_query(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patient_id": "p1", "count": 0, "results": []})
    run_cli(["--json", "state", "memories", "p1", "--query", "fatigue"], handler=handler)
    assert seen[0].url.path.endswith("/v1/state/p1/memories")
    assert seen[0].url.params.get("query") == "fatigue"


def test_state_404(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "patient not found"})

    code, out, _ = run_cli(["--json", "state", "stable", "missing"], handler=handler)
    assert code == 4
    assert json_envelope(out)["error"]["code"] == "NOT_FOUND"


def test_state_never_sends_project_header(run_cli, no_creds, monkeypatch):
    """State is patient-keyed, not project-scoped — no X-Olira-Project header exists to send."""
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patient_id": "p1", "count": 0, "logs": []})
    run_cli(["--json", "state", "logs", "p1"], handler=handler)
    assert "x-olira-project" not in seen[0].headers
