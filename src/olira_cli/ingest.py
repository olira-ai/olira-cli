"""olira ingest — historical bulk data ingestion commands.

Subcommands:
  upload <file>        Upload a JSONL file and create an ingestion job
  list                 List ingestion jobs for the org
  status <job_id>      Show (and optionally tail) a job's status
  confirm <job_id>     Confirm a job at AWAITING_CONFIRMATION
  cancel <job_id>      Cancel a job
  retry-backfill <id>  Retry view backfill on a COMPLETED_WITH_ERRORS job

Every command here uses the "sdk" credential class (a raw olira_... API
key) — /v1/* routes reject browser-login JWTs.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import httpx

from olira_cli import http, output
from olira_cli.credentials import Auth, api_base, resolve_auth, resolve_project, sdk_headers
from olira_cli.errors import CliError, CommandResult, StateError, from_http_error, require_tty

_TERMINAL = {"completed", "completed_with_errors", "cancelled", "failed"}
_ACTIVE = {"queued", "validating", "inserting_patients", "inserting_logs", "confirmed", "replaying", "backfilling"}
_PHASE2 = {"confirmed", "replaying", "backfilling"}
_MISSING_TEMPLATE_SLOT = "missing_template_slot"
_HEARTBEAT_SECONDS = 60.0
_RETRY_BACKOFFS = (2.0, 4.0, 8.0)

_STATUS_LABELS: dict[str, str] = {
    "queued": "Queued",
    "validating": "Validating",
    "inserting_patients": "Inserting patients",
    "inserting_logs": "Inserting logs",
    "awaiting_confirmation": "Awaiting confirmation",
    "confirmed": "Confirmed",
    "replaying": "Replaying",
    "backfilling": "Backfilling",
    "completed": "Completed",
    "completed_with_errors": "Completed with errors",
    "cancelled": "Cancelled",
    "failed": "Failed",
}


def _fmt_status(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def _progress_bar(pct: float, width: int = 24) -> str:
    filled = int(pct / 100 * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {pct:.0f}%"


def _print_job_row(j: dict[str, Any]) -> None:
    jid = j.get("job_id", "")
    st = _fmt_status(j.get("status", ""))
    pts = f"{j.get('patients_processed', 0)}/{j.get('patients_total', 0)} pts"
    logs = f"{j.get('logs_processed', 0)}/{j.get('logs_total', 0)} logs"
    errs = f"  {j.get('error_count', 0)} err" if j.get("error_count") else ""
    age = (j.get("created_at") or "")[:10]
    print(f"  {jid}  {st:<28} {pts:<14} {logs:<14}{errs:<10} {age}")


def _fetch_job(client: httpx.Client, auth: Auth, job_id: str, project: str | None) -> dict[str, Any]:
    r = client.get(f"{api_base(auth)}/v1/ingestion/jobs/{job_id}", headers=sdk_headers(auth, project), timeout=30)
    r.raise_for_status()
    return r.json()


def _partition_error_summary(errors: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings = [e for e in errors if e.get("code") == _MISSING_TEMPLATE_SLOT]
    errs = [e for e in errors if e.get("code") != _MISSING_TEMPLATE_SLOT]
    return warnings, errs


def _job_has_missing_template_slots(job: dict[str, Any]) -> bool:
    slots = job.get("missing_template_slots") or {}
    if slots:
        return True
    warnings, _ = _partition_error_summary(job.get("error_summary") or [])
    return bool(warnings)


def _short_patient_id(patient_id: str) -> str:
    if len(patient_id) > 12:
        return f"{patient_id[:8]}…"
    return patient_id


def _print_missing_template_slot_summary(job: dict[str, Any]) -> None:
    slots: dict[str, list[str]] = job.get("missing_template_slots") or {}
    if not slots:
        warnings, _ = _partition_error_summary(job.get("error_summary") or [])
        for w in warnings:
            print(f"    {w.get('message', '')}")
        return
    print("\n  ⚠  Some patients are missing view template slots:")
    for pid, types in sorted(slots.items()):
        types_str = ", ".join(types)
        print(f"     Patient {_short_patient_id(pid)}: {types_str}")


def _print_awaiting_confirmation_hints(job_id: str) -> None:
    print(
        "\n  ⚑ Job is awaiting your confirmation.\n"
        f"  Review patients, logs and views before proceeding:\n"
        f"    olira ingest status {job_id}\n"
        f"\n  To confirm (starts graph replay + view backfill):\n"
        f"    olira ingest confirm {job_id}\n"
        f"  To confirm with specific views:\n"
        f"    olira ingest confirm {job_id} --summary-types <type1> <type2>\n"
        f"  To initialize missing templates and confirm:\n"
        f"    olira ingest confirm {job_id} --init-templates\n"
        f"  To cancel:\n"
        f"    olira ingest cancel {job_id}"
    )


def _render_awaiting_confirmation(job: dict[str, Any], job_id: str) -> None:
    """Read-only rendering of an awaiting_confirmation job — never prompts, never mutates."""
    if _job_has_missing_template_slots(job):
        _print_missing_template_slot_summary(job)
    _print_awaiting_confirmation_hints(job_id)


def _prompt_missing_template_action() -> str:
    require_tty("Resolving missing template slots", "--init-templates or --no-backfill")
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice

    choices = [
        Choice("init", "Initialize missing templates and continue  (recommended)"),
        Choice("skip", "Skip view generation (--no-backfill)"),
        Choice("proceed", "Proceed anyway — backfill will fail for affected patients"),
        Choice("cancel", "Cancel job"),
    ]
    try:
        return inquirer.select(
            message="What would you like to do?",
            choices=choices,
        ).execute()
    except (KeyboardInterrupt, EOFError):
        raise CliError("Cancelled.", code="CANCELLED") from None


def _confirm_job(
    client: httpx.Client,
    auth: Auth,
    job_id: str,
    project: str | None,
    *,
    summary_types: list[str] | None = None,
    skip_backfill: bool = False,
    initialize_missing_templates: bool = False,
) -> None:
    patch: dict[str, Any] = {}
    if summary_types:
        patch["summary_types"] = summary_types
    if skip_backfill:
        patch["skip_backfill"] = True
    if patch:
        r = client.patch(
            f"{api_base(auth)}/v1/ingestion/jobs/{job_id}",
            json=patch,
            headers=sdk_headers(auth, project),
        )
        r.raise_for_status()
        if summary_types:
            print(f"  Summary types set: {', '.join(summary_types)}")
        if skip_backfill:
            print("  View backfill will be skipped.")

    confirm_body: dict[str, Any] = {}
    if initialize_missing_templates:
        confirm_body["initialize_missing_templates"] = True
    r = client.post(
        f"{api_base(auth)}/v1/ingestion/jobs/{job_id}/confirm",
        json=confirm_body,
        headers=sdk_headers(auth, project),
    )
    r.raise_for_status()


def _cancel_job(client: httpx.Client, auth: Auth, job_id: str, project: str | None) -> None:
    r = client.post(
        f"{api_base(auth)}/v1/ingestion/jobs/{job_id}/cancel",
        headers=sdk_headers(auth, project),
    )
    r.raise_for_status()


def _handle_awaiting_confirmation(
    auth: Auth,
    job_id: str,
    job: dict[str, Any],
    args: Any | None,
    project: str | None,
    *,
    watch_after: bool = False,
) -> CommandResult:
    """Resolve an AWAITING_CONFIRMATION job — interactively or via flags. Mutating; not used by status."""
    if not output.json_mode():
        _print_job_detail(job)

    if not _job_has_missing_template_slots(job):
        if not output.json_mode():
            _print_awaiting_confirmation_hints(job_id)
        return CommandResult({"job": job})

    init_templates = bool(getattr(args, "init_templates", False)) if args is not None else False
    no_backfill = bool(getattr(args, "no_backfill", False)) if args is not None else False
    summary_types = getattr(args, "summary_types", None) if args is not None else None

    with http.client() as client:
        if init_templates:
            print("\n  Initializing missing templates and confirming…")
            _confirm_job(client, auth, job_id, project, summary_types=summary_types, initialize_missing_templates=True)
            print(f"  Job {job_id} confirmed — Phase 2 starting.")
            return _watch_job(auth, job_id, args, project=project) if watch_after else CommandResult({"job_id": job_id})

        if no_backfill:
            _confirm_job(client, auth, job_id, project, summary_types=summary_types, skip_backfill=True)
            print(f"  Job {job_id} confirmed — Phase 2 starting (views skipped).")
            return _watch_job(auth, job_id, args, project=project) if watch_after else CommandResult({"job_id": job_id})

        if not sys.stdin.isatty() or output.json_mode():
            if not output.json_mode():
                _print_missing_template_slot_summary(job)
                _print_awaiting_confirmation_hints(job_id)
            return CommandResult({"job": job})

        _print_missing_template_slot_summary(job)
        choice = _prompt_missing_template_action()
        if choice == "cancel":
            _cancel_job(client, auth, job_id, project)
            print(f"  Job {job_id} cancelled.")
            return CommandResult({"job_id": job_id, "cancelled": True})
        if choice == "init":
            print("\n  Initializing missing templates and confirming…")
            _confirm_job(client, auth, job_id, project, summary_types=summary_types, initialize_missing_templates=True)
        elif choice == "skip":
            _confirm_job(client, auth, job_id, project, summary_types=summary_types, skip_backfill=True)
        else:
            _confirm_job(client, auth, job_id, project, summary_types=summary_types)

        print(f"  Job {job_id} confirmed — Phase 2 starting.")
        return _watch_job(auth, job_id, args, project=project) if watch_after else CommandResult({"job_id": job_id})


def cmd_upload(args: Any) -> CommandResult:
    """Upload a JSONL file and create an ingestion job."""
    import pathlib
    import uuid

    path = pathlib.Path(args.file)
    if not path.exists():
        raise CliError(f"File not found: {path}", code="FILE_NOT_FOUND", exit_code=4)
    if path.suffix != ".jsonl":
        raise CliError("File must have a .jsonl extension.", code="INVALID_FILE", exit_code=5)

    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)
    idem_key = args.idempotency_key or f"cli-{uuid.uuid4().hex[:12]}"
    require_confirm = not args.no_confirm

    output.info(f"Uploading {path.name} ({path.stat().st_size / 1024:.1f} KB)…")

    with http.client() as client:
        r = client.post(f"{api_base(auth)}/v1/ingestion/upload-url", headers=sdk_headers(auth, project))
        r.raise_for_status()
        url_data = r.json()
        upload_url = url_data["upload_url"]
        s3_key = url_data["s3_key"]
        max_bytes = url_data.get("max_bytes", 100 * 1024 * 1024)

        if path.stat().st_size > max_bytes:
            raise CliError(
                f"File ({path.stat().st_size / 1024 / 1024:.1f} MB) exceeds org limit "
                f"({max_bytes / 1024 / 1024:.0f} MB).",
                code="FILE_TOO_LARGE",
                exit_code=5,
            )

        output.info("  Uploading to S3…")
        with open(path, "rb") as f:
            s3r = httpx.put(upload_url, content=f.read(), timeout=120)
        if not s3r.is_success:
            raise CliError(f"S3 upload failed ({s3r.status_code}).", code="NETWORK_ERROR", exit_code=7)

        output.info("  Creating ingestion job…")
        body: dict[str, Any] = {
            "s3_key": s3_key,
            "idempotency_key": idem_key,
            "require_confirmation": require_confirm,
        }
        if args.summary_types:
            body["summary_types"] = args.summary_types
        if getattr(args, "no_backfill", False):
            body["skip_backfill"] = True
        r = client.post(f"{api_base(auth)}/v1/ingestion/jobs", json=body, headers=sdk_headers(auth, project))
        r.raise_for_status()
        job = r.json()
        job_id = job["job_id"]

    if not output.json_mode():
        print(f"\n  Job created: {job_id}")
        print(f"  Idempotency key: {idem_key}")
        if require_confirm:
            print(f"\n  The job will pause at AWAITING_CONFIRMATION for review.\n  Run:  olira ingest confirm {job_id}")
        else:
            print("\n  Job will run to completion without confirmation (--no-confirm).")

    if args.watch:
        return _watch_job(auth, job_id, args, project=project, timeout=getattr(args, "timeout", None))

    return CommandResult({"job_id": job_id, "idempotency_key": idem_key, "require_confirmation": require_confirm})


def cmd_list(args: Any) -> CommandResult:
    """List ingestion jobs for the org."""
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)
    page = getattr(args, "page", 1)
    page_size = getattr(args, "page_size", 10)
    status_filter = getattr(args, "status", None)

    with http.client() as client:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if status_filter:
            params["status"] = status_filter
        r = client.get(f"{api_base(auth)}/v1/ingestion/jobs", params=params, headers=sdk_headers(auth, project))
        r.raise_for_status()
        data = r.json()

    jobs = data.get("jobs") or []
    total = data.get("total", len(jobs))
    pages = max(1, -(-total // page_size))

    if not output.json_mode():
        if not jobs:
            msg = "No ingestion jobs found."
            if status_filter:
                msg = f"No {status_filter} jobs found."
            print(msg)
        else:
            print(f"\n  {'JOB ID':<26} {'STATUS':<28} {'PATIENTS':<14} {'LOGS':<14} {'ERRORS':<10} {'CREATED'}")
            print("  " + "-" * 104)
            for j in jobs:
                _print_job_row(j)
            print(f"\n  Page {page}/{pages} · {total} total job(s)")
            if page < pages:
                print(f"  Next page: olira ingest list --page {page + 1}")

    return CommandResult({"jobs": jobs, "total": total, "page": page, "pages": pages})


def cmd_status(args: Any) -> CommandResult:
    """Show status for a single job. Strictly read-only — never prompts, never mutates."""
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    if args.watch:
        return _watch_job(
            auth, args.job_id, args, project=project, timeout=getattr(args, "timeout", None), read_only=True
        )

    with http.client() as client:
        job = _fetch_job(client, auth, args.job_id, project)

    if not output.json_mode():
        _print_job_detail(job)
        if job.get("status") == "awaiting_confirmation":
            _render_awaiting_confirmation(job, args.job_id)

    return CommandResult({"job": job})


def cmd_confirm(args: Any) -> CommandResult:
    """Confirm a job at AWAITING_CONFIRMATION to start Phase 2."""
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        job = _fetch_job(client, auth, args.job_id, project)

    if job.get("status") == "awaiting_confirmation" and _job_has_missing_template_slots(job):
        has_flag = getattr(args, "init_templates", False) or getattr(args, "no_backfill", False)
        if not has_flag:
            if sys.stdin.isatty() and not output.json_mode():
                return _handle_awaiting_confirmation(auth, args.job_id, job, args, project, watch_after=args.watch)
            if not output.json_mode():
                _print_missing_template_slot_summary(job)
                _print_awaiting_confirmation_hints(args.job_id)
            raise StateError(
                "Job is missing view template slots and cannot be confirmed non-interactively.",
                code="CONFIRMATION_REQUIRED",
                remediation="Re-run with --init-templates or --no-backfill.",
                details={"job": job},
            )

    with http.client() as client:
        _confirm_job(
            client,
            auth,
            args.job_id,
            project,
            summary_types=args.summary_types,
            skip_backfill=getattr(args, "no_backfill", False),
            initialize_missing_templates=getattr(args, "init_templates", False),
        )

    if not output.json_mode():
        print(f"  Job {args.job_id} confirmed — Phase 2 starting.")
    if args.watch:
        return _watch_job(auth, args.job_id, args, project=project, timeout=getattr(args, "timeout", None))
    return CommandResult({"job_id": args.job_id, "confirmed": True})


def cmd_cancel(args: Any) -> CommandResult:
    """Cancel an ingestion job."""
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    if not args.yes:
        require_tty("Cancelling a job", "--yes")
        confirm = input(f"Cancel job {args.job_id}? [y/N]: ").strip().lower()
        if confirm != "y":
            if not output.json_mode():
                print("Cancelled.")
            return CommandResult({"job_id": args.job_id, "cancelled": False})

    with http.client() as client:
        r = client.post(f"{api_base(auth)}/v1/ingestion/jobs/{args.job_id}/cancel", headers=sdk_headers(auth, project))
        r.raise_for_status()

    if not output.json_mode():
        print(f"  Job {args.job_id} cancellation requested.")
    return CommandResult({"job_id": args.job_id, "cancelled": True})


def cmd_retry_backfill(args: Any) -> CommandResult:
    """Retry view backfill on a COMPLETED_WITH_ERRORS job."""
    auth = resolve_auth("sdk", getattr(args, "api_key", None))
    project = resolve_project(args)

    with http.client() as client:
        r = client.post(
            f"{api_base(auth)}/v1/ingestion/jobs/{args.job_id}/retry-backfill", headers=sdk_headers(auth, project)
        )
        r.raise_for_status()

    if not output.json_mode():
        print(f"  Job {args.job_id} backfill retry started.")
    if args.watch:
        return _watch_job(auth, args.job_id, args, project=project, timeout=getattr(args, "timeout", None))
    return CommandResult({"job_id": args.job_id, "retry_started": True})


def _emit_progress(job: dict[str, Any], event: str) -> None:
    if output.json_mode():
        output.emit_event(
            {
                "event": event,
                "job_id": job.get("job_id"),
                "status": job.get("status"),
                "stage": job.get("stage"),
                "progress_pct": job.get("progress_pct"),
                "patients_processed": job.get("patients_processed"),
                "patients_total": job.get("patients_total"),
                "logs_processed": job.get("logs_processed"),
                "logs_total": job.get("logs_total"),
            }
        )
        return
    if event == "heartbeat":
        print(f"  … still {_fmt_status(job.get('status', ''))} — {job.get('progress_pct', 0.0):.0f}%")
        return
    bar = _progress_bar(job.get("progress_pct", 0.0))
    pts_done = job.get("patients_processed", 0)
    pts_tot = job.get("patients_total", 0)
    logs_done = job.get("logs_processed", 0)
    logs_tot = job.get("logs_total", 0)
    eta = f"  ETA ~{job['estimated_seconds_remaining']}s" if job.get("estimated_seconds_remaining") else ""
    print(
        f"  {_fmt_status(job.get('status', '')):<28} {bar}  {pts_done}/{pts_tot} patients  {logs_done}/{logs_tot} logs{eta}"
    )


def _fetch_job_with_retry(client: httpx.Client, auth: Auth, job_id: str, project: str | None) -> dict[str, Any]:
    """Fetch job status, retrying transient network/5xx errors with backoff.

    A blip mid-watch used to kill the whole watch immediately; now it takes
    up to ~14s of retries before giving up.
    """
    last_exc: Exception | None = None
    for backoff in (*_RETRY_BACKOFFS, None):
        try:
            return _fetch_job(client, auth, job_id, project)
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            last_exc = e
        except httpx.TransportError as e:
            last_exc = e
        if backoff is not None:
            output.warn(f"  Warning: transient error polling job status, retrying in {backoff:.0f}s…")
            time.sleep(backoff)
    assert last_exc is not None
    if isinstance(last_exc, httpx.HTTPStatusError):
        raise from_http_error(last_exc)
    raise CliError(str(last_exc), code="NETWORK_ERROR", exit_code=7)


def _watch_job(
    auth: Auth,
    job_id: str,
    args: Any | None = None,
    *,
    project: str | None = None,
    timeout: float | None = None,
    read_only: bool = False,
) -> CommandResult:
    """Poll a job until terminal, printing/emitting on stage change, progress jump, or heartbeat."""
    if not output.json_mode():
        print(f"\n  Watching job {job_id} (Ctrl-C to stop)…\n")
    last_stage = ""
    last_pct = -1.0
    last_emit = time.monotonic()
    start = time.monotonic()
    try:
        with http.client() as client:
            while True:
                job = _fetch_job_with_retry(client, auth, job_id, project)

                status = job.get("status", "")
                stage = job.get("stage", "")
                pct = job.get("progress_pct", 0.0)
                now = time.monotonic()

                if stage != last_stage or abs(pct - last_pct) >= 5.0:
                    last_stage, last_pct, last_emit = stage, pct, now
                    _emit_progress(job, "progress")
                elif now - last_emit >= _HEARTBEAT_SECONDS:
                    last_emit = now
                    _emit_progress(job, "heartbeat")

                if status == "awaiting_confirmation":
                    if read_only:
                        if not output.json_mode():
                            _print_job_detail(job)
                            _render_awaiting_confirmation(job, job_id)
                        return CommandResult({"job": job})
                    return _handle_awaiting_confirmation(auth, job_id, job, args, project, watch_after=False)

                if status in _TERMINAL:
                    if not output.json_mode():
                        _print_job_detail(job)
                    if status in {"completed", "completed_with_errors"}:
                        return CommandResult({"job": job})
                    raise StateError(
                        f"Job {job_id} ended as {status}.",
                        code="JOB_FAILED" if status == "failed" else "JOB_CANCELLED",
                        details={"job": job},
                    )

                if timeout is not None and now - start > timeout:
                    raise CliError(
                        f"Timed out after {timeout:.0f}s waiting for job {job_id} (still {status}).",
                        code="WATCH_TIMEOUT",
                        exit_code=8,
                        remediation=f"olira ingest status {job_id} --json --watch --timeout <seconds>",
                        details={"job": job},
                    )

                interval = 30.0 if status in _PHASE2 else 5.0
                time.sleep(interval)

    except KeyboardInterrupt:
        if not output.json_mode():
            print("\n  Watch stopped (job is still running).")
        raise


def _print_job_detail(job: dict[str, Any]) -> None:
    status = job.get("status", "")
    cancel_requested = job.get("cancel_requested", False)
    display_status = "Cancellation requested…" if cancel_requested and status in _ACTIVE else _fmt_status(status)
    print(f"\n  Job:    {job.get('job_id', '')}")
    print(f"  Status: {display_status}")
    print(f"  Stage:  {job.get('stage', '')}")
    print(f"  Progress: {_progress_bar(job.get('progress_pct', 0.0))}")
    print(f"  Patients: {job.get('patients_processed', 0)}/{job.get('patients_total', 0)}")
    print(
        f"  Logs:     {job.get('logs_processed', 0)}/{job.get('logs_total', 0)}"
        + (f"  ({job.get('logs_failed', 0)} failed)" if job.get("logs_failed") else "")
    )

    by_type = job.get("logs_by_event_type") or {}
    if by_type:
        print("  Log types:")
        for et, count in sorted(by_type.items(), key=lambda x: -x[1]):
            label = et.replace("_", " ").title()
            print(f"    {label:<36} {count}")

    if job.get("skip_backfill"):
        print("  Views:    skipped (--no-backfill)")
    else:
        summary_types = job.get("summary_types") or []
        if summary_types:
            print(f"  Views:    {', '.join(summary_types)}")
        else:
            print("  Views:    all active org templates")

    backfill_status = job.get("backfill_status")
    backfill_pct = job.get("backfill_progress_pct")
    if backfill_status:
        pct_str = f"  {backfill_pct:.0f}%" if backfill_pct is not None else ""
        print(f"  Backfill: {_fmt_status(backfill_status)}{pct_str}")

    patient_log_counts = job.get("patient_log_counts") or {}
    replay_statuses = job.get("patient_replay_statuses") or {}
    if patient_log_counts:
        print(f"\n  Patients ({len(patient_log_counts)}):")
        for pid, count in sorted(patient_log_counts.items(), key=lambda x: -x[1]):
            replay = replay_statuses.get(pid, "")
            replay_str = f"  [{replay.upper()}]" if replay and replay != "pending" else ""
            print(f"    {pid}  {count:>5} logs{replay_str}")

    all_errors = job.get("error_summary") or []
    warnings, errors = _partition_error_summary(all_errors)
    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"    ⚠  {w.get('message', '')}")
        if len(warnings) > 10:
            print(f"    … and {len(warnings) - 10} more")
    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:10]:
            line = f"L{e.get('line', 0)}" if e.get("line") else "   "
            print(f"    {line:>5}  {e.get('message', '')}")
        if len(errors) > 10:
            print(f"    … and {len(errors) - 10} more")
