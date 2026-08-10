"""olira validate: exit codes, structured JSON details, and NO_COLOR handling."""

from __future__ import annotations

from tests.conftest import json_envelope


def test_validate_clean_file_exits_0(run_cli, tmp_path):
    path = tmp_path / "clean.jsonl"
    path.write_text(
        '{"type": "patient", "data": {"first_name": "Jane", "last_name": "Doe"}}\n'
        '{"type": "log", "data": {"patient_id": "abc123", "event_type": "symptom_report", '
        '"timestamp": "2025-01-15T09:00:00Z"}}\n'
    )
    code, out, _ = run_cli(["--json", "validate", str(path)])
    assert code == 0
    env = json_envelope(out)
    assert env["ok"] is True
    assert env["data"]["counts"]["patient_count"] == 1
    assert env["data"]["counts"]["log_count"] == 1


def test_validate_bad_file_exits_5_with_structured_errors(run_cli, tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(
        "not json at all\n"
        '{"type": "log", "data": {"event_type": "unknown_type_xyz", "patient_id": "abc123", '
        '"timestamp": "2025-01-15T09:00:00Z"}}\n'
    )
    code, out, _ = run_cli(["--json", "validate", str(path)])
    assert code == 5
    env = json_envelope(out)
    assert env["ok"] is False
    assert env["error"]["code"] == "VALIDATION_FAILED"
    errors = env["error"]["details"]["errors"]
    assert any("invalid JSON" in e for e in errors)
    assert any("unknown log_type" in e for e in errors)


def test_validate_missing_file_exits_4(run_cli, tmp_path):
    code, out, _ = run_cli(["--json", "validate", str(tmp_path / "nope.jsonl")])
    assert code == 4
    env = json_envelope(out)
    assert env["error"]["code"] == "FILE_NOT_FOUND"


def test_validate_no_color_env_strips_ansi(run_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    path = tmp_path / "clean.jsonl"
    path.write_text('{"type": "patient", "data": {"first_name": "Jane"}}\n')
    code, out, _ = run_cli(["validate", str(path)])
    assert code == 0
    assert "\033[" not in out


def test_validate_check_org_requires_api_key_not_login(run_cli, tmp_path, creds_file):
    """Regression: --check-org used to send a browser-login JWT to a key-only /v1/* route."""
    creds_file()
    path = tmp_path / "clean.jsonl"
    path.write_text('{"type": "patient", "data": {"first_name": "Jane"}}\n')
    code, out, _ = run_cli(["--json", "validate", str(path), "--check-org"])
    assert code == 3
    env = json_envelope(out)
    assert env["error"]["code"] == "AUTH_REQUIRED"
    assert "OLIRA_API_KEY" in env["error"]["remediation"]
