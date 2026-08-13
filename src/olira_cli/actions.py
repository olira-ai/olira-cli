"""olira actions — outbound-action destinations and delivery ledger.

Mirrors the Olira SDK's outbound-actions surface (see `olira-actions` skill)
as CLI commands, so a human or headless agent can manage destinations and
inspect deliveries from the shell without writing SDK code. Wire field names
(`subscribed_event_types`, `event_type`, `digest_schedule.event_types`) match
the REST contract in `services/app-api/routes/actions_common.py` — this
module doesn't rename them to "trigger" the way the SDKs do, since flags here
map straight onto the request/response bodies.

Every command uses the "sdk" credential class, scoped `sdk:actions`, same as
`ingest`/`patients`/etc. Destinations are project-scoped (`--project` /
`OLIRA_PROJECT`), same convention as `patients`/`cohorts`.
"""

from __future__ import annotations

from typing import Any

from olira_cli import http, output
from olira_cli.credentials import api_base, resolve_auth, resolve_project, sdk_headers
from olira_cli.errors import CliError, CommandResult, require_tty

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _unwrap(body: dict[str, Any], key: str = "data") -> Any:
    """Most /v1/* responses wrap their payload in {"data": ...}; a few don't. Handle both."""
    return body.get(key, body) if key in body else body


def _parse_triggers(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_headers(pairs: list[str] | None) -> dict[str, str] | None:
    if not pairs:
        return None
    headers: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise CliError(f"--header must be KEY=VALUE, got {pair!r}.", code="USAGE", exit_code=2)
        k, v = pair.split("=", 1)
        headers[k] = v
    return headers


def _digest_schedule_from_flags(args: Any) -> dict[str, Any] | None:
    time_of_day = getattr(args, "digest_time_of_day", None)
    timezone = getattr(args, "digest_timezone", None)
    triggers = _parse_triggers(getattr(args, "digest_triggers", None))
    if time_of_day is None and timezone is None and triggers is None:
        return None
    if time_of_day is None or timezone is None or triggers is None:
        raise CliError(
            "--digest-time-of-day, --digest-timezone, and --digest-triggers must be given together.",
            code="USAGE",
            exit_code=2,
        )
    return {"time_of_day": time_of_day, "timezone": timezone, "event_types": triggers}


def _destination_config_from_flags(args: Any) -> dict[str, Any]:
    url = getattr(args, "url", None)
    to_email = getattr(args, "to_email", None)
    if bool(url) == bool(to_email):
        raise CliError("Pass exactly one of --url (webhook) or --to-email (email).", code="USAGE", exit_code=2)
    if url:
        return {"destination_type": "webhook", "url": url}
    config: dict[str, Any] = {"destination_type": "email", "to_email": to_email}
    if getattr(args, "subject", None):
        config["subject"] = args.subject
    if getattr(args, "from_name", None):
        config["from_name"] = args.from_name
    return config


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------


def cmd_create_destination(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    body: dict[str, Any] = {"config": _destination_config_from_flags(args)}
    triggers = _parse_triggers(getattr(args, "triggers", None))
    if not triggers:
        raise CliError(
            "Pass --triggers with at least one trigger (comma-separated), or --triggers '*'.",
            code="USAGE",
            exit_code=2,
        )
    body["subscribed_event_types"] = triggers
    if getattr(args, "description", None):
        body["description"] = args.description
    headers = _parse_headers(getattr(args, "header", None))
    if headers is not None:
        body["static_headers"] = headers
    if getattr(args, "rate_limit", None) is not None:
        body["rate_limit_per_minute"] = args.rate_limit
    digest = _digest_schedule_from_flags(args)
    if digest is not None:
        body["digest_schedule"] = digest

    with http.client() as client:
        r = client.post(f"{api_base(auth)}/v1/actions/destinations", json=body, headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    destination = _unwrap(data)
    if not output.json_mode():
        _render_destination(destination)
        if destination.get("signing_secret"):
            print()
            print("  Signing secret (shown once — store it now, it cannot be read back):")
            print(f"  {destination['signing_secret']}")

    return CommandResult(destination)


def cmd_list_destinations(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/actions/destinations", headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_destination_list(_unwrap(data) or [])

    return CommandResult(data)


def _render_destination_list(destinations: list[dict[str, Any]]) -> None:
    if not destinations:
        print("No action destinations found.")
        return
    rows = [
        [
            str(d.get("id", "")),
            d.get("destination_type", ""),
            d.get("status", ""),
            str(len(d.get("subscribed_triggers") or d.get("subscribed_event_types") or [])),
            str(d.get("consecutive_failures", 0)),
        ]
        for d in destinations
    ]
    output.table(["ID", "TYPE", "STATUS", "TRIGGERS", "FAILURES"], rows)


def cmd_get_destination(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.get(
            f"{api_base(auth)}/v1/actions/destinations/{args.destination_id}", headers=sdk_headers(auth, project)
        )
        r.raise_for_status()
        data = r.json()

    destination = _unwrap(data)
    if not output.json_mode():
        _render_destination(destination)

    return CommandResult(destination)


def _render_destination(d: dict[str, Any]) -> None:
    print(f"  ID:          {d.get('id', '')}")
    print(f"  Type:        {d.get('destination_type', '')}")
    print(f"  Status:      {d.get('status', '')}")
    triggers = d.get("subscribed_triggers") or d.get("subscribed_event_types") or []
    print(f"  Triggers:    {', '.join(triggers) if triggers else '-'}")
    if d.get("description"):
        print(f"  Description: {d['description']}")
    print(f"  Rate limit:  {d.get('rate_limit_per_minute', '-')}/min")
    if d.get("signing_secret_last4"):
        print(f"  Secret:      ...{d['signing_secret_last4']}")
    digest = d.get("digest_schedule")
    if digest:
        print(
            f"  Digest:      {digest.get('time_of_day')} {digest.get('timezone')} — {', '.join(digest.get('event_types', []))}"
        )
    print(f"  Failures:    {d.get('consecutive_failures', 0)}")
    if d.get("auto_disabled_at"):
        print(f"  Auto-disabled: {d['auto_disabled_at']}")


def cmd_update_destination(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    body: dict[str, Any] = {}
    if getattr(args, "url", None) is not None:
        body["url"] = args.url
    if getattr(args, "to_email", None) is not None:
        body["to_email"] = args.to_email
    if getattr(args, "subject", None) is not None:
        body["subject"] = args.subject
    if getattr(args, "description", None) is not None:
        body["description"] = args.description
    triggers = _parse_triggers(getattr(args, "triggers", None))
    if triggers is not None:
        body["subscribed_event_types"] = triggers
    if getattr(args, "status", None) is not None:
        body["status"] = args.status
    headers = _parse_headers(getattr(args, "header", None))
    if headers is not None:
        body["static_headers"] = headers

    clear_digest = getattr(args, "clear_digest_schedule", False)
    digest = _digest_schedule_from_flags(args)
    if clear_digest and digest is not None:
        raise CliError(
            "Pass either --clear-digest-schedule or the --digest-* flags, not both.", code="USAGE", exit_code=2
        )
    if clear_digest:
        body["digest_schedule"] = None
    elif digest is not None:
        body["digest_schedule"] = digest

    if not body:
        raise CliError("Nothing to update — pass at least one field to change.", code="USAGE", exit_code=2)

    with http.client() as client:
        r = client.patch(
            f"{api_base(auth)}/v1/actions/destinations/{args.destination_id}",
            json=body,
            headers=sdk_headers(auth, project),
        )
        r.raise_for_status()
        data = r.json()

    destination = _unwrap(data)
    if not output.json_mode():
        _render_destination(destination)

    return CommandResult(destination)


def cmd_delete_destination(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    if not args.yes:
        require_tty("Deleting a destination", "--yes")
        confirm = (
            input(f"Disable destination {args.destination_id}? Pending/retrying deliveries will dead-letter. [y/N]: ")
            .strip()
            .lower()
        )
        if confirm != "y":
            if not output.json_mode():
                print("Cancelled.")
            return CommandResult({"destination_id": args.destination_id, "deleted": False})

    with http.client() as client:
        r = client.delete(
            f"{api_base(auth)}/v1/actions/destinations/{args.destination_id}", headers=sdk_headers(auth, project)
        )
        r.raise_for_status()
        data = r.json()

    result = _unwrap(data)
    if not output.json_mode():
        dead_lettered = result.get("dead_lettered_deliveries", 0) if isinstance(result, dict) else 0
        print(f"  Destination {args.destination_id} disabled. {dead_lettered} pending deliveries dead-lettered.")

    return CommandResult(result if isinstance(result, dict) else {"message": result})


def cmd_rotate_destination_secret(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.post(
            f"{api_base(auth)}/v1/actions/destinations/{args.destination_id}/rotate-secret",
            headers=sdk_headers(auth, project),
        )
        r.raise_for_status()
        data = r.json()

    destination = _unwrap(data)
    if not output.json_mode():
        print("  Signing secret rotated. Old secret stays valid for 24h (dual-signing).")
        if destination.get("signing_secret"):
            print("  New secret (shown once — store it now, it cannot be read back):")
            print(f"  {destination['signing_secret']}")

    return CommandResult(destination)


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------


def cmd_list_deliveries(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    params: dict[str, Any] = {"limit": getattr(args, "limit", 50)}
    if getattr(args, "destination_id", None):
        params["destination_id"] = args.destination_id
    if getattr(args, "status", None):
        params["status"] = args.status
    if getattr(args, "trigger", None):
        params["event_type"] = args.trigger
    if getattr(args, "cursor", None):
        params["cursor"] = args.cursor

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/actions/deliveries", params=params, headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    if not output.json_mode():
        _render_delivery_list(data.get("data") or [])
        if data.get("next_cursor"):
            print(f"\n  More results: --cursor {data['next_cursor']}")

    return CommandResult(data)


def _render_delivery_list(deliveries: list[dict[str, Any]]) -> None:
    if not deliveries:
        print("No deliveries found.")
        return
    rows = [
        [
            str(d.get("id", "")),
            d.get("trigger") or d.get("event_type", ""),
            d.get("status", ""),
            str(d.get("destination_id", "")),
            d.get("delivered_at") or "-",
        ]
        for d in deliveries
    ]
    output.table(["ID", "TRIGGER", "STATUS", "DESTINATION", "DELIVERED"], rows)


def cmd_get_delivery(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.get(f"{api_base(auth)}/v1/actions/deliveries/{args.delivery_id}", headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    delivery = _unwrap(data)
    if not output.json_mode():
        _render_delivery(delivery)

    return CommandResult(delivery)


def _render_delivery(d: dict[str, Any]) -> None:
    print(f"  ID:          {d.get('id', '')}")
    print(f"  Trigger:     {d.get('trigger') or d.get('event_type', '')}")
    print(f"  Status:      {d.get('status', '')}")
    print(f"  Destination: {d.get('destination_id', '')}")
    if d.get("delivered_at"):
        print(f"  Delivered:   {d['delivered_at']}")
    if d.get("redelivery_of"):
        print(f"  Redelivery of: {d['redelivery_of']}")
    attempts = d.get("attempts") or []
    if attempts:
        print(f"  Attempts ({len(attempts)}):")
        for a in attempts:
            print(f"    #{a.get('attempt')} {a.get('at', '')} {a.get('outcome', '')} http={a.get('http_status', '-')}")


def cmd_redeliver_delivery(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.post(
            f"{api_base(auth)}/v1/actions/deliveries/{args.delivery_id}/redeliver", headers=sdk_headers(auth, project)
        )
        r.raise_for_status()
        data = r.json()

    delivery = _unwrap(data)
    if not output.json_mode():
        print(f"  Redelivered as new delivery {delivery.get('id', '')}.")

    return CommandResult(delivery)
