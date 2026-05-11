#!/usr/bin/env python3
"""
CLI Historical Data Ingestion E2E test.

Exercises `olira validate`, `olira ingest upload/list/status/confirm/cancel`
as a real user would, by invoking the CLI as a subprocess.

Sections:
  A  Setup              — write ~/.olira/credentials.json; build test JSONL
  B  validate (clean)   — olira validate <file> → exit 0, summary printed
  C  validate (errors)  — anchor rule, bad event type, PII patient_id, missing/malformed timestamp → exit 1
  D  upload + watch     — olira ingest upload --watch; pauses at AWAITING_CONFIRMATION
  E  ingest list        — job appears in olira ingest list output
  F  ingest status      — olira ingest status <job_id> prints detail
  G  confirm + watch    — olira ingest confirm --watch → COMPLETED or COMPLETED_WITH_ERRORS; summary_types verified
  H  upload + cancel    — upload a second job; olira ingest cancel --yes → CANCELLED
  I  no-confirm path    — olira ingest upload --no-confirm runs straight to terminal
  J  validate --check-org — cross-check patient IDs that exist in the org (ext_id match)
  K  scope enforcement  — run with wrong-scope key credential → 403 error message printed
  L  retry-backfill     — olira ingest retry-backfill on COMPLETED_WITH_ERRORS (skipped if G completes cleanly)

Cleanup always runs (try/finally). Created patients are deleted via the API.

Usage:
  python cli_ingest_e2e.py
  python cli_ingest_e2e.py /path/to/config.json

Config file (cli_ingest.config.json):
  {
    "api_key":    "<sdk:historical-ingest key>",
    "base_api":   "http://localhost:8080/app-api",
    "console_token": "<Auth0 JWT — for patient cleanup>",
    "olira_bin":  "olira"       (optional — default searches PATH / .venv)
  }
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from pathlib import Path

import httpx

# ── formatting ────────────────────────────────────────────────────────────────

PASS = "✔"
FAIL = "✘"
BOLD = "\033[1m"
RED   = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM   = "\033[2m"
RESET = "\033[0m"

failures = 0


def _pass(msg: str) -> None:
    print(f"  {GREEN}{PASS}{RESET} {msg}")


def _fail(msg: str) -> None:
    global failures
    failures += 1
    print(f"  {RED}{FAIL}{RESET} {msg}")


def _info(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


def _skip(msg: str) -> None:
    print(f"  {YELLOW}⊘{RESET} {msg}")


def _section(title: str) -> None:
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'═' * 60}{RESET}")


# ── config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = (
    Path(sys.argv[1]) if len(sys.argv) > 1
    else SCRIPT_DIR / "cli_ingest.config.json"
)

if not CONFIG_FILE.exists():
    print(f"{RED}{FAIL} Config file not found: {CONFIG_FILE}{RESET}")
    example = SCRIPT_DIR / "cli_ingest.config.example.json"
    print(f"  cp {example} {CONFIG_FILE}")
    sys.exit(1)

with open(CONFIG_FILE) as f:
    cfg = json.load(f)

API_KEY: str      = cfg.get("api_key", "")
BASE_API: str     = cfg.get("base_api", "http://localhost:8080/app-api")
CONSOLE_TOKEN: str = cfg.get("console_token", "")
OLIRA_BIN: str    = cfg.get("olira_bin", "")

if not API_KEY or API_KEY.startswith("<"):
    print(f"{RED}{FAIL} api_key looks like a placeholder — fill in {CONFIG_FILE}{RESET}")
    sys.exit(1)

# Resolve binary: config override > .venv/bin/olira > PATH
if not OLIRA_BIN:
    venv_bin = Path(__file__).parents[2] / ".venv" / "bin" / "olira"
    if venv_bin.exists():
        OLIRA_BIN = str(venv_bin)
    else:
        OLIRA_BIN = shutil.which("olira") or "olira"

# Per-run suffix so idempotency keys never collide across runs
RUN_ID = uuid.uuid4().hex[:8]

# Track patients created via the API for cleanup
CREATED_PATIENT_IDS: list[str] = []

# ── credentials file management ───────────────────────────────────────────────

_ORIG_CREDS_BACKUP: dict | None = None
_CREDS_PATH = Path.home() / ".olira" / "credentials.json"


def _backup_credentials() -> None:
    global _ORIG_CREDS_BACKUP
    if _CREDS_PATH.exists():
        with open(_CREDS_PATH) as f:
            _ORIG_CREDS_BACKUP = json.load(f)


def _write_credentials(api_key: str) -> None:
    """Write a credentials file so the CLI picks up the API key as access_token.

    NOTE: this bypasses olira login entirely — the test always has the right SDK key
    in credentials. This means the test does NOT cover the real user flow of
    'olira login → Auth0 JWT stored → olira ingest upload → 401'.
    That path requires OLIRA_API_KEY to be set by the user (see ingest.py _require_creds).
    """
    _CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    creds = {
        "access_token": api_key,
        "api_server": BASE_API,
        "mcp_server": BASE_API,
        "env": "dev",
    }
    with open(_CREDS_PATH, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(_CREDS_PATH, 0o600)


def _restore_credentials() -> None:
    if _ORIG_CREDS_BACKUP is not None:
        with open(_CREDS_PATH, "w") as f:
            json.dump(_ORIG_CREDS_BACKUP, f, indent=2)
        os.chmod(_CREDS_PATH, 0o600)
    elif _CREDS_PATH.exists():
        _CREDS_PATH.unlink()


# ── CLI runner ────────────────────────────────────────────────────────────────

def _cli(*args: str, timeout: int = 60, input_text: str | None = None) -> subprocess.CompletedProcess:
    """Run `olira <args>` and return the CompletedProcess."""
    cmd = [OLIRA_BIN, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
    )


def _cli_out(*args: str, timeout: int = 60) -> tuple[int, str]:
    """Run CLI and return (exit_code, combined_stdout_stderr)."""
    r = _cli(*args, timeout=timeout)
    combined = (r.stdout + r.stderr).strip()
    return r.returncode, combined


# ── test JSONL ────────────────────────────────────────────────────────────────

def _write_test_jsonl(path: Path, run_id: str) -> None:
    lines = [
        {"type": "patient", "data": {
            "first_name": "CLI", "last_name": "AlphaE2E",
            "date_of_birth": "1980-01-01T00:00:00Z",
            "timezone": "America/New_York",
            "external_identifiers": [{"system": "cli-e2e", "value": f"CLI-ALPHA-{run_id}"}],
        }},
        {"type": "patient", "data": {
            "first_name": "CLI", "last_name": "BetaE2E",
            "date_of_birth": "1985-06-15T00:00:00Z",
            "timezone": "America/Chicago",
            "external_identifiers": [{"system": "cli-e2e", "value": f"CLI-BETA-{run_id}"}],
        }},
        {"type": "log", "data": {
            "event_type": "moods_report",
            "patient_id": f"CLI-ALPHA-{run_id}",
            "timestamp": "2025-03-01T08:00:00Z",
            "payload": {"moods": [{"mood": "calm", "intensity": 3}]},
            "idempotency_key": f"cli-e2e-alpha-mood-{run_id}",
        }},
        {"type": "log", "data": {
            "event_type": "vitals_measurement",
            "patient_id": f"CLI-ALPHA-{run_id}",
            "timestamp": "2025-03-02T10:00:00Z",
            "payload": {
                "measurements": {"heart_rate_bpm": 72, "systolic_bp_mmhg": 120, "diastolic_bp_mmhg": 80},
                "context": {"position": "sitting"},
                "source": "manual_entry",
                "collection_datetime": "2025-03-02T09:55:00Z",
            },
            "idempotency_key": f"cli-e2e-alpha-vitals-{run_id}",
        }},
        {"type": "log", "data": {
            "event_type": "moods_report",
            "patient_id": f"CLI-BETA-{run_id}",
            "timestamp": "2025-04-01T09:00:00Z",
            "payload": {"moods": [{"mood": "anxious", "intensity": 6}]},
            "idempotency_key": f"cli-e2e-beta-mood-{run_id}",
        }},
    ]
    with open(path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def _write_bad_jsonl(path: Path) -> None:
    """A JSONL file with deliberate errors for validate testing."""
    lines = [
        # good patient
        {"type": "patient", "data": {
            "first_name": "Good", "last_name": "Patient",
            "date_of_birth": "1990-01-01T00:00:00Z",
            "timezone": "UTC",
            "external_identifiers": [{"system": "test", "value": "GOOD-PAT"}],
        }},
        # bad: patient with no identifying fields (anchor rule violation)
        {"type": "patient", "data": {
            "timezone": "UTC",
        }},
        # bad: unknown event type
        {"type": "log", "data": {
            "event_type": "not_a_real_type",
            "patient_id": "GOOD-PAT",
            "timestamp": "2025-01-01T00:00:00Z",
        }},
        # bad: PII patient_id
        {"type": "log", "data": {
            "event_type": "moods_report",
            "patient_id": "john.doe@example.com",
            "timestamp": "2025-01-01T00:00:00Z",
        }},
        # bad: missing timestamp
        {"type": "log", "data": {
            "event_type": "moods_report",
            "patient_id": "GOOD-PAT",
        }},
        # bad: timestamp present but not valid ISO 8601 (month 13)
        {"type": "log", "data": {
            "event_type": "moods_report",
            "patient_id": "GOOD-PAT",
            "timestamp": "2025-13-01T00:00:00Z",
        }},
    ]
    with open(path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
        f.write("this is not json at all\n")


# ── poll helper ───────────────────────────────────────────────────────────────

_TERMINAL = {"completed", "completed_with_errors", "cancelled", "failed"}


def _poll_job_api(job_id: str, until: set[str], timeout_s: int = 180) -> dict:
    """Poll job status directly via the SDK API (not the CLI) for reliability."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = httpx.get(
            f"{BASE_API}/v1/ingestion/jobs/{job_id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=15,
        )
        r.raise_for_status()
        job = r.json()
        if job["status"] in until or job["status"] in _TERMINAL:
            return job
        time.sleep(3)
    raise TimeoutError(f"Job {job_id} did not reach {until} within {timeout_s}s")


def _extract_job_id(output: str) -> str | None:
    """Extract 'Job created: <id>' or 'Job: <id>' from CLI output."""
    for line in output.splitlines():
        for prefix in ("Job created:", "Job:", "job_id:"):
            if prefix.lower() in line.lower():
                parts = line.split()
                if parts:
                    candidate = parts[-1].strip(".,:")
                    if len(candidate) >= 20:
                        return candidate
    return None


# ── cleanup ───────────────────────────────────────────────────────────────────

def _cleanup() -> None:
    if not CONSOLE_TOKEN or not CREATED_PATIENT_IDS:
        return
    headers = {"Authorization": f"Bearer {CONSOLE_TOKEN}"}
    deleted = 0
    for pid in CREATED_PATIENT_IDS:
        try:
            r = httpx.delete(
                f"{BASE_API}/member/patients/{pid}",
                headers=headers,
                timeout=10,
            )
            if r.status_code in (200, 204, 404):
                deleted += 1
        except Exception:
            pass
    if deleted:
        _info(f"  Cleanup: deleted {deleted} patient(s)")


# ══════════════════════════════════════════════════════════════════════════════
# SECTIONS
# ══════════════════════════════════════════════════════════════════════════════

def section_a_setup(tmp_dir: Path) -> tuple[Path, Path]:
    _section("A · Setup — credentials + test JSONL files")

    _backup_credentials()
    _write_credentials(API_KEY)
    _pass(f"Credentials written to {_CREDS_PATH}")

    good_jsonl = tmp_dir / "good.jsonl"
    bad_jsonl  = tmp_dir / "bad.jsonl"
    _write_test_jsonl(good_jsonl, RUN_ID)
    _write_bad_jsonl(bad_jsonl)
    _pass(f"Test JSONL files written: {good_jsonl.name}, {bad_jsonl.name}")
    _pass(f"Run ID: {RUN_ID}")

    # Sanity: verify binary is reachable
    rc, out = _cli_out("--help")
    if rc == 0 and "ingest" in out:
        _pass(f"CLI binary found: {OLIRA_BIN}")
    else:
        _fail(f"CLI binary not reachable or missing 'ingest' command: {OLIRA_BIN}")

    return good_jsonl, bad_jsonl


def section_b_validate_clean(good_jsonl: Path) -> None:
    _section("B · olira validate (clean file) — exit 0, summary printed")
    try:
        rc, out = _cli_out("validate", str(good_jsonl))
        _info(out)
        if rc == 0:
            _pass("Exit code 0 — validation passed")
        else:
            _fail(f"Exit code {rc} — expected 0 for a clean file")

        if "Validation passed" in out:
            _pass("'Validation passed' message present")
        else:
            _fail("'Validation passed' message not found in output")

        if "patient" in out and "log" in out:
            _pass("Record counts (patient + log) present in output")
        else:
            _fail("Record counts not found in output")

        for et in ("Moods Report", "Vitals Measurement"):
            if et in out:
                _pass(f"Event type '{et}' listed in output")
            else:
                _fail(f"Event type '{et}' missing from output")

    except Exception as e:
        _fail(f"Section B raised: {e}")


def section_c_validate_errors(bad_jsonl: Path) -> None:
    _section("C · olira validate (bad file) — exit 1, errors listed")
    try:
        rc, out = _cli_out("validate", str(bad_jsonl))
        _info(out)
        if rc == 1:
            _pass("Exit code 1 — validation correctly failed")
        else:
            _fail(f"Exit code {rc} — expected 1 for a file with errors")

        checks = [
            ("patient anchor rule", "identifying" in out.lower() or "anchor" in out.lower()),
            ("unknown event_type", "not_a_real_type" in out),
            ("PII email detection", "email" in out.lower() or "john.doe" in out),
            ("missing timestamp", "missing 'timestamp'" in out or "missing timestamp" in out.lower()),
            ("invalid timestamp format", "not a valid ISO 8601" in out or "ISO 8601" in out),
            ("invalid JSON line", "invalid JSON" in out or "JSON" in out),
        ]
        for label, ok in checks:
            if ok:
                _pass(f"Error detected: {label}")
            else:
                _fail(f"Error not detected: {label}")

        if "Validation failed" in out:
            _pass("'Validation failed' summary present")
        else:
            _fail("'Validation failed' summary not found")

    except Exception as e:
        _fail(f"Section C raised: {e}")


def section_d_upload_watch(good_jsonl: Path) -> str | None:
    _section("D · olira ingest upload --watch — pauses at AWAITING_CONFIRMATION")
    job_id: str | None = None
    try:
        idem_key = f"cli-e2e-d-{RUN_ID}"
        # --watch will block until AWAITING_CONFIRMATION (or terminal).
        # We set a generous timeout since Stage 1-3 can take 30-60s.
        r = _cli(
            "ingest", "upload", str(good_jsonl),
            "--idempotency-key", idem_key,
            "--watch",
            timeout=180,
        )
        out = (r.stdout + r.stderr).strip()
        _info(out[:800])

        if r.returncode == 0:
            _pass("Upload + watch exited 0")
        else:
            _fail(f"Upload + watch exited {r.returncode}")

        job_id = _extract_job_id(out)
        if job_id:
            _pass(f"Job ID extracted: {job_id[-12:]}")
        else:
            _fail("Could not extract job ID from output")
            return None

        if "awaiting" in out.lower() or "AWAITING" in out:
            _pass("Output mentions AWAITING_CONFIRMATION")
        else:
            _fail("AWAITING_CONFIRMATION message not found in output")

        if "olira ingest confirm" in out:
            _pass("Confirm hint printed")
        else:
            _fail("Confirm hint not printed")

        # Verify via API that the job is actually at AWAITING_CONFIRMATION
        job = _poll_job_api(job_id, {"awaiting_confirmation"}, timeout_s=10)
        if job["status"] == "awaiting_confirmation":
            _pass("API confirms job is at awaiting_confirmation")
        else:
            _fail(f"API reports status={job['status']!r} (expected awaiting_confirmation)")

        # Collect patient IDs for cleanup
        for pid in job.get("patient_log_counts", {}).keys():
            if pid not in CREATED_PATIENT_IDS:
                CREATED_PATIENT_IDS.append(pid)

    except subprocess.TimeoutExpired:
        _fail("Upload + watch timed out (180s)")
    except Exception as e:
        _fail(f"Section D raised: {e}")
        traceback.print_exc()

    return job_id


def section_e_list(job_id: str | None) -> None:
    _section("E · olira ingest list — job appears in output")
    try:
        rc, out = _cli_out("ingest", "list")
        _info(out)
        if rc == 0:
            _pass("olira ingest list exited 0")
        else:
            _fail(f"olira ingest list exited {rc}")

        if job_id and job_id[-12:] in out:
            _pass(f"Job {job_id[-12:]} appears in list output")
        elif job_id:
            _fail(f"Job {job_id[-12:]} not found in list output")
        else:
            _skip("No job ID to check")

        for label in ("STATUS", "PATIENTS", "LOGS"):
            if label in out:
                _pass(f"Column header '{label}' present")
            else:
                _fail(f"Column header '{label}' missing")

    except Exception as e:
        _fail(f"Section E raised: {e}")


def section_f_status(job_id: str | None) -> None:
    _section("F · olira ingest status — prints job detail")
    if not job_id:
        _skip("No job ID — skipping")
        return
    try:
        rc, out = _cli_out("ingest", "status", job_id)
        _info(out)
        if rc == 0:
            _pass("olira ingest status exited 0")
        else:
            _fail(f"olira ingest status exited {rc}")

        for label in ("Job:", "Status:", "Patients:", "Logs:"):
            if label in out:
                _pass(f"Detail field '{label}' present")
            else:
                _fail(f"Detail field '{label}' missing")

        if "moods" in out.lower() or "vitals" in out.lower():
            _pass("Event type breakdown present in status output")
        else:
            _fail("Event type breakdown not found in status output")

    except Exception as e:
        _fail(f"Section F raised: {e}")


def section_g_confirm_watch(job_id: str | None) -> dict | None:
    _section("G · olira ingest confirm --watch → COMPLETED or COMPLETED_WITH_ERRORS")
    if not job_id:
        _skip("No job ID — skipping")
        return None
    try:
        r = _cli(
            "ingest", "confirm", job_id,
            "--summary-types", "emotional_state_snapshot",
            "--watch",
            timeout=300,
        )
        out = (r.stdout + r.stderr).strip()
        _info(out[:800])

        if r.returncode == 0:
            _pass("confirm --watch exited 0")
        else:
            _fail(f"confirm --watch exited {r.returncode}")

        # Verify via API
        job = _poll_job_api(job_id, _TERMINAL, timeout_s=10)
        if job["status"] in ("completed", "completed_with_errors"):
            _pass(f"API confirms job terminal: {job['status']}")
        else:
            _fail(f"Unexpected terminal status: {job['status']!r}")

        if "Completed" in out or "completed" in out:
            _pass("Completion status reflected in CLI output")
        else:
            _fail("Completion status not found in CLI output")

        # Verify summary_types was passed through, not silently dropped or sent as []
        actual = job.get("summary_types")
        if actual == ["emotional_state_snapshot"]:
            _pass("summary_types correctly stored as ['emotional_state_snapshot']")
        else:
            _fail(f"summary_types mismatch: got {actual!r}, expected ['emotional_state_snapshot']")

        return job

    except subprocess.TimeoutExpired:
        _fail("confirm --watch timed out (300s)")
    except Exception as e:
        _fail(f"Section G raised: {e}")
        traceback.print_exc()
    return None


def section_h_upload_cancel(good_jsonl: Path) -> None:
    _section("H · olira ingest upload + cancel --yes → CANCELLED")
    try:
        idem_key = f"cli-e2e-h-{RUN_ID}"
        # Upload without --watch so we can cancel quickly
        r = _cli("ingest", "upload", str(good_jsonl), "--idempotency-key", idem_key, timeout=60)
        out = (r.stdout + r.stderr).strip()
        _info(out)

        job_id = _extract_job_id(out)
        if not job_id:
            _fail("Could not extract job ID from upload output")
            return

        _pass(f"Job created for cancel test: {job_id[-12:]}")

        # Wait until it's in a cancellable state
        try:
            _poll_job_api(
                job_id,
                {"awaiting_confirmation", "replaying", "backfilling"},
                timeout_s=90,
            )
        except TimeoutError:
            _skip("Job did not reach cancellable state within 90s")
            return

        rc, out = _cli_out("ingest", "cancel", job_id, "--yes")
        _info(out)
        if rc == 0:
            _pass("cancel --yes exited 0")
        else:
            _fail(f"cancel --yes exited {rc}")

        if "cancel" in out.lower():
            _pass("Cancellation message printed")
        else:
            _fail("Cancellation message not found in output")

        # Verify final status via API
        time.sleep(5)
        job = _poll_job_api(job_id, _TERMINAL, timeout_s=60)
        if job["status"] == "cancelled":
            _pass("API confirms job CANCELLED")
        else:
            _fail(f"Expected CANCELLED, got {job['status']!r}")

        for pid in job.get("patient_log_counts", {}).keys():
            if pid not in CREATED_PATIENT_IDS:
                CREATED_PATIENT_IDS.append(pid)

    except Exception as e:
        _fail(f"Section H raised: {e}")
        traceback.print_exc()


def section_i_no_confirm(good_jsonl: Path) -> None:
    _section("I · olira ingest upload --no-confirm → runs to terminal without review")
    try:
        idem_key = f"cli-e2e-i-{RUN_ID}"
        r = _cli(
            "ingest", "upload", str(good_jsonl),
            "--no-confirm",
            "--idempotency-key", idem_key,
            timeout=60,
        )
        out = (r.stdout + r.stderr).strip()
        _info(out)

        if r.returncode == 0:
            _pass("upload --no-confirm exited 0")
        else:
            _fail(f"upload --no-confirm exited {r.returncode}")

        job_id = _extract_job_id(out)
        if not job_id:
            _fail("Could not extract job ID")
            return

        if "no-confirm" in out.lower() or "confirmation" in out.lower() or "completion" in out.lower():
            _pass("No-confirm path mentioned in output")
        else:
            _info("No explicit no-confirm message; checking API status")

        # Verify the job was created with require_confirmation=False
        job = _poll_job_api(job_id, _TERMINAL, timeout_s=240)
        if job["status"] in ("completed", "completed_with_errors"):
            _pass(f"Job reached terminal status without confirmation: {job['status']}")
        elif job["status"] == "awaiting_confirmation":
            _fail("Job stopped at AWAITING_CONFIRMATION — --no-confirm had no effect")
        else:
            _fail(f"Unexpected terminal status: {job['status']!r}")

        for pid in job.get("patient_log_counts", {}).keys():
            if pid not in CREATED_PATIENT_IDS:
                CREATED_PATIENT_IDS.append(pid)

    except subprocess.TimeoutExpired:
        _fail("Section I timed out (60s for upload)")
    except Exception as e:
        _fail(f"Section I raised: {e}")
        traceback.print_exc()


def section_j_validate_check_org(good_jsonl: Path) -> None:
    _section("J · olira validate --check-org — cross-checks patient IDs against org")
    if not CONSOLE_TOKEN:
        _skip("No console_token in config — skipping --check-org test")
        return
    # This section only works if patients from section D/G are still in the org.
    # We test that validate runs without crashing and prints the org fetch message.
    try:
        rc, out = _cli_out("validate", str(good_jsonl), "--check-org", timeout=60)
        _info(out[:400])
        # Either passes or warns — both are fine; we just check it doesn't crash.
        if rc in (0, 1):
            _pass(f"validate --check-org exited {rc} without crashing")
        else:
            _fail(f"validate --check-org unexpected exit code {rc}")

        if "org patient" in out.lower() or "check" in out.lower() or "fetch" in out.lower():
            _pass("Org patient fetch message present")
        else:
            _info("Org fetch message not detected (may have printed differently)")

    except subprocess.TimeoutExpired:
        _fail("validate --check-org timed out")
    except Exception as e:
        _fail(f"Section J raised: {e}")


def section_k_wrong_scope() -> None:
    _section("K · Scope enforcement — wrong-scope key → error message, not crash")
    try:
        # Write a fake credential that is just a random string (wrong scope / invalid key)
        _write_credentials("olira_dev_" + "0" * 64)

        rc, out = _cli_out("ingest", "list", timeout=20)
        _info(out)

        # Restore real credentials immediately
        _write_credentials(API_KEY)

        if rc != 0:
            _pass(f"CLI exited non-zero ({rc}) with invalid key — correct")
        else:
            _fail("CLI exited 0 with invalid key — expected failure")

        if any(w in out.lower() for w in ("error", "403", "401", "unauthorized", "forbidden", "invalid")):
            _pass("Error message printed for invalid key")
        else:
            _fail("No error message found for invalid key")

    except Exception as e:
        _write_credentials(API_KEY)  # always restore
        _fail(f"Section K raised: {e}")


def section_l_retry_backfill(job_id: str | None, g_job: dict | None) -> None:
    _section("L · olira ingest retry-backfill — re-runs view backfill on COMPLETED_WITH_ERRORS")
    if not job_id or not g_job:
        _skip("No job from Section G — skipping")
        return

    if g_job.get("status") != "completed_with_errors":
        _skip(
            f"Section G job ended in '{g_job.get('status')}' not 'completed_with_errors' — "
            "retry-backfill path not exercised (requires a failed backfill to trigger)"
        )
        return

    try:
        r = _cli("ingest", "retry-backfill", job_id, "--watch", timeout=300)
        out = (r.stdout + r.stderr).strip()
        _info(out[:800])

        if r.returncode == 0:
            _pass("retry-backfill --watch exited 0")
        else:
            _fail(f"retry-backfill --watch exited {r.returncode}")

        job = _poll_job_api(job_id, _TERMINAL, timeout_s=10)
        if job["status"] in ("completed", "completed_with_errors"):
            _pass(f"API confirms job terminal after retry: {job['status']}")
        else:
            _fail(f"Unexpected status after retry: {job['status']!r}")

        if "backfill" in out.lower() or "retry" in out.lower():
            _pass("Retry message present in output")
        else:
            _fail("Retry message not found in output")

    except subprocess.TimeoutExpired:
        _fail("retry-backfill --watch timed out (300s)")
    except Exception as e:
        _fail(f"Section L raised: {e}")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    global failures
    failures = 0

    tmp_dir = Path(tempfile.mkdtemp(prefix="olira-cli-e2e-"))

    good_jsonl: Path | None = None
    bad_jsonl: Path | None = None
    d_job_id: str | None = None
    g_job: dict | None = None

    try:
        good_jsonl, bad_jsonl = section_a_setup(tmp_dir)
        section_b_validate_clean(good_jsonl)
        section_c_validate_errors(bad_jsonl)
        d_job_id = section_d_upload_watch(good_jsonl)
        section_e_list(d_job_id)
        section_f_status(d_job_id)
        g_job = section_g_confirm_watch(d_job_id)
        section_h_upload_cancel(good_jsonl)
        section_i_no_confirm(good_jsonl)
        section_j_validate_check_org(good_jsonl)
        section_k_wrong_scope()
        section_l_retry_backfill(d_job_id, g_job)

    finally:
        _restore_credentials()
        _cleanup()
        import shutil as _shutil
        _shutil.rmtree(tmp_dir, ignore_errors=True)

    total_sections = 12
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    if failures == 0:
        print(f"{BOLD}{GREEN}All tests passed ({total_sections} sections).{RESET}")
        return 0
    else:
        print(f"{BOLD}{RED}{failures} assertion(s) failed across {total_sections} sections.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
