"""olira validate — local JSONL validation for historical ingestion files.

Checks each line of a JSONL file for:
  - Valid JSON
  - Required fields (type, data)
  - For log records: event_type is a known OliraLogType value
  - For log records: patient_id is present and not a PII value (email, phone, SSN)
  - Patient records appear before any log that first references them
    (unless --skip-order-check is passed or the patient already exists in the org)

Prints a summary and exits 0 if clean, 1 if errors were found.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ── known event types (mirrors OliraLogType in common-models) ─────────────────

KNOWN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # Symptom reports
        "symptom_report",
        "symptom_free_text",
        "symptom_detail",
        "moods_report",
        "functional_class_reported",
        "health_metric_reported",
        # Lab & clinical
        "lab_results_received",
        "vitals_measurement",
        "clinical_note_received",
        "clinical_finding_reported",
        "procedure_result_received",
        "procedure_performed",
        "genomic_variant_reported",
        "imaging_result_received",
        "clinical_measurement_reported",
        "treatment_response_assessment_reported",
        "clinical_plan_item_reported",
        "care_encounter_reported",
        "care_goal_reported",
        "immunization_reported",
        "allergy_intolerance_reported",
        "family_history_reported",
        "device_reported",
        "memory_report",
        "unstructured_report_received",
        # Questionnaires
        "questionnaire_response",
        "questionnaire_item_response",
        # Conversations
        "conversation_completed",
        "conversation_turn_logged",
        # Passive data
        "heart_rate_data_received",
        "sleep_data_received",
        "activity_data_received",
        "cgm_reading_received",
        "spo2_reading_received",
        "weight_measurement_received",
        # Medications
        "medication_action",
        "medication_dose_update",
        "medication_adverse_event_reported",
        # Engagement
        "user_login",
        "user_logout",
        "content_interacted",
        "notification_interacted",
        "task_updated",
        "interaction_feedback",
        "feature_used",
        # Profile
        "demographics_updated",
        "condition_recorded",
        "preferences_updated",
        "emergency_contact_updated",
        "care_team_updated",
        "insurance_updated",
        "social_updated",
        "pharmacy_updated",
        "treatment_phase_changed",
    }
)

# PII patterns (mirrors SDK validation.py)
_RE_EMAIL = re.compile(r"@")
_RE_PHONE = re.compile(r"^\d{10}$")
_RE_SSN = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_RE_OBJECT_ID = re.compile(r"^[0-9a-f]{24}$")


def _parse_iso8601(ts: str) -> bool:
    """Return True if ts parses as an ISO 8601 datetime."""
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _is_pii(patient_id: str) -> str | None:
    """Return a description of the PII violation, or None if clean."""
    s = patient_id.strip()
    if not s:
        return "empty"
    if _RE_EMAIL.search(s):
        return "looks like an email address"
    stripped = s.replace("-", "").replace(" ", "")
    if _RE_PHONE.match(stripped) and len(stripped) == 10:
        return "looks like a US phone number"
    if _RE_SSN.match(s):
        return "looks like an SSN"
    return None


# ── main entry point ──────────────────────────────────────────────────────────


def cmd_validate(args: Any) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1
    if path.suffix != ".jsonl":
        print(f"Warning: file does not have a .jsonl extension: {path.name}", file=sys.stderr)

    errors: list[str] = []
    warnings: list[str] = []

    patient_count = 0
    log_count = 0
    event_type_counts: dict[str, int] = {}

    # Track patient_ids defined in the file (by external_id) so we can warn
    # when a log references one not yet seen — if --skip-order-check is not set.
    known_patient_ids: set[str] = set()
    skip_order = getattr(args, "skip_order_check", False)

    # Optionally fetch org patients for cross-check
    org_patient_ids: set[str] | None = None
    if getattr(args, "check_org", False):
        org_patient_ids = _fetch_org_patient_ids()
        if org_patient_ids is None:
            return 1  # error already printed

    print(f"Validating {path.name} …")

    line_count = 0
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            line_count += 1
            if line_count % 50_000 == 0:
                print(f"  {line_count:,} lines processed…", end="\r", flush=True)

            # JSON parse
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                errors.append(f"L{lineno}: invalid JSON — {e}")
                continue

            if not isinstance(rec, dict):
                errors.append(f"L{lineno}: expected a JSON object, got {type(rec).__name__}")
                continue

            rec_type = rec.get("type")
            if rec_type not in ("patient", "log"):
                errors.append(f"L{lineno}: unknown record type {rec_type!r} — must be 'patient' or 'log'")
                continue

            data = rec.get("data")
            if not isinstance(data, dict):
                errors.append(f"L{lineno}: 'data' field must be a JSON object")
                continue

            if rec_type == "patient":
                patient_count += 1
                ext_ids = data.get("external_identifiers") or []
                for eid in ext_ids:
                    if isinstance(eid, dict) and eid.get("value"):
                        known_patient_ids.add(str(eid["value"]))
                has_anchor = (
                    any(isinstance(e, dict) and e.get("value") for e in ext_ids)
                    or data.get("email")
                    or data.get("phone_number")
                    or data.get("first_name")
                    or data.get("last_name")
                    or data.get("date_of_birth")
                )
                if not has_anchor:
                    errors.append(
                        f"L{lineno}: patient record has no identifying fields — "
                        "at least one of: external_identifiers, email, phone_number, "
                        "first_name, last_name, or date_of_birth is required"
                    )

            elif rec_type == "log":
                log_count += 1
                et = data.get("event_type") or ""
                pid = str(data.get("patient_id") or "")

                if not et:
                    errors.append(f"L{lineno}: log record is missing 'event_type'")
                elif et not in KNOWN_EVENT_TYPES:
                    errors.append(
                        f"L{lineno}: unknown event_type {et!r} — check the event type catalog at olira.ai/api-docs"
                    )
                else:
                    event_type_counts[et] = event_type_counts.get(et, 0) + 1

                if not pid:
                    errors.append(f"L{lineno}: log record is missing 'patient_id'")
                else:
                    pii = _is_pii(pid)
                    if pii:
                        errors.append(f"L{lineno}: patient_id {pid!r} {pii} — use a pseudonymous identifier")
                    elif not skip_order and not _RE_OBJECT_ID.match(pid):
                        # external_id reference — check it was declared earlier in the file
                        in_org = org_patient_ids is not None and pid in org_patient_ids
                        if pid not in known_patient_ids and not in_org:
                            warnings.append(
                                f"L{lineno}: log references patient_id {pid!r} which has not "
                                "been declared earlier in this file and was not found in the org. "
                                "The job will fail at Stage 3 if it cannot resolve this patient."
                            )

                ts = data.get("timestamp") or ""
                if not ts:
                    errors.append(f"L{lineno}: log record is missing 'timestamp'")
                elif not _parse_iso8601(ts):
                    errors.append(
                        f"L{lineno}: 'timestamp' {ts!r} is not a valid ISO 8601 datetime (e.g. 2025-01-15T09:00:00Z)"
                    )

    # ── Summary ───────────────────────────────────────────────────────────────
    total_lines = patient_count + log_count
    print("\r" + " " * 40 + "\r", end="")  # clear progress line

    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    divider = f"  {DIM}{'─' * 58}{RESET}"

    print()
    print(
        f"  {BOLD}Records{RESET}    {total_lines:>10,}  {DIM}·  {patient_count:,} patient  ·  {log_count:,} log{RESET}"
    )

    if event_type_counts:
        total_logs = sum(event_type_counts.values())
        print()
        print(f"  {BOLD}{'Event type':<38} {'Count':>10}  {'%':>4}{RESET}")
        print(divider)
        for et, count in sorted(event_type_counts.items(), key=lambda x: -x[1]):
            label = et.replace("_", " ").title()
            pct = count / total_logs * 100 if total_logs else 0
            pct_str = f"{pct:.0f}%" if pct >= 1 else "<1%"
            print(f"  {label:<38} {count:>10,}  {DIM}{pct_str:>4}{RESET}")
        print(divider)

    if warnings:
        print(f"\n  {YELLOW}Warnings ({len(warnings)}){RESET}")
        for w in warnings:
            print(f"  {YELLOW}⚠{RESET}  {w}")

    if errors:
        print(f"\n  {RED}Errors ({len(errors)}){RESET}")
        for err in errors[:20]:
            print(f"  {RED}✘{RESET}  {err}")
        if len(errors) > 20:
            print(f"  {DIM}  … and {len(errors) - 20} more{RESET}")
        print(f"\n  {RED}{BOLD}Validation failed{RESET} — {len(errors):,} error(s) found.")
        return 1

    suffix = f" {DIM}(with warnings){RESET}" if warnings else ""
    print(f"\n  {GREEN}✔{RESET}  {BOLD}Validation passed{RESET}{suffix}")
    return 0


def _fetch_org_patient_ids() -> set[str] | None:
    """Fetch external_identifiers from all org patients via the SDK API."""
    import httpx

    from olira_cli.credentials import load_credentials

    creds = load_credentials()
    if not creds or not creds.get("access_token"):
        print("Not logged in. Run: olira login --env <dev|stage|prod>", file=sys.stderr)
        return None

    api_base = creds["api_server"].rstrip("/")
    token = creds["access_token"]
    ids: set[str] = set()

    print("  Fetching org patients for cross-check…")
    page = 1
    try:
        with httpx.Client(timeout=30) as client:
            while True:
                r = client.get(
                    f"{api_base}/v1/patients",
                    params={"page": page, "page_size": 100},
                    headers={"Authorization": f"Bearer {token}"},
                )
                r.raise_for_status()
                data = r.json()
                patients = data.get("patients") or data.get("data") or []
                for p in patients:
                    for ext in p.get("external_identifiers") or []:
                        if ext.get("value"):
                            ids.add(str(ext["value"]))
                    # Also accept Olira UUID direct reference
                    if p.get("id"):
                        ids.add(str(p["id"]))
                total = data.get("total", 0)
                if page * 100 >= total:
                    break
                page += 1
        print(f"  Found {len(ids)} patient identifier(s) in org.\n")
        return ids
    except httpx.HTTPStatusError as e:
        try:
            msg = e.response.json().get("detail") or str(e)
        except Exception:
            msg = str(e)
        print(f"Error fetching org patients ({e.response.status_code}): {msg}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error fetching org patients: {e}", file=sys.stderr)
        return None
