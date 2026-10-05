"""Shared fixtures. Every test runs against mocked services; nothing touches the network.

The fixtures under ``fixtures/`` are real answers recorded on 2026-10-05 with
the exact requests the tools send: OpenHistoricalMap's Overpass API (CC0) and
BLM's PLSS map service (US government work).
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from us_places_mcp import server
from us_places_mcp.config import DEFAULT_OVERPASS_URL, DEFAULT_PLSS_URL, Config
from us_places_mcp.fetch import Fetcher

FIXTURES = Path(__file__).parent / "fixtures"
OVERPASS_HOST = "overpass-api.openhistoricalmap.org"
PLSS_HOST = "gis.blm.gov"
EMPTY_ARCGIS = {"features": []}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def make_fetcher(tmp_path: Path, **kwargs) -> Fetcher:
    options = {"backoff": 0.0}
    options.update(kwargs)
    return Fetcher(tmp_path / "cache", {OVERPASS_HOST: 0.0, PLSS_HOST: 0.0}, **options)


@pytest.fixture
def served(tmp_path, monkeypatch) -> Fetcher:
    """Install a fast test fetcher as the server's for the duration of a test."""
    fetcher = make_fetcher(tmp_path)
    monkeypatch.setattr(server.holder, "fetcher", fetcher)
    monkeypatch.setattr(server.holder, "config", Config(cache_dir=tmp_path / "cache"))
    return fetcher


@pytest.fixture
def services():
    """A respx router; any request it does not expect fails the test."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


def route(router: respx.MockRouter, overpass=None, plss=None) -> dict[str, respx.Route]:
    """Answer Overpass by a substring of the query, PLSS by layer and a substring of ``where``.

    ``overpass``: list of (substring, answer); ``plss``: list of ((layer, substring),
    answer). An answer is a dict (200 JSON) or an ``httpx.Response``. Unmatched
    requests get an empty answer, which is what the services give for "nothing".
    """

    def answer(value):
        return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)

    def on_overpass(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.content.decode())["data"][0]
        for needle, value in overpass or []:
            if needle in query:
                return answer(value)
        return httpx.Response(200, json={"elements": []})

    def on_plss(request: httpx.Request) -> httpx.Response:
        layer = int(request.url.path.rstrip("/").split("/")[-2])
        where = request.url.params.get("where") or request.url.params.get("geometry") or ""
        for (want_layer, needle), value in plss or []:
            if layer == want_layer and needle in where:
                return answer(value)
        return httpx.Response(200, json=EMPTY_ARCGIS)

    return {
        "overpass": router.post(DEFAULT_OVERPASS_URL).mock(side_effect=on_overpass),
        "plss": router.get(url__startswith=DEFAULT_PLSS_URL).mock(side_effect=on_plss),
    }


async def call_tool(tool_name: str, /, **arguments) -> dict:
    """Invoke a tool the way a client does, so Field defaults are resolved."""
    result = await server.mcp.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)


#: Errors a tool returns from its own input checks, before any work.
LOCAL_VALIDATION_ERRORS = frozenset(
    {
        "no_criteria",
        "invalid_point",
        "invalid_date",
        "invalid_state",
        "invalid_id",
        "state_land_state",
    }
)

#: Arguments that carry each tool past its own checks.
VALID_ARGS = {
    "county_at": {"latitude": 39.896, "longitude": -80.179, "date": "1795"},
    "county_history": {"county": "Greene", "state": "PA"},
    "parse_legal_description": {"text": "E½NE Sec. 18, T84N R39W, 5th P.M."},
    "plss_locate": {"state": "IA", "description": "E½NE Sec. 18, T84N R39W, 5th P.M."},
    "plss_from_point": {"latitude": 42.0877, "longitude": -95.43},
    "public_land_state": {"state": "IA"},
    "find_land_entry_file": {"authority": "May 20, 1862: Homestead Entry", "state": "NE"},
    "glo_links": {"search_text": "Abraham Lincoln"},
    "cache_status": {},
}

#: Tools that make no network call.
OFFLINE_TOOLS = {
    "parse_legal_description",
    "public_land_state",
    "find_land_entry_file",
    "glo_links",
    "cache_status",
}


def assert_reached_body(tool_name: str, result) -> None:
    """Fail if a sweep stopped at input validation instead of the tool's body."""
    if isinstance(result, dict) and result.get("error") in LOCAL_VALIDATION_ERRORS:
        raise AssertionError(
            f"{tool_name} rejected the sweep's arguments with {result['error']!r}; "
            f"update VALID_ARGS. Message: {result.get('message')!r}"
        )
