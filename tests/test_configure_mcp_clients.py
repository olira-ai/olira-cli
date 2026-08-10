"""olira configure claude / codex: no auth required, env-var references (never raw
secrets) written to disk, and existing config content/other servers preserved.
"""

from __future__ import annotations

from tests.conftest import json_envelope


def test_configure_claude_requires_no_auth(run_cli, no_creds, tmp_path):
    """Unlike configure cursor, this needs no login and no API key to run."""
    code, out, _ = run_cli(["--json", "configure", "claude", "--dir", str(tmp_path)])
    assert code == 0
    env = json_envelope(out)
    assert env["data"]["action"] == "created"


def test_configure_claude_writes_env_var_reference_not_a_secret(run_cli, no_creds, tmp_path, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_should_never_appear_in_the_file")
    run_cli(["--json", "configure", "claude", "--dir", str(tmp_path)])
    content = (tmp_path / ".mcp.json").read_text()
    assert "should_never_appear_in_the_file" not in content
    assert "${OLIRA_API_KEY}" in content
    assert '"type": "http"' in content


def test_configure_claude_respects_api_key_env_override(run_cli, no_creds, tmp_path):
    run_cli(["--json", "configure", "claude", "--dir", str(tmp_path), "--api-key-env", "MY_TOKEN"])
    content = (tmp_path / ".mcp.json").read_text()
    assert "${MY_TOKEN}" in content


def test_configure_claude_preserves_other_mcp_servers(run_cli, no_creds, tmp_path):
    import json

    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": {"other-server": {"url": "https://example.com"}}}))
    run_cli(["--json", "configure", "claude", "--dir", str(tmp_path)])
    config = json.loads(path.read_text())
    assert "other-server" in config["mcpServers"]
    assert "olira-patient-state" in config["mcpServers"]


def test_configure_claude_second_run_is_unchanged(run_cli, no_creds, tmp_path):
    run_cli(["--json", "configure", "claude", "--dir", str(tmp_path)])
    code, out, _ = run_cli(["--json", "configure", "claude", "--dir", str(tmp_path)])
    assert code == 0
    assert json_envelope(out)["data"]["action"] == "unchanged"


def test_configure_claude_env_selects_server_url(run_cli, no_creds, tmp_path):
    code, out, _ = run_cli(["--json", "configure", "claude", "--dir", str(tmp_path), "--env", "stage"])
    assert code == 0
    env = json_envelope(out)
    assert "stage" in env["data"]["mcp_server"]


def test_configure_codex_requires_no_auth(run_cli, no_creds, tmp_path):
    code, out, _ = run_cli(["--json", "configure", "codex", "--dir", str(tmp_path)])
    assert code == 0
    env = json_envelope(out)
    assert env["data"]["action"] == "created"
    content = (tmp_path / ".codex" / "config.toml").read_text()
    assert 'bearer_token_env_var = "OLIRA_API_KEY"' in content
    assert "[mcp_servers.olira-patient-state]" in content


def test_configure_codex_never_writes_raw_token(run_cli, no_creds, tmp_path, monkeypatch):
    monkeypatch.setenv("OLIRA_API_KEY", "olira_dev_should_never_appear_in_the_file")
    run_cli(["--json", "configure", "codex", "--dir", str(tmp_path)])
    content = (tmp_path / ".codex" / "config.toml").read_text()
    assert "should_never_appear_in_the_file" not in content


def test_configure_codex_preserves_surrounding_toml_content(run_cli, no_creds, tmp_path):
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('model = "gpt-5"\n\n[sandbox]\nmode = "workspace-write"\n')

    run_cli(["--json", "configure", "codex", "--dir", str(tmp_path)])
    content = config_path.read_text()
    assert 'model = "gpt-5"' in content
    assert 'mode = "workspace-write"' in content
    assert "[mcp_servers.olira-patient-state]" in content

    # idempotent re-run: unrelated content still untouched, block not duplicated
    run_cli(["--json", "configure", "codex", "--dir", str(tmp_path)])
    content2 = config_path.read_text()
    assert content2.count("[mcp_servers.olira-patient-state]") == 1
    assert 'model = "gpt-5"' in content2


def test_init_agent_codex_only_writes_agents_md(run_cli, tmp_path):
    code, out, _ = run_cli(["--json", "init", "agent", "--dir", str(tmp_path), "--codex"])
    assert code == 0
    env = json_envelope(out)
    paths = {f["path"] for f in env["data"]["files"]}
    assert paths == {str(tmp_path / "AGENTS.md")}
    assert (tmp_path / "AGENTS.md").exists()
