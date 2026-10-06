"""Shared fixtures. Every test runs against mocked services; nothing touches the network.

The fixtures under ``fixtures/`` are real answers recorded with the exact
requests the tools send: on 2026-10-05, OpenHistoricalMap's Overpass API (CC0)
and BLM's PLSS map service; on 2026-10-06, USGS's GNIS ``find`` and TNM
Access, and Harvard Dataverse's description of the post-office dataset (all
US government works or CC0). The two data files are slices, byte for byte, of
the real downloads: ``gnis_archive_pa_slice.txt`` holds 14 lines of
``PA_Features_20210825.txt`` and ``post_offices_slice.csv`` 42 rows of
``us-post-offices.csv``. Never the whole of either.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from us_places_mcp import server
from us_places_mcp.config import (
    DATAVERSE_FILE_HOST,
    DEFAULT_DATAVERSE_URL,
    DEFAULT_GNIS_ARCHIVE_URL,
    DEFAULT_GNIS_URL,
    DEFAULT_OVERPASS_URL,
    DEFAULT_PLSS_URL,
    DEFAULT_TNM_URL,
    Config,
)
from us_places_mcp.fetch import Fetcher

FIXTURES = Path(__file__).parent / "fixtures"
OVERPASS_HOST = "overpass-api.openhistoricalmap.org"
PLSS_HOST = "gis.blm.gov"
GNIS_HOST = "carto.nationalmap.gov"
TNM_HOST = "tnmaccess.nationalmap.gov"
ARCHIVE_HOST = "prd-tnm.s3.amazonaws.com"
DATAVERSE_HOST = "dataverse.harvard.edu"
ALL_HOSTS = (
    OVERPASS_HOST,
    PLSS_HOST,
    GNIS_HOST,
    TNM_HOST,
    ARCHIVE_HOST,
    DATAVERSE_HOST,
    DATAVERSE_FILE_HOST,
)
EMPTY_ARCGIS = {"features": []}
EMPTY_FIND = {"results": []}
EMPTY_TNM = {"total": 0, "items": [], "errors": [], "messages": []}

#: The post-office file's id in the recorded Dataverse answer.
OFFICES_FILE_ID = 4491713
OFFICES_DOWNLOAD = f"{DEFAULT_DATAVERSE_URL}/api/access/datafile/{OFFICES_FILE_ID}"
#: Where the mock Dataverse redirects the download, as the real one does.
OFFICES_STORE = f"https://{DATAVERSE_FILE_HOST}/10.7910/DVN/NUKCNA/us-post-offices.orig"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def raw(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def dataverse_answer(csv: bytes) -> dict:
    """The recorded description of the dataset, pointed at a slice of the file.

    Everything is as recorded except the post-office file's checksum and size,
    which become the slice's, because the slice is what the mock serves.
    """
    answer = copy.deepcopy(fixture("dataverse_post_offices"))
    for entry in answer["data"]["latestVersion"]["files"]:
        if entry["dataFile"]["id"] == OFFICES_FILE_ID:
            entry["dataFile"]["checksum"]["value"] = md5(csv)
            entry["dataFile"]["originalFileSize"] = len(csv)
    return answer


def make_fetcher(tmp_path: Path, **kwargs) -> Fetcher:
    options = {"backoff": 0.0}
    options.update(kwargs)
    return Fetcher(tmp_path / "cache", dict.fromkeys(ALL_HOSTS, 0.0), **options)


@pytest.fixture
def served(tmp_path, monkeypatch) -> Fetcher:
    """Install a fast test fetcher as the server's for the duration of a test."""
    fetcher = make_fetcher(tmp_path)
    monkeypatch.setattr(server.holder, "fetcher", fetcher)
    monkeypatch.setattr(server.holder, "config", Config(cache_dir=tmp_path / "cache"))
    return fetcher


@pytest.fixture
def data_dir(served) -> Path:
    """Where the served configuration keeps downloaded datasets."""
    return server.holder.config.data_dir


@pytest.fixture
def services():
    """A respx router; any request it does not expect fails the test."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


def route(
    router: respx.MockRouter,
    overpass=None,
    plss=None,
    gnis=None,
    tnm=None,
    archive=None,
    offices=None,
) -> dict[str, respx.Route]:
    """Answer each service as the real one would, from recorded answers.

    ``overpass``: list of (substring of the query, answer); ``plss``: list of
    ((layer, substring of ``where``), answer); ``gnis``: list of (substring of
    ``searchText``, answer); ``tnm``: one answer for any point. An answer is a
    dict (200 JSON) or an ``httpx.Response``. Unmatched requests get an empty
    answer, which is what the services give for "nothing".

    ``archive``: {state: bytes} served as that state's 2021 file, with the S3
    ETag (an MD5) of those bytes, or {state: httpx.Response}; other states get
    S3's 404. ``offices``: the
    CSV bytes Dataverse serves (by a redirect to its file store, as it does),
    with the recorded dataset description pointed at them.
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

    def on_gnis(request: httpx.Request) -> httpx.Response:
        text = request.url.params.get("searchText") or ""
        for needle, value in gnis or []:
            if needle in text:
                return answer(value)
        return httpx.Response(200, json=EMPTY_FIND)

    def on_archive(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        for state, body in (archive or {}).items():
            if name == f"{state}_Features_20210825.txt":
                if isinstance(body, httpx.Response):
                    return body
                return httpx.Response(200, content=body, headers={"ETag": f'"{md5(body)}"'})
        return httpx.Response(
            404,
            text="<Error><Code>NoSuchKey</Code><Message>The specified key does not exist."
            "</Message></Error>",
        )

    routes = {
        "overpass": router.post(DEFAULT_OVERPASS_URL).mock(side_effect=on_overpass),
        "plss": router.get(url__startswith=DEFAULT_PLSS_URL).mock(side_effect=on_plss),
        "gnis": router.get(f"{DEFAULT_GNIS_URL}/find").mock(side_effect=on_gnis),
        "tnm": router.get(url__startswith=DEFAULT_TNM_URL).mock(
            side_effect=lambda request: answer(tnm if tnm is not None else EMPTY_TNM)
        ),
        "archive": router.get(url__startswith=DEFAULT_GNIS_ARCHIVE_URL).mock(
            side_effect=on_archive
        ),
    }
    if offices is not None:
        routes["dataverse"] = router.get(
            url__startswith=f"{DEFAULT_DATAVERSE_URL}/api/datasets/"
        ).mock(return_value=httpx.Response(200, json=dataverse_answer(offices)))
        routes["download"] = router.get(url__startswith=OFFICES_DOWNLOAD).mock(
            return_value=httpx.Response(303, headers={"Location": OFFICES_STORE})
        )
        routes["store"] = router.get(OFFICES_STORE).mock(
            return_value=httpx.Response(200, content=offices)
        )
    return routes


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
        "invalid_feature_class",
        "invalid_scale",
        "invalid_radius",
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
    "find_place_name": {"name": "Green Mount Cemetery", "state": "PA"},
    "historical_topo_maps": {"latitude": 39.896, "longitude": -80.179},
    "post_offices": {"state": "SD", "county": "Kingsbury", "year": 1890},
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
