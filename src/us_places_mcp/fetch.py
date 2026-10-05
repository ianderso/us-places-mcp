"""A cached, paced HTTP client for the two public services this server reads.

* **Two hosts.** A request hook refuses any host but OpenHistoricalMap's
  Overpass API and BLM's PLSS map service, so nothing a model passes in can
  make the server fetch another site.
* **One request at a time per host,** with a courtesy gap: Overpass runs on
  donated capacity and publishes no rate limit.
* **Identical concurrent calls share one request.**
* **Answers are cached on disk,** keyed by host, path and canonical
  parameters, for a time each caller chooses. A failure is never cached.

Both services can report an error inside a 200 response: ArcGIS as
``{"error": {...}}``, Overpass as a ``remark`` naming a runtime error. Those
are raised like any other failure, so they are never cached as answers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import __version__

logger = logging.getLogger("us_places_mcp.fetch")

#: Where the project lives; named in the User-Agent.
PROJECT_URL = "https://github.com/ianderso/us-places-mcp"

#: Cache lifetimes, in seconds.
DAY = 86_400.0
FOREVER: float | None = None


class UpstreamError(RuntimeError):
    """A request a service refused, or that could not be completed.

    ``status`` is the HTTP status, or 0 when no response arrived at all.
    """

    def __init__(self, status: int, detail: str, *, host: str):
        self.status = status
        self.detail = detail
        self.host = host
        super().__init__(f"{host} -> {status or 'no response'}: {detail}")


class HostNotAllowed(RuntimeError):
    """Raised when a request is aimed at a host this server does not read."""


def user_agent(contact: str = "") -> str:
    """The User-Agent sent with every request, naming this project."""
    extra = f"; {contact}" if contact else ""
    return f"us-places-mcp/{__version__} (+{PROJECT_URL}{extra})"


class Fetcher:
    """Cached, paced async client for a fixed set of hosts.

    Parameters
    ----------
    cache_dir : Path
        Directory for cached responses. Created on first write.
    intervals : dict of str to float
        The allowed hosts, each with the least time between the starts of two
        live requests to it.
    timeout : float, optional
        Per-request timeout in seconds.
    contact : str, optional
        Appended to the User-Agent.
    retries : int, optional
        Further attempts after a 429, a 5xx, or no response.
    backoff : float, optional
        Base of the exponential wait between attempts, in seconds.
    """

    def __init__(
        self,
        cache_dir: Path,
        intervals: dict[str, float],
        *,
        timeout: float = 60.0,
        contact: str = "",
        retries: int = 3,
        backoff: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._cache_dir = cache_dir
        self._intervals = dict(intervals)
        self._retries = retries
        self._backoff = backoff
        self._clock = clock
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent(contact), "Accept": "application/json"},
            event_hooks={"request": [self._only_allowed_hosts]},
            follow_redirects=False,
            transport=transport,
        )
        self._locks = {host: asyncio.Lock() for host in self._intervals}
        self._last_start: dict[str, float] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self.live_calls = 0
        self.cache_hits = 0
        self.shared_waits = 0

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _only_allowed_hosts(self, request: httpx.Request) -> None:
        if request.url.host not in self._intervals:
            raise HostNotAllowed(
                f"refusing a request to {request.url.host!r}: this server only reads "
                f"{', '.join(sorted(self._intervals))}"
            )

    async def get_json(
        self, url: str, params: dict[str, Any], *, ttl: float | None, refresh: bool = False
    ) -> Any:
        """GET ``url`` with query ``params`` and return decoded JSON, cached."""
        return await self._cached("GET", url, params, ttl=ttl, refresh=refresh)

    async def post_form_json(
        self, url: str, form: dict[str, str], *, ttl: float | None, refresh: bool = False
    ) -> Any:
        """POST ``form`` to ``url`` and return decoded JSON, cached."""
        return await self._cached("POST", url, form, ttl=ttl, refresh=refresh)

    async def _cached(
        self, method: str, url: str, params: dict, *, ttl: float | None, refresh: bool
    ) -> Any:
        host = urlsplit(url).hostname or ""
        if host not in self._intervals:
            raise HostNotAllowed(f"refusing a request to {host!r}")
        key = _key(method, url, params)
        if not refresh:
            cached = self._cache_get(key, ttl)
            if cached is not None:
                self.cache_hits += 1
                return cached
        if (pending := self._inflight.get(key)) is not None:
            self.shared_waits += 1
            return await asyncio.shield(pending)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            data = await self._fetch(method, url, host, params)
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            future.exception()  # retrieved: nobody else may be waiting
            raise
        else:
            future.set_result(data)
            self._cache_put(key, data)
            return data
        finally:
            self._inflight.pop(key, None)

    async def _fetch(self, method: str, url: str, host: str, params: dict) -> Any:
        attempt = 0
        while True:
            response: httpx.Response | None = None
            detail = ""
            async with self._locks[host]:
                await self._pace(host)
                self._last_start[host] = self._clock()
                self.live_calls += 1
                try:
                    if method == "GET":
                        response = await self._http.get(url, params=params)
                    else:
                        response = await self._http.post(url, data=params)
                except httpx.TransportError as exc:
                    detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
            if response is not None:
                if response.status_code < 400:
                    return _decode(response, host)
                detail = _detail(response)
            status = response.status_code if response is not None else 0
            if not (status == 0 or status == 429 or status >= 500) or attempt >= self._retries:
                raise UpstreamError(status, detail, host=host)
            attempt += 1
            wait = self._backoff * 2 ** (attempt - 1) + random.uniform(0, self._backoff / 2)
            logger.info("%s -> %s; retry %d in %.1fs", host, status or "no response", attempt, wait)
            await self._sleep(wait)

    async def _pace(self, host: str) -> None:
        last = self._last_start.get(host)
        if last is None:
            return
        wait = self._intervals[host] - (self._clock() - last)
        if wait > 0:
            await self._sleep(wait)

    def _cache_get(self, key: str, ttl: float | None) -> Any:
        path = self._cache_dir / f"{key}.json"
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, ValueError):
            logger.warning("discarding unreadable cache entry %s", path.name)
            return None
        if not isinstance(entry, dict) or "data" not in entry:
            return None
        stored = entry.get("stored")
        if ttl is not None and (not isinstance(stored, int | float) or time.time() - stored > ttl):
            return None
        return entry["data"]

    def _cache_put(self, key: str, data: Any) -> None:
        try:
            _write_atomically(
                self._cache_dir / f"{key}.json", json.dumps({"stored": time.time(), "data": data})
            )
        except OSError:
            logger.warning("could not write the response cache in %s", self._cache_dir)


def _key(method: str, url: str, params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{method} {url}\n{canonical}".encode()).hexdigest()[:24]


def _decode(response: httpx.Response, host: str) -> Any:
    try:
        data = response.json()
    except ValueError:
        raise UpstreamError(502, "the answer was not JSON", host=host) from None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            message = err.get("message") or "the service reported an error"
            details = err.get("details")
            if isinstance(details, list) and details:
                message = f"{message}: {'; '.join(str(d) for d in details)}"
            code = err.get("code")
            raise UpstreamError(code if isinstance(code, int) else 400, message, host=host)
        remark = data.get("remark")
        if isinstance(remark, str) and "error" in remark.lower():
            # Overpass reports a timeout or an out-of-memory abort this way.
            raise UpstreamError(504, remark.strip(), host=host)
    return data


def _detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        text = " ".join(response.text.split())
        return text[:300] or response.reason_phrase
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or response.reason_phrase)
        if isinstance(err, str):
            return err
    return response.reason_phrase


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
