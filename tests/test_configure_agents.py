"""olira configure agents: idempotency and --target filtering."""

from __future__ import annotations

from tests.conftest import json_envelope


def test_configure_agents_creates_all_files(run_cli, tmp_path):
    code, out, _ = run_cli(["--json", "configure", "agents", "--dir", str(tmp_path)])
    assert code == 0
    env = json_envelope(out)
    actions = {f["action"] for f in env["data"]["files"]}
    assert actions == {"created"}
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".claude" / "skills" / "olira" / "SKILL.md").exists()
    assert (tmp_path / ".cursor" / "rules" / "olira.mdc").exists()


def test_configure_agents_second_run_is_unchanged(run_cli, tmp_path):
    run_cli(["--json", "configure", "agents", "--dir", str(tmp_path)])
    code, out, _ = run_cli(["--json", "configure", "agents", "--dir", str(tmp_path)])
    assert code == 0
    env = json_envelope(out)
    actions = {f["action"] for f in env["data"]["files"]}
    assert actions == {"unchanged"}


def test_configure_agents_preserves_surrounding_agents_md_content(run_cli, tmp_path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# My repo\n\nSome existing instructions.\n")
    run_cli(["--json", "configure", "agents", "--dir", str(tmp_path), "--target", "agents-md"])
    content = agents_md.read_text()
    assert "Some existing instructions." in content
    assert "Olira CLI" in content

    run_cli(["--json", "configure", "agents", "--dir", str(tmp_path), "--target", "agents-md"])
    content2 = agents_md.read_text()
    assert content == content2


def test_configure_agents_target_filters_files(run_cli, tmp_path):
    code, out, _ = run_cli(["--json", "configure", "agents", "--dir", str(tmp_path), "--target", "claude"])
    assert code == 0
    assert not (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".claude" / "skills" / "olira" / "SKILL.md").exists()
    assert not (tmp_path / ".cursor").exists()


def test_configure_agents_never_prompts(run_cli, tmp_path, no_tty, refuse_input):
    code, _, _ = run_cli(["--json", "configure", "agents", "--dir", str(tmp_path)])
    assert code == 0
