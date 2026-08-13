"""olira init agent: idempotency, --claude/--cursor/--codex filtering, and the per-process skill split."""

from __future__ import annotations

from tests.conftest import json_envelope

_SKILLS = ["olira-ingest", "olira-query", "olira-setup", "olira-actions"]


def test_init_agent_creates_all_files(run_cli, tmp_path):
    code, out, _ = run_cli(["--json", "init", "agent", "--dir", str(tmp_path)])
    assert code == 0
    env = json_envelope(out)
    actions = {f["action"] for f in env["data"]["files"]}
    assert actions == {"created"}
    assert (tmp_path / "AGENTS.md").exists()
    for slug in _SKILLS:
        assert (tmp_path / ".claude" / "skills" / slug / "SKILL.md").exists()
        assert (tmp_path / ".agents" / "skills" / slug / "SKILL.md").exists()


def test_init_agent_second_run_is_unchanged(run_cli, tmp_path):
    run_cli(["--json", "init", "agent", "--dir", str(tmp_path)])
    code, out, _ = run_cli(["--json", "init", "agent", "--dir", str(tmp_path)])
    assert code == 0
    env = json_envelope(out)
    actions = {f["action"] for f in env["data"]["files"]}
    assert actions == {"unchanged"}


def test_init_agent_preserves_surrounding_agents_md_content(run_cli, tmp_path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# My repo\n\nSome existing instructions.\n")
    run_cli(["--json", "init", "agent", "--dir", str(tmp_path), "--codex"])
    content = agents_md.read_text()
    assert "Some existing instructions." in content
    assert "Olira CLI" in content

    run_cli(["--json", "init", "agent", "--dir", str(tmp_path), "--codex"])
    content2 = agents_md.read_text()
    assert content == content2


def test_init_agent_claude_flag_filters_files(run_cli, tmp_path):
    code, out, _ = run_cli(["--json", "init", "agent", "--dir", str(tmp_path), "--claude"])
    assert code == 0
    assert (tmp_path / "AGENTS.md").exists()
    for slug in _SKILLS:
        assert (tmp_path / ".claude" / "skills" / slug / "SKILL.md").exists()
    assert not (tmp_path / ".agents").exists()


def test_init_agent_shared_skills_are_identical_to_claude(run_cli, tmp_path):
    """Cursor/Codex and Claude Code read the same SKILL.md format — one file, no per-client fork."""
    run_cli(["--json", "init", "agent", "--dir", str(tmp_path)])
    for slug in _SKILLS:
        claude_content = (tmp_path / ".claude" / "skills" / slug / "SKILL.md").read_text()
        shared_content = (tmp_path / ".agents" / "skills" / slug / "SKILL.md").read_text()
        assert claude_content == shared_content


def test_init_agent_never_prompts(run_cli, tmp_path, no_tty, refuse_input):
    code, _, _ = run_cli(["--json", "init", "agent", "--dir", str(tmp_path)])
    assert code == 0


def test_init_agent_skills_are_independently_focused(run_cli, tmp_path):
    """Each skill should carry only its own workflow's detail, not a copy of the others'."""
    run_cli(["--json", "init", "agent", "--dir", str(tmp_path), "--claude"])
    ingest = (tmp_path / ".claude" / "skills" / "olira-ingest" / "SKILL.md").read_text()
    query = (tmp_path / ".claude" / "skills" / "olira-query" / "SKILL.md").read_text()
    setup = (tmp_path / ".claude" / "skills" / "olira-setup" / "SKILL.md").read_text()
    actions = (tmp_path / ".claude" / "skills" / "olira-actions" / "SKILL.md").read_text()

    assert "name: olira-ingest" in ingest
    assert "AWAITING_CONFIRMATION" in ingest.upper() or "awaiting_confirmation" in ingest
    assert "olira patients list" not in ingest

    assert "name: olira-query" in query
    assert "olira patients list" in query
    assert "AWAITING_CONFIRMATION".lower() not in query.lower()

    assert "name: olira-setup" in setup
    assert "keys create" in setup
    assert "AWAITING_CONFIRMATION".lower() not in setup.lower()

    assert "name: olira-actions" in actions
    assert "Olira-Signature" in actions
    assert "EmailDestinationConfig" in actions
    assert "localhost" in actions
    assert "webhookConfig" in actions
    assert "using System.Linq;" in actions
    assert "olira patients list" not in actions
    assert "AWAITING_CONFIRMATION".lower() not in actions.lower()
    assert "keys create" not in actions


def test_init_agent_skill_content_has_no_unsubstituted_placeholder(run_cli, tmp_path):
    """{{VERSION}} must always be replaced — a leaked placeholder means the loader broke."""
    run_cli(["--json", "init", "agent", "--dir", str(tmp_path)])
    for slug in _SKILLS:
        content = (tmp_path / ".claude" / "skills" / slug / "SKILL.md").read_text()
        assert "{{VERSION}}" not in content
        assert "doc matches v" in content
