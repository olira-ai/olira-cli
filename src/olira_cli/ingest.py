"""olira ingest — historical bulk data ingestion commands.

Subcommands:
  upload <file>        Upload a JSONL file and create an ingestion job
  list                 List ingestion jobs for the org
  status <job_id>      Show (and optionally tail) a job's status
  confirm <job_id>     Confirm a job at AWAITING_CONFIRMATION
  cancel <job_id>      Cancel a job
"""

from __future__ import annotations

import sys
import time
from typing import Any

import httpx

from olira_cli.credentials import load_credentials

# ── helpers ────────────────────────────────────────────────────────────────────

_TERMINAL = {"completed", "completed_with_errors", "cancelled", "failed"}
_ACTIVE = {"queued", "validating", "inserting_patients", "inserting_logs", "confirmed", "replaying", "backfilling"}
_PHASE2 = {"confirmed", "replaying", "backfilling"}  # slow-poll territory

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


def _require_creds() -> dict[str, Any] | None:
    import os

    api_key = os.environ.get("OLIRA_API_KEY")
    if api_key:
        creds = load_credentials()
        api_server = (creds or {}).get("api_server", "https://api.prod.olira.ai")
        return {"access_token": api_key, "api_server": api_server}
    creds = load_credentials()
    if not creds or not creds.get("access_token"):
        print(
            "Not logged in. Run: olira login  —  or set OLIRA_API_KEY=olira_... for SDK operations.",
            file=sys.stderr,
        )
        return None
    return creds


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _api(creds: dict[str, Any]) -> str:
    return creds["api_server"].rstrip("/")


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


def _fetch_job(client: httpx.Client, api_base: str, token: str, job_id: str) -> dict[str, Any]:
    r = client.get(f"{api_base}/v1/ingestion/jobs/{job_id}", headers=_headers(token), timeout=30)
    r.raise_for_status()
    return r.json()


# ── upload ─────────────────────────────────────────────────────────────────────


def cmd_upload(args: Any) -> int:
    """Upload a JSONL file and create an ingestion job."""
    import pathlib
    import uuid

    path = pathlib.Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1
    if path.suffix != ".jsonl":
        print("Error: file must have a .jsonl extension.", file=sys.stderr)
        return 1

    creds = _require_creds()
    if not creds:
        return 1

    api_base = _api(creds)
    token = creds["access_token"]
    idem_key = args.idempotency_key or f"cli-{uuid.uuid4().hex[:12]}"
    require_confirm = not args.no_confirm

    print(f"Uploading {path.name} ({path.stat().st_size / 1024:.1f} KB)…")

    try:
        with httpx.Client(timeout=30) as client:
            # 1. Get presigned URL
            r = client.post(
                f"{api_base}/v1/ingestion/upload-url",
                headers=_headers(token),
            )
            r.raise_for_status()
            url_data = r.json()
            upload_url = url_data["upload_url"]
            s3_key = url_data["s3_key"]
            max_bytes = url_data.get("max_bytes", 100 * 1024 * 1024)

            if path.stat().st_size > max_bytes:
                print(
                    f"Error: file ({path.stat().st_size / 1024 / 1024:.1f} MB) "
                    f"exceeds org limit ({max_bytes / 1024 / 1024:.0f} MB).",
                    file=sys.stderr,
                )
                return 1

            # 2. PUT to S3
            print("  Uploading to S3…")
            with open(path, "rb") as f:
                s3r = httpx.put(upload_url, content=f.read(), timeout=120)
            if not s3r.is_success:
                print(f"Error: S3 upload failed ({s3r.status_code}).", file=sys.stderr)
                return 1

            # 3. Create job
            print("  Creating ingestion job…")
            body: dict[str, Any] = {
                "s3_key": s3_key,
                "idempotency_key": idem_key,
                "require_confirmation": require_confirm,
            }
            if args.summary_types:
                body["summary_types"] = args.summary_types
            if getattr(args, "no_backfill", False):
                body["skip_backfill"] = True
            r = client.post(
                f"{api_base}/v1/ingestion/jobs",
                json=body,
                headers=_headers(token),
            )
            r.raise_for_status()
            job = r.json()
            job_id = job["job_id"]

        print(f"\n  Job created: {job_id}")
        print(f"  Idempotency key: {idem_key}")
        if require_confirm:
            print(f"\n  The job will pause at AWAITING_CONFIRMATION for review.\n  Run:  olira ingest confirm {job_id}")
        else:
            print("\n  Job will run to completion without confirmation (--no-confirm).")

        if args.watch:
            return _watch_job(api_base, token, job_id)

        return 0

    except httpx.HTTPStatusError as e:
        _print_http_error(e)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ── list ───────────────────────────────────────────────────────────────────────


def cmd_list(args: Any) -> int:
    """List ingestion jobs for the org."""
    creds = _require_creds()
    if not creds:
        return 1

    api_base = _api(creds)
    token = creds["access_token"]
    page = getattr(args, "page", 1)
    page_size = getattr(args, "page_size", 10)
    status_filter = getattr(args, "status", None)

    try:
        with httpx.Client(timeout=30) as client:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if status_filter:
                params["status"] = status_filter
            r = client.get(
                f"{api_base}/v1/ingestion/jobs",
                params=params,
                headers=_headers(token),
            )
            r.raise_for_status()
            data = r.json()

        jobs = data.get("jobs") or []
        total = data.get("total", len(jobs))

        if not jobs:
            msg = "No ingestion jobs found."
            if status_filter:
                msg = f"No {status_filter} jobs found."
            print(msg)
            return 0

        print(f"\n  {'JOB ID':<26} {'STATUS':<28} {'PATIENTS':<14} {'LOGS':<14} {'ERRORS':<10} {'CREATED'}")
        print("  " + "-" * 104)
        for j in jobs:
            _print_job_row(j)

        pages = max(1, -(-total // page_size))  # ceiling division
        print(f"\n  Page {page}/{pages} · {total} total job(s)")
        if page < pages:
            print(f"  Next page: olira ingest list --page {page + 1}")
        return 0

    except httpx.HTTPStatusError as e:
        _print_http_error(e)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ── status ─────────────────────────────────────────────────────────────────────


def cmd_status(args: Any) -> int:
    """Show status for a single job, optionally tailing progress."""
    creds = _require_creds()
    if not creds:
        return 1

    api_base = _api(creds)
    token = creds["access_token"]

    if args.watch:
        return _watch_job(api_base, token, args.job_id)

    try:
        with httpx.Client(timeout=30) as client:
            job = _fetch_job(client, api_base, token, args.job_id)
        _print_job_detail(job)
        return 0
    except httpx.HTTPStatusError as e:
        _print_http_error(e)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ── confirm ────────────────────────────────────────────────────────────────────


def cmd_confirm(args: Any) -> int:
    """Confirm a job at AWAITING_CONFIRMATION to start Phase 2."""
    creds = _require_creds()
    if not creds:
        return 1

    api_base = _api(creds)
    token = creds["access_token"]

    try:
        with httpx.Client(timeout=30) as client:
            # Optionally update summary_types / skip_backfill before confirming
            patch: dict[str, Any] = {}
            if args.summary_types:
                patch["summary_types"] = args.summary_types
            if getattr(args, "no_backfill", False):
                patch["skip_backfill"] = True
            if patch:
                r = client.patch(
                    f"{api_base}/v1/ingestion/jobs/{args.job_id}",
                    json=patch,
                    headers=_headers(token),
                )
                r.raise_for_status()
                if args.summary_types:
                    print(f"  Summary types set: {', '.join(args.summary_types)}")
                if patch.get("skip_backfill"):
                    print("  View backfill will be skipped.")

            r = client.post(
                f"{api_base}/v1/ingestion/jobs/{args.job_id}/confirm",
                headers=_headers(token),
            )
            r.raise_for_status()

        print(f"  Job {args.job_id} confirmed — Phase 2 starting.")
        if args.watch:
            return _watch_job(api_base, token, args.job_id)
        return 0

    except httpx.HTTPStatusError as e:
        _print_http_error(e)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ── cancel ─────────────────────────────────────────────────────────────────────


def cmd_cancel(args: Any) -> int:
    """Cancel an ingestion job."""
    creds = _require_creds()
    if not creds:
        return 1

    api_base = _api(creds)
    token = creds["access_token"]

    if not args.yes:
        try:
            confirm = input(f"Cancel job {args.job_id}? [y/N]: ").strip().lower()
        except EOFError:
            return 1
        if confirm != "y":
            print("Cancelled.")
            return 0

    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{api_base}/v1/ingestion/jobs/{args.job_id}/cancel",
                headers=_headers(token),
            )
            r.raise_for_status()
        print(f"  Job {args.job_id} cancellation requested.")
        return 0
    except httpx.HTTPStatusError as e:
        _print_http_error(e)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ── retry-backfill ─────────────────────────────────────────────────────────────


def cmd_retry_backfill(args: Any) -> int:
    """Retry view backfill on a COMPLETED_WITH_ERRORS job."""
    creds = _require_creds()
    if not creds:
        return 1

    api_base = _api(creds)
    token = creds["access_token"]

    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{api_base}/v1/ingestion/jobs/{args.job_id}/retry-backfill",
                headers=_headers(token),
            )
            r.raise_for_status()

        print(f"  Job {args.job_id} backfill retry started.")
        if args.watch:
            return _watch_job(api_base, token, args.job_id)
        return 0

    except httpx.HTTPStatusError as e:
        _print_http_error(e)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ── shared: watch ──────────────────────────────────────────────────────────────


def _watch_job(api_base: str, token: str, job_id: str) -> int:
    """Poll a job until terminal, printing a line on stage change or 5% progress jump."""
    print(f"\n  Watching job {job_id} (Ctrl-C to stop)…\n")
    last_stage = ""
    last_pct = -1.0
    try:
        with httpx.Client(timeout=30) as client:
            while True:
                try:
                    job = _fetch_job(client, api_base, token, job_id)
                except httpx.HTTPStatusError as e:
                    _print_http_error(e)
                    return 1

                status = job.get("status", "")
                stage = job.get("stage", "")
                pct = job.get("progress_pct", 0.0)

                if stage != last_stage or abs(pct - last_pct) >= 5.0:
                    last_stage = stage
                    last_pct = pct
                    bar = _progress_bar(pct)
                    pts_done = job.get("patients_processed", 0)
                    pts_tot = job.get("patients_total", 0)
                    logs_done = job.get("logs_processed", 0)
                    logs_tot = job.get("logs_total", 0)
                    eta = (
                        f"  ETA ~{job['estimated_seconds_remaining']}s"
                        if job.get("estimated_seconds_remaining")
                        else ""
                    )
                    print(
                        f"  {_fmt_status(status):<28} {bar}  "
                        f"{pts_done}/{pts_tot} patients  {logs_done}/{logs_tot} logs{eta}"
                    )

                if status == "awaiting_confirmation":
                    print(
                        "\n  ⚑ Job is awaiting your confirmation.\n"
                        f"  Review patients, logs and views before proceeding:\n"
                        f"    olira ingest status {job_id}\n"
                        f"\n  To confirm (starts graph replay + view backfill):\n"
                        f"    olira ingest confirm {job_id}\n"
                        f"  To confirm with specific views:\n"
                        f"    olira ingest confirm {job_id} --summary-types <type1> <type2>\n"
                        f"  To cancel:\n"
                        f"    olira ingest cancel {job_id}"
                    )
                    return 0

                if status in _TERMINAL:
                    _print_job_detail(job)
                    return 0 if status in {"completed", "completed_with_errors"} else 1

                # Phase 2 (replay + backfill) runs sequentially per patient and can take
                # hours — poll slowly to avoid unnecessary requests.
                interval = 30.0 if status in _PHASE2 else 5.0
                time.sleep(interval)

    except KeyboardInterrupt:
        print("\n  Watch stopped (job is still running).")
        return 0


# ── shared: detail ─────────────────────────────────────────────────────────────


def _print_job_detail(job: dict[str, Any]) -> None:
    status = job.get("status", "")
    print(f"\n  Job:    {job.get('job_id', '')}")
    print(f"  Status: {_fmt_status(status)}")
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

    errors = job.get("error_summary") or []
    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:10]:
            line = f"L{e.get('line', 0)}" if e.get("line") else "   "
            print(f"    {line:>5}  {e.get('message', '')}")
        if len(errors) > 10:
            print(f"    … and {len(errors) - 10} more")


def _print_http_error(e: httpx.HTTPStatusError) -> None:
    try:
        body = e.response.json()
        msg = body.get("detail") or body.get("message") or str(e)
    except Exception:
        msg = str(e)
    print(f"Error ({e.response.status_code}): {msg}", file=sys.stderr)
