"""Console redirect login flow — callback server and browser open."""

import asyncio
import base64
import json
import logging
import secrets
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

logger = logging.getLogger(__name__)

SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Authorization Successful</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;
               background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .container { text-align: center; background: white; padding: 60px 80px; border-radius: 16px;
                     box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .checkmark { font-size: 64px; margin-bottom: 20px; }
        h1 { color: #22c55e; margin: 0 0 10px 0; }
        p { color: #666; margin: 0; font-size: 18px; }
        .close-note { margin-top: 20px; color: #999; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="checkmark">✓</div>
        <h1>Authorization Successful!</h1>
        <p>You have been authenticated successfully.</p>
        <p class="close-note">You can close this window and return to the terminal.</p>
    </div>
</body>
</html>"""

ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sign-in failed</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               display: flex; justify-content: center; align-items: center; min-height: 100vh;
               background: #1a1a1a; color: #e8e8e6; }}
        .card {{ background: #242424; border: 1px solid #3e3e3e; border-radius: 16px;
                 padding: 48px 40px; max-width: 420px; width: 90%; text-align: center; }}
        .icon {{ width: 44px; height: 44px; border-radius: 50%; background: #3a3000;
                 display: flex; align-items: center; justify-content: center;
                 margin: 0 auto 20px; font-size: 20px; }}
        h1 {{ font-size: 18px; font-weight: 600; margin-bottom: 8px; }}
        .message {{ font-size: 14px; color: #a0a0a0; line-height: 1.5; margin-bottom: 0; }}
        .detail {{ margin-top: 16px; font-size: 12px; color: #666; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">⚠</div>
        <h1>Sign-in failed</h1>
        <p class="message">{error_message}</p>
        {error_detail}
    </div>
</body>
</html>"""

NO_ACCOUNT_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>No account found</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               display: flex; justify-content: center; align-items: center; min-height: 100vh;
               background: #1a1a1a; color: #e8e8e6; }
        .wrap { width: 100%; max-width: 360px; padding: 0 24px; }
        h2 { font-size: 22px; font-weight: 600; text-align: center; margin-bottom: 8px; }
        .sub { font-size: 14px; color: #a0a0a0; text-align: center; margin-bottom: 32px; line-height: 1.5; }
        .action-card { background: #242424; border: 1px solid #3e3e3e; border-radius: 12px;
                       padding: 20px; margin-bottom: 12px; }
        .action-card p { font-size: 13px; font-weight: 600; color: #e8e8e6; margin-bottom: 4px; }
        .action-card span { font-size: 13px; color: #a0a0a0; line-height: 1.5; display: block; margin-bottom: 12px; }
        .action-card a { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px;
                         font-size: 13px; font-weight: 500; color: #1a1a1a; background: #e8e8e6;
                         border-radius: 8px; text-decoration: none; }
        .action-card a:hover { background: #ffffff; }
        .action-card.info span { margin-bottom: 0; }
        .footer { text-align: center; margin-top: 24px; }
        .footer a { font-size: 13px; color: #a0a0a0; text-decoration: none; }
        .footer a:hover { color: #e8e8e6; }
    </style>
</head>
<body>
    <div class="wrap">
        <h2>No account found</h2>
        <p class="sub">This Google account isn&apos;t linked to an Olira organisation yet.</p>

        <div class="action-card">
            <p>Setting up a new organisation?</p>
            <span>You&apos;ll need an access code from Olira to create your organisation.</span>
            <a href="https://console.olira.ai/signup">Create organisation</a>
        </div>

        <div class="action-card info">
            <p>Joining an existing team?</p>
            <span>Ask your organisation admin to invite you. You&apos;ll receive an email with a link to join.</span>
        </div>

        <div class="footer">
            <a href="javascript:window.close()">Close this window</a>
        </div>
    </div>
</body>
</html>"""

FRAGMENT_BRIDGE_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Completing authentication…</title></head>
<body>
<script>
  const hash = window.location.hash.slice(1);
  if (hash) {
    window.location.replace('/done?' + hash);
  } else {
    document.body.textContent = 'No token received.';
  }
</script>
<p>Completing authentication, please wait…</p>
</body>
</html>"""


def _derive_console_url(mcp_server_url: str) -> str | None:
    """Infer the Console URL from the MCP server URL."""
    try:
        parsed = urlparse(mcp_server_url)
        host = parsed.netloc or parsed.path
        if "mcp-patient-state.dev.olira.ai" in host:
            return "https://console.dev.olira.ai"
        if "mcp-patient-state.stage.olira.ai" in host:
            return "https://console.stage.olira.ai"
        if "mcp-patient-state.olira.ai" in host and "stage" not in host and "dev" not in host:
            return "https://console.olira.ai"
    except Exception:
        pass
    return None


def _derive_api_url(env: str) -> str:
    """Return API base URL for the given env."""
    if env == "prod":
        return "https://app-api.prod.olira.ai/app-api"
    if env == "stage":
        return "https://app-api.stage.olira.ai/app-api"
    if env == "local":
        return "http://localhost:8080/app-api"
    return "https://app-api.dev.olira.ai/app-api"


def _decode_jwt_payload(token: str) -> dict | None:
    """Decode JWT payload (no signature verification). Returns dict or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1].replace("-", "+").replace("_", "/")
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        return json.loads(base64.b64decode(payload_b64).decode())
    except Exception:
        return None


class _ConsoleCallbackHandler(BaseHTTPRequestHandler):
    callback_result: dict | None = None
    callback_event: threading.Event | None = None
    console_url: str | None = None

    def log_message(self, format: str, *args) -> None:
        logger.debug(format, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            body = FRAGMENT_BRIDGE_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/done":
            params = parse_qs(parsed.query)
            access_token = params.get("access_token", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]
            error_description = params.get("error_description", [None])[0]
            console_base = (_ConsoleCallbackHandler.console_url or "").rstrip("/")
            if access_token:
                _ConsoleCallbackHandler.callback_result = {"access_token": access_token, "state": state}
                if console_base:
                    redirect_url = f"{console_base}/cli-login-done"
                    self.send_response(302)
                    self.send_header("Location", redirect_url)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    body = SUCCESS_HTML.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            elif error:
                _ConsoleCallbackHandler.callback_result = {
                    "error": error,
                    "error_description": error_description or "Authentication failed",
                }
                if error == "no_account":
                    body = NO_ACCOUNT_HTML.encode()
                else:
                    body = ERROR_HTML.format(
                        error_message=error_description or "Authentication failed",
                        error_detail=f'<p class="detail">error={error}</p>',
                    ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                _ConsoleCallbackHandler.callback_result = {
                    "error": "no_token",
                    "error_description": "No access_token received",
                }
                body = ERROR_HTML.format(
                    error_message="No token received. Please try running <code>olira login</code> again.",
                    error_detail='<p class="detail">no access_token in callback</p>',
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            if _ConsoleCallbackHandler.callback_event:
                _ConsoleCallbackHandler.callback_event.set()
            return
        self.send_error(404, "Not Found")


class _QuietHTTPServer(HTTPServer):
    """HTTPServer that silently drops BrokenPipeError.

    The fragment-bridge page redirects the browser to /done before the write
    fully completes, causing harmless BrokenPipeErrors that would otherwise
    clutter stderr.

    allow_reuse_address ensures SO_REUSEADDR is set before bind() so the port
    can be reclaimed immediately after a previous run without waiting for
    TIME_WAIT to expire.
    """

    allow_reuse_address = True

    def handle_error(self, request: object, client_address: object) -> None:
        import sys

        if isinstance(sys.exc_info()[1], BrokenPipeError):
            return
        super().handle_error(request, client_address)  # type: ignore[arg-type]


class _ConsoleCallbackServer:
    _DEFAULT_PORT = 9876

    def __init__(self, port: int = _DEFAULT_PORT, timeout: int = 300, console_url: str | None = None):
        self.timeout = timeout
        self.console_url = console_url
        self._server: _QuietHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._callback_event: threading.Event | None = None
        self.port = self._find_port(port)

    def _find_port(self, start: int) -> int:
        """Find an available port by binding to 127.0.0.1 — same address the server will use."""
        for port in range(start, start + 100):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(("127.0.0.1", port))
                    s.listen(1)
                    return port
            except OSError:
                continue
        raise RuntimeError(f"No available port in range {start}-{start + 100}")

    def _run_server(
        self,
        event: threading.Event,
        server_ready: threading.Event | None = None,
        console_url: str | None = None,
    ) -> None:
        _ConsoleCallbackHandler.callback_result = None
        _ConsoleCallbackHandler.callback_event = event
        _ConsoleCallbackHandler.console_url = console_url
        try:
            self._server = _QuietHTTPServer(("127.0.0.1", self.port), _ConsoleCallbackHandler)
            self._server.timeout = 0.5
            if server_ready:
                server_ready.set()
            while not event.is_set():
                self._server.handle_request()
        except Exception as exc:
            logger.error("Callback server error: %s", exc)
        finally:
            if self._server:
                try:
                    self._server.server_close()
                except Exception:
                    pass
            self._server = None

    async def start(self) -> None:
        event = threading.Event()
        server_ready = threading.Event()
        self._callback_event = event
        self._server_thread = threading.Thread(
            target=self._run_server,
            args=(event, server_ready, self.console_url),
            daemon=True,
        )
        self._server_thread.start()
        for _ in range(20):
            await asyncio.sleep(0.1)
            if server_ready.is_set():
                return
        raise RuntimeError("Console callback server failed to start")

    async def wait_for_token(self, nonce: str) -> str:
        if self._callback_event is None:
            raise RuntimeError("Server not started — call start() first")
        event = self._callback_event
        loop = asyncio.get_event_loop()
        start = loop.time()
        while not event.is_set():
            await asyncio.sleep(0.1)
            if loop.time() - start > self.timeout:
                raise ValueError(f"Timeout waiting for Console callback after {self.timeout}s")
        result = _ConsoleCallbackHandler.callback_result
        if not result:
            raise ValueError("No callback result received")
        if "error" in result:
            raise ValueError(f"Callback error: {result['error']} — {result.get('error_description')}")
        received_state = result.get("state")
        if received_state != nonce:
            raise ValueError(f"State mismatch — expected {nonce!r}, got {received_state!r}")
        access_token = result.get("access_token")
        if not access_token:
            raise ValueError("No access_token in callback")
        event.set()
        if self._server_thread:
            self._server_thread.join(timeout=2)
        return access_token

    def get_redirect_uri(self) -> str:
        return f"http://localhost:{self.port}/callback"


class _MCPValidationResult:
    ok: bool
    unreachable: bool

    def __init__(self, ok: bool, unreachable: bool = False):
        self.ok = ok
        self.unreachable = unreachable


async def _validate_token_with_mcp(token: str, mcp_server: str) -> _MCPValidationResult:
    """POST tools/list to MCP to validate the token.
    Returns ok=True on success, ok=False+unreachable=True if the server is down,
    ok=False+unreachable=False if the server explicitly rejected the token.
    """
    import httpx

    url = mcp_server.rstrip("/") + "/mcp"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
            if r.status_code in (401, 403):
                return _MCPValidationResult(ok=False)
            if r.status_code != 200:
                return _MCPValidationResult(ok=False, unreachable=True)
            data = r.json()
            if "error" in data:
                return _MCPValidationResult(ok=False)
            return _MCPValidationResult(ok="result" in data)
    except Exception:
        return _MCPValidationResult(ok=False, unreachable=True)


def run_login(
    env: str | None = None,
    mcp_server: str | None = None,
    console_url: str | None = None,
    port: int = 9100,
) -> int:
    """Run the Console redirect login flow. Returns 0 on success, 1 on error."""
    if not mcp_server and not env:
        print("Error: Either --env (dev|stage|prod) or --mcp-server URL is required.", file=__import__("sys").stderr)
        return 1
    if mcp_server is None:
        if env == "prod":
            mcp_server = "https://mcp-patient-state.olira.ai"
        elif env == "stage":
            mcp_server = "https://mcp-patient-state.stage.olira.ai"
        elif env == "local":
            mcp_server = "http://localhost:8084"
        else:
            mcp_server = "https://mcp-patient-state.dev.olira.ai"
    if console_url is None:
        if env == "local":
            console_url = "http://localhost:3000"
        else:
            console_url = _derive_console_url(mcp_server)
        if not console_url:
            print(
                "Error: Could not infer console URL. Pass --console-url (e.g. http://localhost:3000).",
                file=__import__("sys").stderr,
            )
            return 1
    if env is None:
        if "dev.olira.ai" in mcp_server:
            env = "dev"
        elif "stage.olira.ai" in mcp_server:
            env = "stage"
        elif "localhost" in mcp_server or "127.0.0.1" in mcp_server:
            env = "local"
        else:
            env = "prod"

    async def _do_login() -> int:
        nonce = secrets.token_urlsafe(16)
        handler = _ConsoleCallbackServer(port=port, console_url=console_url)
        await handler.start()
        redirect_uri = handler.get_redirect_uri()
        query = urlencode({"redirect_uri": redirect_uri, "state": nonce})
        login_url = f"{console_url.rstrip('/')}/cli-login?{query}"
        print("Opening browser for authentication…")
        print(f"  {login_url}\n")
        try:
            webbrowser.open(login_url)
        except Exception:
            pass
        print("Waiting for authentication… (press Ctrl+C to cancel)\n")
        try:
            access_token = await handler.wait_for_token(nonce)
        except ValueError as e:
            print(f"Error: {e}", file=__import__("sys").stderr)
            return 1

        result = await _validate_token_with_mcp(access_token, mcp_server)
        if not result.ok:
            if result.unreachable:
                print(f"  Warning: MCP server unreachable ({mcp_server}) — skipping token validation.")
            else:
                print("Error: Token was rejected by MCP server. Login failed.", file=__import__("sys").stderr)
                return 1

        payload = _decode_jwt_payload(access_token)
        identity = "unknown"
        organization = "unknown"
        expires_at = ""
        if payload:
            exp = payload.get("exp")
            if exp is not None:
                from datetime import datetime, timezone

                dt = datetime.fromtimestamp(exp, tz=timezone.utc)
                expires_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        api_server = _derive_api_url(env)

        from olira_cli.api import fetch_member_profile

        profile = fetch_member_profile(api_server, access_token)
        if profile.get("email"):
            parts = [p for p in [profile.get("first_name", ""), profile.get("last_name", "")] if p]
            identity = " ".join(parts) if parts else profile["email"]
        elif payload:
            identity = payload.get("https://olira.ai/email") or payload.get("email") or payload.get("sub", "unknown")

        if profile.get("org_name"):
            organization = profile["org_name"]
        elif payload:
            organization = (
                payload.get("https://olira.ai/organization_name") or payload.get("organization_name") or "unknown"
            )
        creds = {
            "access_token": access_token,
            "mcp_server": mcp_server,
            "api_server": api_server,
            "console_url": console_url,
            "env": env,
            "identity": identity,
            "organization": organization,
            "expires_at": expires_at,
        }
        from olira_cli.credentials import save_credentials

        save_credentials(creds)
        print(f"Logged in as {identity} ({organization})")
        print("  Token saved to ~/.olira/credentials.json")
        if expires_at:
            print(f"  Expires: {expires_at}")
        return 0

    return asyncio.run(_do_login())
