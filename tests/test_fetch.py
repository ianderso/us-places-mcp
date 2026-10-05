"""The HTTP layer: allowed hosts, caching, pacing, retries and in-band errors."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from us_places_mcp import __version__
from us_places_mcp.config import DEFAULT_OVERPASS_URL, DEFAULT_PLSS_URL
from us_places_mcp.fetch import PROJECT_URL, HostNotAllowed, UpstreamError, user_agent

from .conftest import make_fetcher

PLSS_Q = f"{DEFAULT_PLSS_URL}/1/query"


async def test_a_request_to_any_other_host_is_refused(tmp_path):
    fetcher = make_fetcher(tmp_path)
    with pytest.raises(HostNotAllowed):
        await fetcher.get_json("https://researchworks.oclc.org/x", {}, ttl=None)
    with pytest.raises(HostNotAllowed):
        await fetcher._http.get("https://example.org/")


async def test_the_user_agent_names_the_project(tmp_path, services):
    route = services.get(PLSS_Q).mock(return_value=httpx.Response(200, json={"features": []}))
    await make_fetcher(tmp_path).get_json(PLSS_Q, {"where": "1=1"}, ttl=None)
    assert route.calls.last.request.headers["user-agent"] == (
        f"us-places-mcp/{__version__} (+{PROJECT_URL})"
    )
    assert user_agent("me@example.org").endswith("; me@example.org)")


async def test_a_repeat_is_served_from_the_cache(tmp_path, services):
    route = services.get(PLSS_Q).mock(return_value=httpx.Response(200, json={"features": []}))
    fetcher = make_fetcher(tmp_path)
    await fetcher.get_json(PLSS_Q, {"where": "a", "f": "json"}, ttl=None)
    await fetcher.get_json(PLSS_Q, {"f": "json", "where": "a"}, ttl=None)
    assert route.call_count == 1 and (fetcher.live_calls, fetcher.cache_hits) == (1, 1)


async def test_an_expired_entry_is_fetched_again(tmp_path, services):
    route = services.post(DEFAULT_OVERPASS_URL).mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    fetcher = make_fetcher(tmp_path)
    await fetcher.post_form_json(DEFAULT_OVERPASS_URL, {"data": "q"}, ttl=60)
    for entry in fetcher.cache_dir.glob("*.json"):
        data = json.loads(entry.read_text())
        data["stored"] = time.time() - 120
        entry.write_text(json.dumps(data))
    await fetcher.post_form_json(DEFAULT_OVERPASS_URL, {"data": "q"}, ttl=60)
    assert route.call_count == 2


async def test_refresh_bypasses_the_cache(tmp_path, services):
    route = services.get(PLSS_Q).mock(return_value=httpx.Response(200, json={"features": []}))
    fetcher = make_fetcher(tmp_path)
    await fetcher.get_json(PLSS_Q, {"where": "a"}, ttl=None)
    await fetcher.get_json(PLSS_Q, {"where": "a"}, ttl=None, refresh=True)
    assert route.call_count == 2


async def test_an_arcgis_error_inside_a_200_is_an_error_and_not_cached(tmp_path, services):
    services.get(PLSS_Q).mock(
        return_value=httpx.Response(
            200,
            json={
                "error": {
                    "code": 400,
                    "message": "Unable to complete operation.",
                    "details": ["bad where"],
                }
            },
        )
    )
    fetcher = make_fetcher(tmp_path)
    with pytest.raises(UpstreamError) as caught:
        await fetcher.get_json(PLSS_Q, {"where": "x"}, ttl=None)
    assert caught.value.status == 400 and "bad where" in caught.value.detail
    assert list(fetcher.cache_dir.glob("*.json")) == []


async def test_an_overpass_runtime_error_remark_is_an_outage(tmp_path, services):
    services.post(DEFAULT_OVERPASS_URL).mock(
        return_value=httpx.Response(
            200, json={"elements": [], "remark": 'runtime error: Query timed out in "query"'}
        )
    )
    with pytest.raises(UpstreamError) as caught:
        await make_fetcher(tmp_path).post_form_json(DEFAULT_OVERPASS_URL, {"data": "q"}, ttl=None)
    assert caught.value.status == 504


async def test_a_busy_overpass_is_retried(tmp_path, services):
    answers = iter(
        [httpx.Response(429), httpx.Response(504), httpx.Response(200, json={"elements": []})]
    )
    route = services.post(DEFAULT_OVERPASS_URL).mock(side_effect=lambda r: next(answers))
    data = await make_fetcher(tmp_path).post_form_json(
        DEFAULT_OVERPASS_URL, {"data": "q"}, ttl=None
    )
    assert data == {"elements": []} and route.call_count == 3


async def test_persistent_failure_gives_up(tmp_path, services):
    route = services.get(PLSS_Q).mock(return_value=httpx.Response(503, text="down"))
    with pytest.raises(UpstreamError) as caught:
        await make_fetcher(tmp_path, retries=1).get_json(PLSS_Q, {"where": "x"}, ttl=None)
    assert caught.value.status == 503 and route.call_count == 2


async def test_each_host_is_paced_on_its_own(tmp_path, services):
    now = [0.0]
    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    services.get(PLSS_Q).mock(return_value=httpx.Response(200, json={"features": []}))
    services.post(DEFAULT_OVERPASS_URL).mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    from us_places_mcp.fetch import Fetcher

    fetcher = Fetcher(
        tmp_path / "c",
        {"overpass-api.openhistoricalmap.org": 2.0, "gis.blm.gov": 0.5},
        clock=lambda: now[0],
        sleep=fake_sleep,
    )
    await fetcher.post_form_json(DEFAULT_OVERPASS_URL, {"data": "a"}, ttl=None)
    await fetcher.get_json(PLSS_Q, {"where": "a"}, ttl=None)  # another host: no wait
    await fetcher.post_form_json(DEFAULT_OVERPASS_URL, {"data": "b"}, ttl=None)
    assert waits == [pytest.approx(2.0)]


async def test_identical_concurrent_calls_share_one_request(tmp_path, services):
    gate = asyncio.Event()

    async def slow(request):
        await gate.wait()
        return httpx.Response(200, json={"features": []})

    route = services.get(PLSS_Q).mock(side_effect=slow)
    fetcher = make_fetcher(tmp_path)
    one = asyncio.create_task(fetcher.get_json(PLSS_Q, {"where": "a"}, ttl=None))
    two = asyncio.create_task(fetcher.get_json(PLSS_Q, {"where": "a"}, ttl=None))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    gate.set()
    assert await one == await two
    assert route.call_count == 1 and fetcher.shared_waits == 1
