"""olira patients / cohorts / projects / integrations — read-only query commands.

Every command here uses the "sdk" credential class (a raw olira_... API
key) — /v1/* routes reject browser-login JWTs. Patients and cohorts are
project-scoped (X-Olira-Project header); projects and integrations are
org-level and take no --project.
"""

from __future__ import annotations

from typing import Any

from olira_cli import http, output
from olira_cli.credentials import api_base, resolve_auth, resolve_project, sdk_headers
from olira_cli.errors import CliError, CommandResult

# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------


def _unwrap(body: dict[str, Any], key: str = "data") -> Any:
    """Most /v1/* responses wrap their payload in {"data": ...}; a few don't. Handle both."""
    return body.get(key, body) if key in body else body


def cmd_patients_list(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    external_system = getattr(args, "external_system", None)
    external_value = getattr(args, "external_value", None)
    if bool(external_system) != bool(external_value):
        raise CliError(
            "--external-system and --external-value must be given together.",
            code="USAGE",
            exit_code=2,
        )

    params: dict[str, Any] = {"limit": getattr(args, "limit", 100), "offset": getattr(args, "offset", 0)}
    if external_system:
        params["external_system"] = external_system
        params["external_value"] = external_value

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/patients", params=params, headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_patient_list(data.get("patients") or [])

    return CommandResult(data)


def _render_patient_list(patients: list[dict[str, Any]]) -> None:
    if not patients:
        print("No patients found.")
        return
    rows = []
    for p in patients:
        name = " ".join(filter(None, [p.get("first_name"), p.get("last_name")])) or "-"
        rows.append([str(p.get("id", "")), name, p.get("status", ""), p.get("email") or p.get("phone_number") or "-"])
    output.table(["ID", "NAME", "STATUS", "CONTACT"], rows)


def cmd_patients_get(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.get(
            f"{api_base(auth)}/v1/patients/{args.patient_id}",
            headers=sdk_headers(auth, project),
        )
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_patient(_unwrap(data))

    return CommandResult(data)


def _render_patient(p: dict[str, Any]) -> None:
    name = " ".join(filter(None, [p.get("first_name"), p.get("last_name")])) or "-"
    print(f"  ID:       {p.get('id', '')}")
    print(f"  Name:     {name}")
    print(f"  Status:   {p.get('status', '')}")
    if p.get("email"):
        print(f"  Email:    {p['email']}")
    if p.get("phone_number"):
        print(f"  Phone:    {p['phone_number']}")
    if p.get("date_of_birth"):
        print(f"  DOB:      {p['date_of_birth']}")
    if p.get("primary_disease_site"):
        print(f"  Disease:  {p['primary_disease_site']} ({p.get('disease_stage', '?')})")
    ext_ids = p.get("external_identifiers") or []
    if ext_ids:
        print("  External IDs:")
        for e in ext_ids:
            print(f"    {e.get('system', '')}: {e.get('value', '')}")
    print(f"  Created:  {p.get('created_at', '')}")


# ---------------------------------------------------------------------------
# Cohorts
# ---------------------------------------------------------------------------


def cmd_cohorts_list(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/cohorts", headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_cohort_list(_unwrap(data) or [])

    return CommandResult(data)


def _render_cohort_list(cohorts: list[dict[str, Any]]) -> None:
    if not cohorts:
        print("No cohorts found.")
        return
    rows = [
        [
            str(c.get("id", "")),
            c.get("name", ""),
            str(c.get("patient_count", 0)),
            str(c.get("template_assignment_count", 0)),
        ]
        for c in cohorts
    ]
    output.table(["ID", "NAME", "PATIENTS", "TEMPLATES"], rows)


def cmd_cohorts_get(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/cohorts/{args.cohort_id}", headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_cohort(_unwrap(data))

    return CommandResult(data)


def _render_cohort(c: dict[str, Any]) -> None:
    patient_ids = c.get("patient_ids") or []
    print(f"  ID:          {c.get('id', '')}")
    print(f"  Name:        {c.get('name', '')}")
    if c.get("description"):
        print(f"  Description: {c['description']}")
    print(f"  Patients:    {len(patient_ids)}")
    print(f"  Created:     {c.get('created_at', '')}")
    print(f"  Updated:     {c.get('updated_at', '')}")


def cmd_cohorts_templates(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/cohorts/{args.cohort_id}/templates", headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_cohort_templates(_unwrap(data) or [])

    return CommandResult(data)


def _render_cohort_templates(templates: list[dict[str, Any]]) -> None:
    if not templates:
        print("No templates assigned.")
        return
    rows = [[t.get("summary_type", ""), str(t.get("template_id", "")), t.get("assigned_at", "")] for t in templates]
    output.table(["SUMMARY TYPE", "TEMPLATE ID", "ASSIGNED"], rows)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def cmd_projects_list(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/projects", headers=sdk_headers(auth))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_project_list(_unwrap(data) or [])

    return CommandResult(data)


def _render_project_list(projects: list[dict[str, Any]]) -> None:
    if not projects:
        print("No projects found.")
        return
    rows = []
    for p in projects:
        default_marker = "yes" if p.get("is_default") else ""
        rows.append(
            [
                str(p.get("id", "")),
                p.get("name", ""),
                p.get("slug", ""),
                p.get("environment") or "-",
                p.get("status", ""),
                default_marker,
            ]
        )
    output.table(["ID", "NAME", "SLUG", "ENV", "STATUS", "DEFAULT"], rows)


def cmd_projects_get(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/projects/{args.project_id}", headers=sdk_headers(auth))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_project(_unwrap(data))

    return CommandResult(data)


def _render_project(p: dict[str, Any]) -> None:
    print(f"  ID:          {p.get('id', '')}")
    print(f"  Name:        {p.get('name', '')}")
    print(f"  Slug:        {p.get('slug', '')}")
    print(f"  Environment: {p.get('environment') or '-'}")
    print(f"  Status:      {p.get('status', '')}")
    print(f"  Default:     {'yes' if p.get('is_default') else 'no'}")
    print(f"  Created:     {p.get('created_at', '')}")
    if p.get("deprecated_at"):
        print(f"  Deprecated:  {p['deprecated_at']}")


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


def cmd_integrations_catalog(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/integrations/catalog", headers=sdk_headers(auth))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_integration_catalog(_unwrap(data) or [])

    return CommandResult(data)


def _render_integration_catalog(catalog: list[dict[str, Any]]) -> None:
    if not catalog:
        print("No providers in catalog.")
        return
    rows = [
        [c.get("integration_type", ""), c.get("name", ""), c.get("category") or "-", c.get("auth_mode", "")]
        for c in catalog
    ]
    output.table(["TYPE", "NAME", "CATEGORY", "AUTH MODE"], rows)


def cmd_integrations_list(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/integrations", headers=sdk_headers(auth))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_integration_list(_unwrap(data) or [])

    return CommandResult(data)


def _render_integration_list(integrations: list[dict[str, Any]]) -> None:
    if not integrations:
        print("No integrations connected.")
        return
    rows = [
        [
            str(i.get("id", "")),
            i.get("integration_type", ""),
            i.get("display_name") or "-",
            i.get("status", ""),
            i.get("connection_status") or "-",
        ]
        for i in integrations
    ]
    output.table(["ID", "TYPE", "NAME", "STATUS", "CONNECTION"], rows)


def cmd_integrations_get(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/integrations/{args.integration_id}", headers=sdk_headers(auth))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_integration(_unwrap(data))

    return CommandResult(data)


def _render_integration(i: dict[str, Any]) -> None:
    print(f"  ID:         {i.get('id', '')}")
    print(f"  Type:       {i.get('integration_type', '')}")
    if i.get("display_name"):
        print(f"  Name:       {i['display_name']}")
    print(f"  Status:     {i.get('status', '')}")
    print(f"  Connection: {i.get('connection_status') or '-'}")
    print(f"  Auth mode:  {i.get('auth_mode', '')}")
    if i.get("endpoint_url"):
        print(f"  Endpoint:   {i['endpoint_url']}")
    allowed = i.get("allowed_data_point_keys") or []
    print(f"  Data points allowed: {len(allowed)}")
    print(f"  Created:    {i.get('created_at', '')}")
    print(f"  Updated:    {i.get('updated_at', '')}")


def cmd_integrations_data_points(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    catalog_mode = getattr(args, "catalog", False)
    suffix = "/data-points/catalog" if catalog_mode else "/data-points"

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/integrations/{args.integration_id}{suffix}", headers=sdk_headers(auth))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        if catalog_mode:
            _render_data_point_catalog(_unwrap(data) or [])
        else:
            _render_data_points(_unwrap(data) or [])

    return CommandResult(data)


def _render_data_point_catalog(points: list[dict[str, Any]]) -> None:
    if not points:
        print("No data points available for this integration.")
        return
    rows = [[p.get("key", ""), p.get("name", ""), p.get("source") or "-", p.get("category") or "-"] for p in points]
    output.table(["KEY", "NAME", "SOURCE", "CATEGORY"], rows)


def _render_data_points(points: list[dict[str, Any]]) -> None:
    if not points:
        print("No data points subscribed.")
        return
    rows = [
        [str(p.get("id", "")), p.get("name", ""), p.get("status", ""), p.get("next_sync_at") or "-"] for p in points
    ]
    output.table(["ID", "NAME", "STATUS", "NEXT SYNC"], rows)
