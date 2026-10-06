"""Historical topographic maps: TNM Access answers read, filtered and explained."""

from __future__ import annotations

import httpx
import pytest

from us_places_mcp import topo

from .conftest import call_tool, fixture, raw, route

WAYNESBURG = {"latitude": 39.896, "longitude": -80.179}
TNM = fixture("tnm_topo_waynesburg")


def test_a_point_is_a_bounding_box_of_no_size():
    params = topo.params(39.896, -80.179)
    assert params["bbox"] == "-80.17900,39.89600,-80.17900,39.89600"
    assert params["datasets"] == "Historical Topographic Maps"


def test_scans_are_read_oldest_first():
    maps = topo.scans(TNM)
    assert len(maps) == 16
    first = maps[0]
    assert (first["date"], first["scale"], first["quadrangle"]) == (1901, 62500, "Waynesburg, PA")
    assert first["scan_id"] == 222433 and first["extent"] == "15 x 15 minute"
    assert first["geopdf"].endswith("PA_Waynesburg_222433_1901_62500_geo.pdf")
    assert first["geotiff"].endswith("PA_Waynesburg_222433_1901_62500_geo.tif")
    assert first["preview_jpg"].endswith("_tn.jpg")
    assert [m["date"] for m in maps] == sorted(m["date"] for m in maps)


def test_an_item_that_is_not_a_quadrangle_is_skipped():
    assert topo.scan({"title": "Something else", "urls": {}}) is None
    assert topo.scans({"items": "not a list"}) == []


async def test_every_map_of_a_point(served, services):
    routes = route(services, tnm=TNM)
    result = await call_tool("historical_topo_maps", **WAYNESBURG)
    assert result["covering_this_point"] == result["matching"] == 16
    assert result["scales_here"] == [24000, 62500, 100000, 250000]
    assert result["maps"][0]["date"] == 1901
    assert result["topoview"] == "https://ngmdb.usgs.gov/topoview/viewer/#13/39.8960/-80.1790"
    assert any("later printings" in n for n in result["notes"])
    assert "public domain" in result["source"]
    await call_tool("historical_topo_maps", **WAYNESBURG)
    assert routes["tnm"].call_count == 1, "the second call is served from the cache"


async def test_years_and_scale_filter_without_asking_again(served, services):
    routes = route(services, tnm=TNM)
    early = await call_tool("historical_topo_maps", **WAYNESBURG, year_to=1910, scale=62500)
    assert [(m["date"], m["scan_id"]) for m in early["maps"]] == [
        (1901, 222433),
        (1904, 170082),
        (1904, 170083),
        (1904, 170084),
        (1904, 222435),
        (1904, 222437),
    ]
    late = await call_tool("historical_topo_maps", **WAYNESBURG, year_from=1950, scale=24000)
    assert {m["date"] for m in late["maps"]} == {1961} and late["matching"] == 4
    none = await call_tool("historical_topo_maps", **WAYNESBURG, year_from=1990, scale=62500)
    assert none["maps"] == [] and "None of the maps" in none["notes"][0]
    assert routes["tnm"].call_count == 1


async def test_no_map_covers_the_point(served, services):
    route(services)
    result = await call_tool("historical_topo_maps", latitude=51.5, longitude=-0.12)
    assert result["maps"] == [] and "longitudes are negative" in result["notes"][0]


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"latitude": 39.9, "longitude": 280.0}, "invalid_point"),
        ({**WAYNESBURG, "year_from": 99}, "invalid_date"),
        ({**WAYNESBURG, "year_to": 3000}, "invalid_date"),
        ({**WAYNESBURG, "scale": 12}, "invalid_scale"),
    ],
)
async def test_input_is_checked_before_asking(served, services, args, error):
    routes = route(services)
    assert (await call_tool("historical_topo_maps", **args))["error"] == error
    assert routes["tnm"].call_count == 0


async def test_a_bad_request_reported_inside_a_200_is_named(served, services):
    route(services, tnm=httpx.Response(200, content=raw("tnm_bad_request.txt")))
    result = await call_tool("historical_topo_maps", **WAYNESBURG)
    assert result["error"] == "bad_request"
    assert "must be numeric" in result["message"]
