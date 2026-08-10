"""resolve_auth() precedence and the sdk/console credential-class split."""

from __future__ import annotations

import pytest

from olira_cli.credentials import resolve_auth
from olira_cli.errors import AuthError


def test_sdk_prefers_flag_over_env(no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_env_key")
    auth = resolve_auth("sdk", api_key_flag="olira_dev_flag_key")
    assert auth.token == "olira_dev_flag_key"
    assert auth.source == "flag"


def test_sdk_falls_back_to_env(no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_env_key")
    auth = resolve_auth("sdk")
    assert auth.token == "olira_dev_env_key"
    assert auth.source == "env"


def test_sdk_uses_default_prod_url_with_no_creds_file(no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_prod_key")
    auth = resolve_auth("sdk")
    assert auth.api_server == "https://app-api.prod.olira.ai/app-api"


def test_sdk_uses_creds_file_api_server_when_present(creds_file, monkeypatch):
    creds_file(api_server="https://app-api.stage.olira.ai/app-api")
    monkeypatch.setenv("OLIRA_API_KEY", "olira_stage_key")
    auth = resolve_auth("sdk")
    assert auth.api_server == "https://app-api.stage.olira.ai/app-api"


def test_sdk_env_url_overrides_creds_file_api_server(creds_file, monkeypatch):
    """OLIRA_API_URL must win over a stored login's api_server, not the other way round."""
    creds_file(api_server="https://app-api.stage.olira.ai/app-api")
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    monkeypatch.setenv("OLIRA_API_URL", "https://app-api.dev.olira.ai/app-api")
    auth = resolve_auth("sdk")
    assert auth.api_server == "https://app-api.dev.olira.ai/app-api"


def test_sdk_rejects_login_only_credential(creds_file):
    creds_file()
    with pytest.raises(AuthError) as exc:
        resolve_auth("sdk")
    assert exc.value.exit_code == 3
    assert "OLIRA_API_KEY" in exc.value.remediation


def test_sdk_login_only_remediation_does_not_suggest_a_fixed_scope(creds_file):
    """resolve_auth is shared by every sdk-class command (ingest, patients, state,
    integrations, ...) and can't know which scope the caller actually needs — it must
    not hardcode one (regression: used to always suggest sdk:historical-ingest, wrong
    for every command except ingest)."""
    creds_file()
    with pytest.raises(AuthError) as exc:
        resolve_auth("sdk")
    assert "sdk:historical-ingest" not in exc.value.remediation


def test_sdk_with_nothing_raises_auth_required(no_creds):
    with pytest.raises(AuthError) as exc:
        resolve_auth("sdk")
    assert exc.value.exit_code == 3


def test_console_uses_creds_file(creds_file):
    creds = creds_file()
    auth = resolve_auth("console")
    assert auth.token == creds["access_token"]
    assert auth.source == "login"


def test_console_rejects_api_key_only(no_creds, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_key")
    with pytest.raises(AuthError) as exc:
        resolve_auth("console")
    assert exc.value.exit_code == 3
    assert "olira login" in exc.value.remediation


def test_console_with_nothing_raises_not_logged_in(no_creds):
    with pytest.raises(AuthError):
        resolve_auth("console")
