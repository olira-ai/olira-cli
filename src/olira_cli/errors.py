"""Structured CLI errors — one exception hierarchy, one exit-code mapping, one HTTP-error translator."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class CommandResult:
    """What every cmd_*() returns. cli.main() turns this into the JSON envelope
    (or does nothing in human mode, since the command already printed via _render_*())."""

    data: dict[str, Any]
    exit_code: int = 0
    warnings: list[str] = field(default_factory=list)


class CliError(Exception):
    """Base for all errors the CLI raises deliberately.

    Caught once in cli.main(); carries everything output.emit_error() needs
    to render either a human message or a JSON error envelope.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "ERROR",
        exit_code: int = 1,
        remediation: str | None = None,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.remediation = remediation
        self.details = details or {}
        self.http_status = http_status


class AuthError(CliError):
    def __init__(self, message: str, *, code: str = "AUTH_REQUIRED", remediation: str | None = None, **kw: Any):
        super().__init__(message, code=code, exit_code=3, remediation=remediation, **kw)


class NotFoundError(CliError):
    def __init__(self, message: str, *, code: str = "NOT_FOUND", remediation: str | None = None, **kw: Any):
        super().__init__(message, code=code, exit_code=4, remediation=remediation, **kw)


class ValidationError(CliError):
    def __init__(self, message: str, *, code: str = "VALIDATION_FAILED", remediation: str | None = None, **kw: Any):
        super().__init__(message, code=code, exit_code=5, remediation=remediation, **kw)


class StateError(CliError):
    def __init__(self, message: str, *, code: str = "WRONG_STATE", remediation: str | None = None, **kw: Any):
        super().__init__(message, code=code, exit_code=6, remediation=remediation, **kw)


class NetworkError(CliError):
    def __init__(self, message: str, *, code: str = "NETWORK_ERROR", remediation: str | None = None, **kw: Any):
        super().__init__(message, code=code, exit_code=7, remediation=remediation, **kw)


class WatchTimeoutError(CliError):
    def __init__(self, message: str, *, code: str = "WATCH_TIMEOUT", remediation: str | None = None, **kw: Any):
        super().__init__(message, code=code, exit_code=8, remediation=remediation, **kw)


def _extract_body_message(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    return body.get("detail") or body.get("message")


def from_http_error(e: httpx.HTTPStatusError) -> CliError:
    """Translate an httpx.HTTPStatusError into the right CliError subclass.

    Single replacement for the CLI's three previously-divergent error printers.
    Guards non-JSON response bodies (unlike the old api.py variants, which
    called response.json() unguarded and could themselves raise).
    """
    status = e.response.status_code
    body_msg = _extract_body_message(e.response)
    msg = body_msg or str(e)

    if status in (401, 403):
        return AuthError(msg, code="AUTH_FORBIDDEN" if status == 403 else "AUTH_REQUIRED", http_status=status)
    if status == 404:
        return NotFoundError(msg, http_status=status)
    if status == 409:
        return StateError(msg, code="CONFLICT", http_status=status)
    if status == 422:
        return ValidationError(msg, http_status=status)
    if status >= 500:
        return NetworkError(msg, code="SERVER_ERROR", http_status=status)
    return CliError(msg, code="HTTP_ERROR", exit_code=1, http_status=status)


def require_tty(action: str, bypass_flag: str) -> None:
    """Raise StateError if we can't safely prompt: no TTY, or JSON mode requested.

    Call this immediately before any InquirerPy/input() call so a headless
    agent gets a clear, fast failure instead of a hang or a garbled prompt.
    """
    from olira_cli import output

    if not sys.stdin.isatty() or output.json_mode():
        raise StateError(
            f"{action} requires an interactive terminal.",
            code="PROMPT_REQUIRED",
            remediation=f"Re-run with {bypass_flag}.",
        )
