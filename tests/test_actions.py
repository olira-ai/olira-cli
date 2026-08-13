"""olira actions — destination CRUD, secret rotation, and the delivery ledger.

Covers: sdk-credential-class enforcement, request body/param construction for
every subcommand, the create/update mutual-exclusion and all-or-nothing
validation rules, the delete confirmation prompt, and HTTP error mapping
(409 on redeliver).
"""

from __future__ import annotations

import httpx

from tests.conftest import json_envelope


def _capturing(status: int, body):
    seen: list[httpx.Request] = []

    def _h(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return _h, seen


# ---------------------------------------------------------------------------
# Credential class
# ---------------------------------------------------------------------------


def test_create_destination_requires_api_key_not_login(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "actions", "create-destination", "--url", "https://hooks.example.com/x"])
    assert code == 3
    env = json_envelope(out)
    assert env["error"]["code"] == "AUTH_REQUIRED"


def test_list_deliveries_requires_api_key(run_cli, creds_file):
    creds_file()
    code, out, _ = run_cli(["--json", "actions", "list-deliveries"])
    assert code == 3


# ---------------------------------------------------------------------------
# create-destination
# ---------------------------------------------------------------------------


def test_create_destination_webhook_full_body(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(
        201, {"id": "dest-1", "destination_type": "webhook", "status": "active", "signing_secret": "whsec_abc"}
    )
    code, out, _ = run_cli(
        [
            "--json",
            "actions",
            "create-destination",
            "--url",
            "https://hooks.example.com/olira",
            "--triggers",
            "patient.state.changed,ingestion.failed",
            "--description",
            "acme prod",
            "--header",
            "X-Api-Key=secret1",
            "--header",
            "X-Env=prod",
            "--rate-limit",
            "300",
            "--digest-time-of-day",
            "09:00",
            "--digest-timezone",
            "America/New_York",
            "--digest-triggers",
            "patient.state.changed",
            "--project",
            "proj-1",
        ],
        handler=handler,
    )
    assert code == 0
    env = json_envelope(out)
    assert env["data"]["signing_secret"] == "whsec_abc"

    body = seen[0].read()
    import json as _json

    parsed = _json.loads(body)
    assert parsed["config"] == {"destination_type": "webhook", "url": "https://hooks.example.com/olira"}
    assert parsed["subscribed_event_types"] == ["patient.state.changed", "ingestion.failed"]
    assert parsed["description"] == "acme prod"
    assert parsed["static_headers"] == {"X-Api-Key": "secret1", "X-Env": "prod"}
    assert parsed["rate_limit_per_minute"] == 300
    assert parsed["digest_schedule"] == {
        "time_of_day": "09:00",
        "timezone": "America/New_York",
        "event_types": ["patient.state.changed"],
    }
    assert seen[0].headers.get("x-olira-project") == "proj-1"


def test_create_destination_email_minimal_body(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(201, {"id": "dest-2", "destination_type": "email", "status": "active"})
    code, _, _ = run_cli(
        [
            "--json",
            "actions",
            "create-destination",
            "--to-email",
            "ops@acme.example",
            "--triggers",
            "ingestion.failed",
        ],
        handler=handler,
    )
    assert code == 0

    import json as _json

    parsed = _json.loads(seen[0].read())
    assert parsed["config"] == {"destination_type": "email", "to_email": "ops@acme.example"}
    assert parsed["subscribed_event_types"] == ["ingestion.failed"]
    assert "static_headers" not in parsed
    assert "digest_schedule" not in parsed


def test_create_destination_requires_triggers(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "actions", "create-destination", "--url", "https://x.example.com"])
    assert code == 2
    assert json_envelope(out)["error"]["code"] == "USAGE"


def test_create_destination_url_and_to_email_are_mutually_exclusive(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(
        ["--json", "actions", "create-destination", "--url", "https://x.example.com", "--to-email", "a@b.com"]
    )
    assert code == 2
    assert json_envelope(out)["error"]["code"] == "USAGE"


def test_create_destination_requires_one_of_url_or_to_email(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "actions", "create-destination"])
    assert code == 2
    assert json_envelope(out)["error"]["code"] == "USAGE"


def test_create_destination_digest_flags_must_be_given_together(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(
        [
            "--json",
            "actions",
            "create-destination",
            "--url",
            "https://x.example.com",
            "--triggers",
            "patient.state.changed",
            "--digest-time-of-day",
            "09:00",
        ]
    )
    assert code == 2
    assert json_envelope(out)["error"]["code"] == "USAGE"


# ---------------------------------------------------------------------------
# update-destination
# ---------------------------------------------------------------------------


def test_update_destination_only_sends_given_fields(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(200, {"id": "dest-1", "status": "disabled"})
    code, _, _ = run_cli(["--json", "actions", "update-destination", "dest-1", "--status", "disabled"], handler=handler)
    assert code == 0

    import json as _json

    parsed = _json.loads(seen[0].read())
    assert parsed == {"status": "disabled"}
    assert seen[0].method == "PATCH"


def test_update_destination_clear_digest_schedule_sends_explicit_null(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(200, {"id": "dest-1"})
    run_cli(["--json", "actions", "update-destination", "dest-1", "--clear-digest-schedule"], handler=handler)

    import json as _json

    parsed = _json.loads(seen[0].read())
    assert parsed == {"digest_schedule": None}


def test_update_destination_clear_and_digest_flags_conflict(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(
        [
            "--json",
            "actions",
            "update-destination",
            "dest-1",
            "--clear-digest-schedule",
            "--digest-time-of-day",
            "09:00",
            "--digest-timezone",
            "UTC",
            "--digest-triggers",
            "patient.state.changed",
        ]
    )
    assert code == 2
    assert json_envelope(out)["error"]["code"] == "USAGE"


def test_update_destination_with_no_fields_is_usage_error(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "actions", "update-destination", "dest-1"])
    assert code == 2
    assert json_envelope(out)["error"]["code"] == "USAGE"


# ---------------------------------------------------------------------------
# delete-destination
# ---------------------------------------------------------------------------


def test_delete_destination_yes_skips_prompt(run_cli, no_creds, monkeypatch, refuse_input):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(200, {"message": "disabled", "dead_lettered_deliveries": 2})
    code, out, _ = run_cli(["--json", "actions", "delete-destination", "dest-1", "--yes"], handler=handler)
    assert code == 0
    assert seen[0].method == "DELETE"
    assert json_envelope(out)["data"]["dead_lettered_deliveries"] == 2


def test_delete_destination_without_yes_and_no_tty_fails_fast(run_cli, no_creds, monkeypatch, no_tty, refuse_input):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    code, out, _ = run_cli(["--json", "actions", "delete-destination", "dest-1"])
    assert code == 6
    assert json_envelope(out)["error"]["code"] == "PROMPT_REQUIRED"


# ---------------------------------------------------------------------------
# rotate-destination-secret
# ---------------------------------------------------------------------------


def test_rotate_destination_secret_posts_to_rotate_path(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(200, {"id": "dest-1", "signing_secret": "whsec_new"})
    code, out, _ = run_cli(["--json", "actions", "rotate-destination-secret", "dest-1"], handler=handler)
    assert code == 0
    assert seen[0].method == "POST"
    assert str(seen[0].url).endswith("/v1/actions/destinations/dest-1/rotate-secret")
    assert json_envelope(out)["data"]["signing_secret"] == "whsec_new"


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------


def test_list_deliveries_passes_filters_and_project_header(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(200, {"data": [], "next_cursor": None})
    run_cli(
        [
            "--json",
            "actions",
            "list-deliveries",
            "--destination-id",
            "dest-1",
            "--status",
            "dead_letter",
            "--trigger",
            "patient.state.changed",
            "--cursor",
            "abc123",
            "--limit",
            "25",
            "--project",
            "proj-1",
        ],
        handler=handler,
    )
    params = seen[0].url.params
    assert params.get("destination_id") == "dest-1"
    assert params.get("status") == "dead_letter"
    assert params.get("event_type") == "patient.state.changed"
    assert params.get("cursor") == "abc123"
    assert params.get("limit") == "25"
    assert seen[0].headers.get("x-olira-project") == "proj-1"


def test_get_delivery_path(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(200, {"id": "del-1", "status": "delivered", "attempts": []})
    code, out, _ = run_cli(["--json", "actions", "get-delivery", "del-1"], handler=handler)
    assert code == 0
    assert str(seen[0].url).endswith("/v1/actions/deliveries/del-1")
    assert json_envelope(out)["data"]["id"] == "del-1"


def test_redeliver_delivery_posts_to_redeliver_path(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, seen = _capturing(201, {"id": "del-2", "redelivery_of": "del-1"})
    code, out, _ = run_cli(["--json", "actions", "redeliver-delivery", "del-1"], handler=handler)
    assert code == 0
    assert seen[0].method == "POST"
    assert str(seen[0].url).endswith("/v1/actions/deliveries/del-1/redeliver")
    assert json_envelope(out)["data"]["redelivery_of"] == "del-1"


def test_redeliver_delivery_409_disabled_destination_maps_to_conflict(run_cli, no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    handler, _ = _capturing(409, {"detail": "Destination is disabled."})
    code, out, _ = run_cli(["--json", "actions", "redeliver-delivery", "del-1"], handler=handler)
    assert code == 6
    assert json_envelope(out)["error"]["code"] == "CONFLICT"
