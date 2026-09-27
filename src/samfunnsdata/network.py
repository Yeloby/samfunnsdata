"""The application's synchronous HTTP boundary. No persistent request log.

Mode is process-wide and consulted before every HTTP hop. Requests already
admitted may finish; switching mode is not socket cancellation or an OS firewall.
Observations are operation-local (ContextVar), including on GUI worker threads.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from threading import Lock
from urllib.parse import urljoin, urlsplit

import httpx

from .help import application_version


class NetworkMode(StrEnum):
    ONLINE = "online"
    CACHE_ONLY = "cache_only"


HOSTS = {
    "norges_bank": frozenset({"data.norges-bank.no"}),
    "ssb": frozenset({"data.ssb.no"}),
    "nav": frozenset({"www.nav.no"}),
    "elections": frozenset({"valgresultat.no"}),
    "fhi": frozenset({"statistikk-data.fhi.no"}),
    "vegvesen": frozenset({
        "www.vegvesen.no",
        "nvdbapiles-v3.atlas.vegvesen.no",
        "trafikkdata-api.atlas.vegvesen.no",
        "trafikkdata.atlas.vegvesen.no",
    }),
}
LABELS = {
    "norges_bank": "Norges Bank",
    "ssb": "SSB",
    "nav": "NAV",
    "elections": "Valgdirektoratet",
    "fhi": "FHI",
    "vegvesen": "Statens vegvesen",
}
_mode = NetworkMode.ONLINE
_mode_lock = Lock()
_records = ContextVar("network_records", default=None)


class NetworkError(ValueError):
    """Safe, source-aware user message; never includes a backend error/URL."""


class CacheOnlyMiss(NetworkError):
    pass


class DestinationNotAllowed(NetworkError):
    pass


class SourceNetworkError(NetworkError):
    pass


class SourceTimeout(SourceNetworkError):
    pass


class SourceHTTPError(NetworkError, httpx.HTTPStatusError):
    """Preserve HTTPStatusError compatibility using sanitized debug objects."""

    def __init__(self, source, method, origin, status):
        request = httpx.Request(method, origin)
        response = httpx.Response(status, request=request)
        httpx.HTTPStatusError.__init__(
            self, f"{LABELS[source]} svarte med HTTP {status}. Prøv igjen senere.",
            request=request, response=response,
        )


@dataclass(frozen=True)
class RequestRecord:
    source: str
    purpose: str
    method: str
    requested_host: str | None
    requested_url: str | None
    final_host: str | None
    final_url: str | None
    started_at: str
    completed_at: str
    network_mode: str
    cache_relationship: str
    free_text: bool
    network_occurred: bool
    success: bool
    response_status: int | None
    failure: str | None


def set_mode(mode):
    global _mode
    mode = NetworkMode(mode)
    with _mode_lock:
        _mode = mode


def get_mode():
    with _mode_lock:
        return _mode


@contextmanager
def observe_requests():
    records = []
    token = _records.set(records)
    try:
        yield records
    finally:
        _records.reset(token)


def _origin(url):
    """Origins only: drop paths, query, fragments and userinfo (even on errors)."""
    try:
        parsed = urlsplit(str(url))
        host = parsed.hostname
        return host, f"https://{host}" if host else None
    except ValueError:
        return None, None


def validate_destination(source, url):
    try:
        parsed = urlsplit(str(url))
        valid = (parsed.scheme == "https" and parsed.hostname in HOSTS.get(source, ())
                 and parsed.port in (None, 443) and not parsed.username
                 and not parsed.password and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise DestinationNotAllowed(
            f"{LABELS.get(source, 'Ukjent kilde')}: nettadressen er ikke godkjent. Ingen forespørsel til denne adressen ble sendt."
        )


def request(source, purpose, method, url, *, timeout=30.0, params=None,
            json=None, follow_redirects=False, free_text=False, cache_relationship="miss"):
    """GET/POST only; caller cannot inject headers, cookies, auth or a new host.

    Top-level HTTPX calls intentionally retain finite per-call client lifetimes.
    There is no shared cookie jar or persistent client to race at shutdown.
    Same approved HTTPS host only, up to five explicitly validated redirects.
    """
    if method not in ("GET", "POST"):
        raise NetworkError("Bare GET og POST støttes.")
    if not isinstance(timeout, (float, int)) or not isfinite(timeout) or timeout <= 0:
        raise NetworkError("Nettverkskall krever en positiv, endelig tidsavbruddsgrense.")
    started = datetime.now(UTC).isoformat()
    mode = get_mode()
    requested_host, requested_url = _origin(url)
    final_host = final_url = None
    occurred, success, status, failure = False, False, None, None
    current_url, current_method = url, method
    try:
        for hop in range(6):
            # Admission is a short critical section, not a lock over blocking IO.
            mode = get_mode()
            if mode == NetworkMode.CACHE_ONLY:
                raise CacheOnlyMiss(
                    f"{LABELS.get(source, 'Kilden')}: nødvendige data finnes ikke i lokal cache. "
                    "Kun lokal cache er valgt; tillat nettilgang for å hente data."
                )
            validate_destination(source, current_url)
            if hop and not follow_redirects:
                raise DestinationNotAllowed(f"{LABELS[source]}: omdirigering er ikke tillatt for dette kildekallet.")
            final_host, final_url = _origin(current_url)
            headers = {"User-Agent": f"Samfunnsdata/{application_version()}"}
            occurred = True
            if current_method == "GET":
                kwargs = {"params": params} if params is not None else {}
                response = httpx.get(current_url, timeout=timeout, headers=headers,
                                     follow_redirects=False, **kwargs)
            else:
                response = httpx.post(current_url, json=json, timeout=timeout, headers=headers,
                                      follow_redirects=False)
            status = response.status_code
            if response.is_redirect:
                if not follow_redirects:
                    raise DestinationNotAllowed(f"{LABELS[source]}: omdirigering er ikke tillatt for dette kildekallet.")
                location = response.headers.get("location")
                response.close()
                if not location or hop == 5:
                    raise SourceNetworkError(f"{LABELS[source]}: ugyldig eller for lang omdirigering.")
                current_url = urljoin(str(response.url), location)
                params = None  # do not duplicate parameters on redirected URLs
                if status == 303 or (status in (301, 302) and current_method == "POST"):
                    current_method, json = "GET", None
                continue
            if not 200 <= status < 300:
                response.close()
                raise SourceHTTPError(source, current_method, final_url, status)
            success = True
            return response
    except httpx.TimeoutException:
        failure = "SourceTimeout"
        raise SourceTimeout(f"{LABELS.get(source, 'Kilden')}: tidsavbrudd. Prøv igjen senere.") from None
    except httpx.RequestError:
        failure = "SourceNetworkError"
        raise SourceNetworkError(f"{LABELS.get(source, 'Kilden')}: nettverksfeil. Kontroller forbindelsen og prøv igjen.") from None
    except NetworkError as error:
        failure = type(error).__name__
        raise
    finally:
        record = RequestRecord(source, purpose, method, requested_host, requested_url,
                               final_host, final_url, started, datetime.now(UTC).isoformat(),
                               mode.value, cache_relationship, free_text, occurred, success, status, failure)
        records = _records.get()
        if records is not None:
            records.append(record)
        if success:
            response.extensions["samfunnsdata_request"] = record
