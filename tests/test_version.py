"""Minimal test so CI pytest runs pass."""

import olira_cli


def test_version_is_non_empty() -> None:
    """Package exposes a non-empty __version__."""
    assert hasattr(olira_cli, "__version__")
    assert isinstance(olira_cli.__version__, str)
    assert len(olira_cli.__version__) > 0
