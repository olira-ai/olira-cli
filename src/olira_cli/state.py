"""olira state — read-only patient clinical state queries.

Every command here uses the "sdk" credential class (a raw olira_... API
key) and needs sdk:state-read scope. patient_id is always a path param;
there is no --project (state is keyed by patient, not project). Clinical
payloads are arbitrary JSON — human mode pretty-prints them rather than
inventing a prose format.
"""

from __future__ import annotations

import json
from typing import Any

from olira_cli import http, output
from olira_cli.credentials import Auth, api_base, resolve_auth, sdk_headers
from olira_cli.errors import CommandResult


def _get(auth: Auth, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with http.client() as client:
        r = client.get(f"{api_base(auth)}{path}", params=params, headers=sdk_headers(auth))
        r.raise_for_status()
        return r.json()


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_stable(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    params = {}
    if getattr(args, "modules", None):
        params["modules"] = args.modules
    data = _get(auth, f"/v1/state/{args.patient_id}/stable", params)

    if not output.json_mode():
        modules = data.get("modules") or {}
        print(f"  Patient: {data.get('patient_id', '')}")
        if not modules:
            print("  No stable modules.")
        for module_type, module in modules.items():
            print(f"\n  {module_type}  (updated {module.get('updated_at', '')})")
            _print_json(module.get("payload"))

    return CommandResult(data)


def cmd_modules(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    module_type = getattr(args, "module_type", None)

    if module_type:
        data = _get(auth, f"/v1/state/{args.patient_id}/event-modules/{module_type}")
        if not output.json_mode():
            print(f"  Patient: {data.get('patient_id', '')}")
            print(f"  Module:  {data.get('module_type', '')}")
            print(f"  Created: {data.get('created_at', '')}")
            print(f"  Updated: {data.get('updated_at', '')}")
            _print_json(data.get("payload"))
        return CommandResult(data)

    data = _get(auth, f"/v1/state/{args.patient_id}/event-modules")
    if not output.json_mode():
        modules = data.get("modules") or []
        if not modules:
            print("No event state modules.")
        else:
            rows = [[m.get("module_type", ""), m.get("created_at", ""), m.get("updated_at", "")] for m in modules]
            output.table(["MODULE TYPE", "CREATED", "UPDATED"], rows)
    return CommandResult(data)


def cmd_views(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    view_type = getattr(args, "view_type", None)

    if view_type:
        data = _get(auth, f"/v1/state/{args.patient_id}/views/{view_type}")
        if not output.json_mode():
            print(f"  Patient:    {data.get('patient_id', '')}")
            print(f"  View type:  {data.get('view_type', '')}")
            print(f"  View id:    {data.get('view_id', '')}")
            print(f"  Valid from: {data.get('valid_from', '')}")
            print(f"  Valid to:   {data.get('valid_to') or '-'}")
            _print_json(data.get("content"))
        return CommandResult(data)

    data = _get(auth, f"/v1/state/{args.patient_id}/views")
    if not output.json_mode():
        views = data.get("views") or []
        if not views:
            print("No views.")
        else:
            rows = [
                [
                    v.get("view_type", ""),
                    str(v.get("view_id", "")),
                    str(v.get("has_blocks", False)),
                    str(v.get("has_temp", False)),
                ]
                for v in views
            ]
            output.table(["VIEW TYPE", "VIEW ID", "HAS BLOCKS", "HAS TEMP"], rows)
    return CommandResult(data)


def cmd_view_block(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    data = _get(auth, f"/v1/state/{args.patient_id}/views/{args.view_type}/blocks/{args.block_id}")

    if not output.json_mode():
        print(f"  Patient:   {data.get('patient_id', '')}")
        print(f"  View type: {data.get('view_type', '')}")
        print(f"  Block id:  {data.get('block_id', '')}")
        print(f"  Updated:   {data.get('updated_at', '')}")
        confidences = data.get("confidences")
        if confidences:
            print(f"  Confidences: {confidences}")
        _print_json(data.get("content"))

    return CommandResult(data)


def cmd_recent(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    params = {"limit": getattr(args, "limit", 50)}
    data = _get(auth, f"/v1/state/{args.patient_id}/views/{args.view_type}/recent", params)

    if not output.json_mode():
        entries = data.get("entries") or []
        print(f"  Patient:   {data.get('patient_id', '')}")
        print(f"  View type: {data.get('view_type', '')}")
        print(f"  Showing {data.get('count', len(entries))} of {data.get('total_count', len(entries))}")
        for e in entries:
            print(f"    - {e}")

    return CommandResult(data)


def cmd_logs(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    params: dict[str, Any] = {"limit": getattr(args, "limit", 50), "offset": getattr(args, "offset", 0)}
    if getattr(args, "since", None):
        params["since"] = args.since
    if getattr(args, "event_types", None):
        params["event_types"] = args.event_types
    if getattr(args, "trace_type", None):
        params["trace_type"] = args.trace_type
    if getattr(args, "trace_id", None):
        params["trace_id"] = args.trace_id

    data = _get(auth, f"/v1/state/{args.patient_id}/logs", params)

    if not output.json_mode():
        logs = data.get("logs") or []
        print(f"  Patient: {data.get('patient_id', '')}  ({data.get('count', len(logs))} log(s))")
        for log in logs:
            print(f"\n  [{log.get('timestamp', '')}] {log.get('type', '')}  (id: {log.get('id', '')})")
            _print_json(log.get("payload"))

    return CommandResult(data)


def cmd_events(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    params: dict[str, Any] = {"limit": getattr(args, "limit", 50), "status": getattr(args, "status", "complete")}
    if getattr(args, "since", None):
        params["since"] = args.since
    if getattr(args, "log_type", None):
        params["log_type"] = args.log_type
    if getattr(args, "trace_type", None):
        params["trace_type"] = args.trace_type
    if getattr(args, "trace_id", None):
        params["trace_id"] = args.trace_id

    data = _get(auth, f"/v1/state/{args.patient_id}/events", params)

    if not output.json_mode():
        events = data.get("events") or []
        print(f"  Patient: {data.get('patient_id', '')}  ({data.get('count', len(events))} event(s))")
        for e in events:
            print(
                f"    - [{e.get('triggered_at', '')}] {e.get('log_type', '')}  "
                f"status={e.get('status', '')}  trigger={e.get('trigger', '')}"
            )

    return CommandResult(data)


def cmd_memories(args: Any) -> CommandResult:
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    params: dict[str, Any] = {"limit": getattr(args, "limit", 100)}
    if getattr(args, "query", None):
        params["query"] = args.query

    data = _get(auth, f"/v1/state/{args.patient_id}/memories", params)

    if not output.json_mode():
        results = data.get("results") or []
        print(f"  Patient: {data.get('patient_id', '')}  ({data.get('count', len(results))} memory/memories)")
        for m in results:
            print(f"\n  [{m.get('created_at', '')}] {m.get('content', '')}")

    return CommandResult(data)
