"""Minimal test so CI pytest runs pass."""

import pytest

import olira_cli


def test_version_is_non_empty() -> None:
    """Package exposes a non-empty __version__."""
    assert hasattr(olira_cli, "__version__")
    assert isinstance(olira_cli.__version__, str)
    assert len(olira_cli.__version__) > 0


def test_version_flag_prints_version_and_exits(run_cli, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert olira_cli.__version__ in out
