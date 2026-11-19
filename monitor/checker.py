"""One HTTP check per site: status code, response time, expected text and TLS certificate expiry."""
from __future__ import annotations

import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from typing import Callable, Optional
from urllib.parse import urlparse

USER_AGENT = "uptime-monitor/1.0 (+https://github.com/Siddhanth-Mani/uptime-monitor)"
MAX_BODY_BYTES = 512 * 1024  # enough to find the expected text without downloading huge pages


@dataclass
class CheckResult:
    ts: int                      # unix time of the check (seconds)
    ok: bool
    status: Optional[int]        # HTTP status code, None if no response
    ms: Optional[int]            # response time in milliseconds, None if no response
    error: Optional[str]         # short human-readable reason when not ok
    cert_days: Optional[int]     # days until the TLS certificate expires (https only)

    def to_dict(self) -> dict:
        return asdict(self)


def _classify(exc: BaseException) -> str:
    """Turn a network exception into a short reason a person can act on."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "Timed out"
    if isinstance(reason, socket.gaierror):
        return "DNS lookup failed"
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "TLS certificate invalid"
    if isinstance(reason, ssl.SSLError):
        return "TLS error"
    if isinstance(reason, ConnectionRefusedError):
        return "Connection refused"
    if isinstance(reason, ConnectionResetError):
        return "Connection reset"
    return type(reason).__name__


def cert_days_left(host: str, port: int = 443, timeout: float = 10.0) -> Optional[int]:
    """Days until the server's certificate expires, or None if it can't be read."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                not_after = tls.getpeercert()["notAfter"]
    except (OSError, ssl.SSLError, KeyError):
        return None
    return int((ssl.cert_time_to_seconds(not_after) - time.time()) // 86400)


def _fetch_once(url: str, expect: Optional[str], timeout: float) -> tuple[bool, Optional[int], Optional[int], Optional[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_BODY_BYTES)
            ms = int((time.perf_counter() - start) * 1000)
            status = resp.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return False, exc.code, int((time.perf_counter() - start) * 1000), _classify(exc)
    except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
        return False, None, None, _classify(exc)
    if expect and expect.encode("utf-8") not in body:
        return False, status, ms, "Expected text missing"
    return True, status, ms, None


def check_site(
    url: str,
    expect: Optional[str] = None,
    timeout: float = 15.0,
    retry_delay: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    cert_lookup: Callable[[str], Optional[int]] = cert_days_left,
) -> CheckResult:
    """Check a site, retrying once so a single dropped packet isn't reported as an outage."""
    ok, status, ms, error = _fetch_once(url, expect, timeout)
    if not ok:
        sleep(retry_delay)
        ok, status, ms, error = _fetch_once(url, expect, timeout)

    parsed = urlparse(url)
    cert = cert_lookup(parsed.hostname) if parsed.scheme == "https" and parsed.hostname else None
    return CheckResult(ts=int(time.time()), ok=ok, status=status, ms=ms, error=error, cert_days=cert)
