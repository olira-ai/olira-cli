"""olira patients / cohorts / projects / integrations — read-only query commands.

Covers: envelope shape, path/param construction, --project header presence
(patients/cohorts) vs absence (projects/integrations), sdk-credential-class
enforcement, and HTTP error mapping.
"""

from __future__ import annotations

import httpx

from tests.conftest import json_envelope


def _capturing(body):
    """Returns (handler, requests) — requests accumulates every httpx.Request seen."""
    seen: list[httpx.Request] = []

    def _h(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    return _h, seen


# ---------------------------------------------------------------------------
# Credential class: every new command is sdk-only
# ---------------------------------------------------------------------------


def test_patients_list_requires_api_key_not_login(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "patients", "list"])
    assert code == 3
    env = json_envelope(out)
    assert env["error"]["code"] == "AUTH_REQUIRED"
    assert "OLIRA_API_KEY" in env["error"]["remediation"]


def test_state_stable_requires_api_key(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "state", "stable", "patient-1"])
    assert code == 3


def test_integrations_list_requires_api_key(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "integrations", "list"])
    assert code == 3


def test_projects_list_requires_api_key(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "projects", "list"])
    assert code == 3


def test_cohorts_list_requires_api_key(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "cohorts", "list"])
    assert code == 3


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------


def test_patients_list_envelope_and_project_header(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patients": [{"id": "p1", "first_name": "Jane"}], "total": 1, "has_more": False})
    code, out, _ = run_cli(["--json", "patients", "list", "--project", "proj-1"], handler=handler)
    assert code == 0
    env = json_envelope(out)
    assert env["data"]["patients"][0]["id"] == "p1"
    assert seen[0].headers.get("x-olira-project") == "proj-1"
    assert seen[0].url.params.get("limit") == "100"
    assert seen[0].url.params.get("offset") == "0"


def test_patients_list_no_project_header_when_unset(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"patients": [], "total": 0, "has_more": False})
    run_cli(["--json", "patients", "list"], handler=handler)
    assert "x-olira-project" not in seen[0].headers


def test_patients_list_external_pair_must_be_together(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "patients", "list", "--external-system", "epic"])
    assert code == 2
    env = json_envelope(out)
    assert env["error"]["code"] == "USAGE"


def test_patients_get_path(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"id": "p1", "first_name": "Jane", "last_name": "Doe"})
    code, out, _ = run_cli(["--json", "patients", "get", "p1"], handler=handler)
    assert code == 0
    assert seen[0].url.path.endswith("/v1/patients/p1")


def test_patients_get_404(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    code, out, _ = run_cli(["--json", "patients", "get", "missing"], handler=handler)
    assert code == 4
    assert json_envelope(out)["error"]["code"] == "NOT_FOUND"


def test_patients_get_403(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "forbidden"})

    code, out, _ = run_cli(["--json", "patients", "get", "p1"], handler=handler)
    assert code == 3
    assert json_envelope(out)["error"]["code"] == "AUTH_FORBIDDEN"


# ---------------------------------------------------------------------------
# Cohorts
# ---------------------------------------------------------------------------


def test_cohorts_list_has_project_header(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"data": [{"id": "c1", "name": "Trial A"}]})
    run_cli(["--json", "cohorts", "list", "--project", "trial"], handler=handler)
    assert seen[0].headers.get("x-olira-project") == "trial"


def test_cohorts_get(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"id": "c1", "name": "Trial A", "patient_ids": ["p1", "p2"]})
    code, out, _ = run_cli(["--json", "cohorts", "get", "c1"], handler=handler)
    assert code == 0
    assert seen[0].url.path.endswith("/v1/cohorts/c1")
    assert json_envelope(out)["data"]["patient_ids"] == ["p1", "p2"]


def test_cohorts_templates(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"data": [{"summary_type": "weekly", "template_id": "t1"}]})
    run_cli(["--json", "cohorts", "templates", "c1"], handler=handler)
    assert seen[0].url.path.endswith("/v1/cohorts/c1/templates")


# ---------------------------------------------------------------------------
# Projects — org-level, no --project flag exists at all
# ---------------------------------------------------------------------------


def test_projects_list_no_project_header(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"data": [{"id": "proj1", "name": "Default", "is_default": True}]})
    code, out, _ = run_cli(["--json", "projects", "list"], handler=handler)
    assert code == 0
    assert "x-olira-project" not in seen[0].headers


def test_projects_get_by_slug(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"id": "proj1", "name": "Dev", "slug": "dev-sandbox"})
    run_cli(["--json", "projects", "get", "dev-sandbox"], handler=handler)
    assert seen[0].url.path.endswith("/v1/projects/dev-sandbox")


def test_projects_has_no_project_flag(run_cli):
    """Confirms --project isn't even a recognized flag for projects (org-level resource)."""
    import pytest

    with pytest.raises(SystemExit) as exc:
        run_cli(["projects", "list", "--project", "x"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


def test_integrations_catalog(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"data": [{"integration_type": "epic", "name": "Epic"}]})
    code, out, _ = run_cli(["--json", "integrations", "catalog"], handler=handler)
    assert code == 0
    assert seen[0].url.path.endswith("/v1/integrations/catalog")


def test_integrations_get(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"id": "i1", "integration_type": "epic", "status": "active"})
    run_cli(["--json", "integrations", "get", "i1"], handler=handler)
    assert seen[0].url.path.endswith("/v1/integrations/i1")


def test_integrations_data_points_subscribed_vs_catalog(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"data": []})
    run_cli(["--json", "integrations", "data-points", "i1"], handler=handler)
    assert seen[0].url.path.endswith("/v1/integrations/i1/data-points")

    handler2, seen2 = _capturing({"data": []})
    run_cli(["--json", "integrations", "data-points", "i1", "--catalog"], handler=handler2)
    assert seen2[0].url.path.endswith("/v1/integrations/i1/data-points/catalog")


# ---------------------------------------------------------------------------
# Log types — org-level, no --project flag exists at all
# ---------------------------------------------------------------------------


def test_log_types_list_requires_api_key(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "log-types", "list"])
    assert code == 3


def test_log_types_list_no_project_header(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing({"data": [{"subtype": "symptom_report", "category": "symptom_reports"}]})
    code, out, _ = run_cli(["--json", "log-types", "list"], handler=handler)
    assert code == 0
    assert seen[0].url.path.endswith("/v1/log-types")
    assert "x-olira-project" not in seen[0].headers


def test_log_types_get_by_subtype(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(
        {
            "subtype": "symptom_report",
            "category": "symptom_reports",
            "aliases": [],
            "display_name": "Symptom report",
            "description": "desc",
            "payload_schema": {"type": "object"},
            "payload_description": "",
            "sources": ["logged"],
            "version": 1,
        }
    )
    run_cli(["--json", "log-types", "get", "symptom_report"], handler=handler)
    assert seen[0].url.path.endswith("/v1/log-types/symptom_report")


def test_log_types_has_no_project_flag(run_cli):
    """Confirms --project isn't even a recognized flag for log-types (org-level resource)."""
    import pytest

    with pytest.raises(SystemExit) as exc:
        run_cli(["log-types", "list", "--project", "x"])
    assert exc.value.code == 2
