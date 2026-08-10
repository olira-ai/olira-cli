"""httpx client factory with a test-injection seam.

Every command module gets its client from here instead of calling
httpx.Client() directly, so tests can swap in an httpx.MockTransport without
monkeypatching httpx globally or hitting the network.
"""

from __future__ import annotations

import httpx

_transport: httpx.BaseTransport | None = None


def client(timeout: float = 30.0) -> httpx.Client:
    if _transport is not None:
        return httpx.Client(timeout=timeout, transport=_transport)
    return httpx.Client(timeout=timeout)
