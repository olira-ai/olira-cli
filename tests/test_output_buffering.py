"""Regression: --watch's NDJSON events must reach a redirected file/pipe as they're
written, not sit buffered until the process exits — that's what makes
"run --watch in the background, tail the log" actually work for long jobs.
"""

from __future__ import annotations

import sys

from olira_cli.cli import _force_line_buffering


def test_force_line_buffering_enables_line_buffering_on_redirected_stdout(tmp_path, monkeypatch):
    path = tmp_path / "out.txt"
    f = open(path, "w", encoding="utf-8")  # noqa: SIM115 - closed explicitly below
    monkeypatch.setattr(sys, "stdout", f)
    try:
        assert f.line_buffering is False, "a plain redirected file should default to full buffering"
        _force_line_buffering()
        assert sys.stdout.line_buffering is True
    finally:
        f.close()


def test_force_line_buffering_tolerates_streams_without_reconfigure(monkeypatch):
    """pytest's own capture objects and similar stand-ins may not support reconfigure()."""

    class _NoReconfigure:
        pass

    monkeypatch.setattr(sys, "stdout", _NoReconfigure())
    monkeypatch.setattr(sys, "stderr", _NoReconfigure())
    _force_line_buffering()  # must not raise
