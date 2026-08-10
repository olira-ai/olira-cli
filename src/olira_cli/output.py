"""Output layer — human chrome vs. the JSON envelope, and nothing in between.

Mode is set once by cli.main() from the parsed --json flag. Every command
module reads it through the functions here instead of calling print()
directly, so human formatting and machine formatting can never drift apart
mid-command.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from olira_cli.errors import CliError

_json_mode = False


def set_mode(json_mode: bool) -> None:
    global _json_mode
    _json_mode = json_mode


def json_mode() -> bool:
    return _json_mode


def is_tty() -> bool:
    return sys.stdout.isatty()


def use_color() -> bool:
    if _json_mode:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return is_tty()


def info(msg: str) -> None:
    """Human-only chrome (progress lines, hints, tips). Suppressed entirely in JSON mode."""
    if not _json_mode:
        print(msg)


def warn(msg: str) -> None:
    """Diagnostic warning — always stderr, in both modes."""
    print(msg, file=sys.stderr)


def table(headers: list[str], rows: list[list[str]], widths: list[int] | None = None) -> None:
    """Print a simple fixed-width table. No-op in JSON mode."""
    if _json_mode:
        return
    if widths is None:
        widths = [
            max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)
        ]
    print("  " + " ".join(f"{h:<{w}}" for h, w in zip(headers, widths, strict=True)))
    print("  " + "-" * (sum(widths) + len(widths) - 1))
    for row in rows:
        print("  " + " ".join(f"{str(c):<{w}}" for c, w in zip(row, widths, strict=True)))


def _cli_version() -> str:
    from olira_cli import __version__

    return __version__


def emit_success(command: str, data: dict[str, Any], warnings: list[str] | None = None) -> None:
    """Emit the success envelope. JSON mode only — human rendering already happened via _render_*()."""
    if not _json_mode:
        return
    envelope = {
        "ok": True,
        "command": command,
        "cli_version": _cli_version(),
        "data": data,
        "warnings": warnings or [],
    }
    print(json.dumps(envelope, default=str))


def emit_error(command: str, err: CliError) -> None:
    if _json_mode:
        envelope = {
            "ok": False,
            "command": command,
            "cli_version": _cli_version(),
            "error": {
                "code": err.code,
                "message": err.message,
                "remediation": err.remediation,
                "http_status": err.http_status,
                "details": err.details,
            },
        }
        print(json.dumps(envelope, default=str))
        return
    print(f"Error: {err.message}", file=sys.stderr)
    if err.remediation:
        print(f"  {err.remediation}", file=sys.stderr)


def emit_event(event: dict[str, Any]) -> None:
    """Emit one NDJSON line (used by --watch in JSON mode). No-op in human mode."""
    if _json_mode:
        print(json.dumps(event, default=str))
