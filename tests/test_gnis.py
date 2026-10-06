"""GNIS place names: the live service, the 2021 archive, and the two together."""

from __future__ import annotations

import hashlib
import json
import os

import httpx
import pytest

from us_places_mcp import datasets, gnis

from .conftest import FIXTURES, call_tool, fixture, md5, raw, route

PA_SLICE = raw("gnis_archive_pa_slice.txt")
WAYNESBURG_FIND = ("Waynesburg", fixture("gnis_find_waynesburg_pa"))
FORT_ZELLAR_FIND = ("Fort Zellar", fixture("gnis_find_fort_zellar_pa"))


# --------------------------------------------------------------------------- #
# Names and classes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("given", "spelled"),
    [
        ("Mt. Hope Cemetery", "Mount Hope Cemetery"),
        ("Mt Hope", "Mount Hope"),
        ("St. Mary's Church", "Saint Marys Church"),
        ("St Mary’s", "Saint Marys"),
        ("Ft Jackson", "Fort Jackson"),
        ("Pt Pleasant", "Point Pleasant"),
        ("Green Mount Cemetery", "Green Mount Cemetery"),
        ("Main St", "Main St"),
    ],
)
def test_names_are_spelled_as_gnis_spells_them(given, spelled):
    assert gnis.search_text(given) == spelled


def test_keys_ignore_case_and_punctuation():
    assert (
        gnis.key("Mt. Zion  cemetery") == gnis.key("MOUNT ZION CEMETERY") == "MOUNT ZION CEMETERY"
    )
    assert gnis.key('"Old Main" Building') == "OLD MAIN BUILDING"
    assert gnis.key("100% _") == "100"
    assert gnis.county_key("Greene County") == gnis.county_key("greene") == "GREENE"


def test_feature_classes():
    assert gnis.feature_class("post office") == "Post Office"
    assert gnis.feature_class("CEMETERY") == "Cemetery"
    assert gnis.feature_class("Graveyard") is None
    assert "Cemetery" in gnis.ARCHIVE_CLASSES and "Cemetery" not in gnis.LIVE_CLASSES
    assert gnis.LIVE_CLASSES & gnis.ARCHIVE_CLASSES == {"Military"}


def test_find_filters_only_from_the_tables():
    params = gnis.find_params("Mount Hope", "PA", "Cemetery")
    assert params["searchText"] == "Mount Hope" and params["contains"] == "true"
    assert "8" not in params["layers"].split(",")
    defs = json.loads(params["layerDefs"])
    assert set(defs) == {str(n) for n in gnis.LIVE_LAYERS}
    assert set(defs.values()) == {"state_alpha='PA' AND gaz_featureclass='Cemetery'"}
    assert "layerDefs" not in gnis.find_params("Mount Hope", None, None)


def test_live_places_are_read_from_points_and_multipoints():
    places = gnis.live_places(fixture("gnis_find_waynesburg_pa"))
    assert len(places) == 5
    town = next(p for p in places if p["class"] == "Populated Place" and p["name"] == "Waynesburg")
    assert town == {
        "name": "Waynesburg",
        "class": "Populated Place",
        "state": "PA",
        "county": "Greene",
        "lat": 39.89647,
        "lon": -80.17923,
        "gnis_id": 1190723,
        "source": "live",
    }
    reservoir = next(p for p in places if p["class"] == "Reservoir")
    assert reservoir["lat"] is not None, "a point geometry, not a multipoint"
    assert gnis.live_places({"error": "x"}) == []


# --------------------------------------------------------------------------- #
# The archive file
# --------------------------------------------------------------------------- #
def test_only_the_states_own_dropped_features_are_read(tmp_path):
    path = tmp_path / "PA.txt"
    path.write_bytes(PA_SLICE)
    rows = gnis.read_archive(path, "PA")
    names = sorted(r[1] for r in rows)
    assert len(rows) == 11
    assert "Waynesburg" not in names, "a populated place is still in the live GNIS"
    assert "Bacon Run" not in names, "so is a stream"
    assert "Arc Corner" not in names, "a Delaware feature listed in the Pennsylvania file"
    assert '"Old Main" Administration Building' in names, "quotes are part of the name"
    fort = next(r for r in rows if r[1] == "Jacksons Fort (historical)")
    assert fort[7] is None and fort[8] is None, "unknown coordinates are not (0, 0)"


def test_an_archive_file_of_another_shape_is_refused(tmp_path):
    path = tmp_path / "PA.txt"
    path.write_text("A|B|C\n1|2|3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="FEATURE_ID"):
        gnis.read_archive(path, "PA")


def test_an_s3_etag_is_checked_whole_or_in_parts(tmp_path):
    small = tmp_path / "small"
    small.write_bytes(PA_SLICE)
    assert "MD5" in datasets.check_s3_etag(small, len(PA_SLICE), md5(PA_SLICE))
    with pytest.raises(datasets.DataError, match="does not match"):
        datasets.check_s3_etag(small, len(PA_SLICE), md5(b"something else"))
    with pytest.raises(datasets.DataError, match="no checksum"):
        datasets.check_s3_etag(small, len(PA_SLICE), "")

    # A 9 MB file uploaded in 8 MiB parts, as USGS's PA file was.
    body = os.urandom(9_000_000)
    big = tmp_path / "big"
    big.write_bytes(body)
    part = 8 * 1024 * 1024
    digests = b"".join(hashlib.md5(body[i : i + part]).digest() for i in range(0, len(body), part))
    etag = f"{hashlib.md5(digests).hexdigest()}-2"
    assert "2 upload parts" in datasets.check_s3_etag(big, len(body), etag)
    with pytest.raises(datasets.DataError):
        datasets.check_s3_etag(big, len(body), f"{md5(body)}-2")


# --------------------------------------------------------------------------- #
# find_place_name
# --------------------------------------------------------------------------- #
async def test_a_cemetery_gnis_dropped_is_found_in_the_archive(served, services, data_dir):
    routes = route(services, archive={"PA": PA_SLICE})
    result = await call_tool("find_place_name", name="Green Mount Cemetery", state="PA")
    assert result["answered_by"] == ["archive_2021"]
    assert result["sources"] == {"live": {"found": 0}, "archive_2021": {"found": 1}}
    [place] = result["places"]
    assert place == {
        "name": "Green Mount Cemetery",
        "class": "Cemetery",
        "state": "PA",
        "county": "Greene",
        "lat": 39.90186,
        "lon": -80.18731,
        "gnis_id": 1176092,
        "source": "archive_2021",
        "topo_quad": "Waynesburg",
    }
    announced = result["downloaded"]
    assert announced["file"] == "PA_Features_20210825.txt"
    assert announced["bytes"] == len(PA_SLICE) and announced["features_loaded"] == 11
    assert announced["verified"].startswith("MD5")
    assert announced["saved_to"] == str(data_dir / "gnis-2021.sqlite")
    assert any("25 August 2021" in n for n in result["notes"])

    again = await call_tool("find_place_name", name="Mount Zion Cemetery", state="PA")
    assert "downloaded" not in again, "a state is downloaded once"
    assert routes["archive"].call_count == 1
    assert [p["topo_quad"] for p in again["places"]] == ["Mather", "Holbrook"]
    assert [p.name for p in data_dir.iterdir()] == ["gnis-2021.sqlite"], "no .part left"


async def test_live_and_archive_together_closest_names_first(served, services):
    route(services, gnis=[WAYNESBURG_FIND], archive={"PA": PA_SLICE})
    result = await call_tool("find_place_name", name="Waynesburg", state="Pennsylvania")
    assert result["answered_by"] == ["live", "archive_2021"]
    assert result["total"] == 7
    names = [(p["name"], p["source"]) for p in result["places"]]
    assert names[0] == ("Waynesburg", "live")
    assert ("Waynesburg Post Office", "archive_2021") in names
    assert ("Waynesburg College", "archive_2021") in names


async def test_a_feature_in_both_is_reported_once_as_live(served, services):
    route(services, gnis=[FORT_ZELLAR_FIND], archive={"PA": PA_SLICE})
    result = await call_tool("find_place_name", name="Fort Zellar", state="PA")
    assert result["sources"]["live"]["found"] == result["sources"]["archive_2021"]["found"] == 1
    assert [(p["gnis_id"], p["source"]) for p in result["places"]] == [(1211876, "live")]
    assert result["total"] == 1


async def test_archive_names_match_whatever_the_spacing(served, services):
    route(services, archive={"PA": PA_SLICE})
    result = await call_tool("find_place_name", name="Greenmount Cemetery", state="PA")
    assert [p["name"] for p in result["places"]] == ["Green Mount Cemetery"]


async def test_the_county_narrows_both_sources(served, services):
    route(services, gnis=[WAYNESBURG_FIND], archive={"PA": PA_SLICE})
    greene = await call_tool(
        "find_place_name", name="Mount Zion", state="PA", county="Greene County"
    )
    assert len(greene["places"]) == 2
    other = await call_tool("find_place_name", name="Waynesburg", state="PA", county="Lebanon")
    assert other["places"] == [] and other["total"] == 0


async def test_a_class_the_live_gnis_holds_skips_the_archive(served, services):
    routes = route(services, gnis=[WAYNESBURG_FIND])
    result = await call_tool(
        "find_place_name", name="Waynesburg", state="PA", feature_class="populated place"
    )
    assert result["feature_class"] == "Populated Place"
    assert result["sources"]["archive_2021"]["searched"] is False
    assert routes["archive"].call_count == 0
    params = routes["gnis"].calls.last.request.url.params
    assert "gaz_featureclass='Populated Place'" in params["layerDefs"]


async def test_a_dropped_class_without_a_state_asks_for_one(served, services):
    routes = route(services)
    result = await call_tool("find_place_name", name="Mount Hope", feature_class="Cemetery")
    assert result["error"] == "no_criteria" and "Pass the state" in result["message"]
    assert routes["gnis"].call_count == routes["archive"].call_count == 0


async def test_without_a_state_only_the_live_gnis_is_searched(served, services):
    routes = route(services, gnis=[WAYNESBURG_FIND])
    result = await call_tool("find_place_name", name="Waynesburg")
    assert result["answered_by"] == ["live"]
    assert "a state at a time" in result["sources"]["archive_2021"]["why"]
    assert routes["archive"].call_count == 0
    assert "layerDefs" not in routes["gnis"].calls.last.request.url.params


async def test_one_source_failing_does_not_hide_the_other(served, services):
    route(services, gnis=[("Green", httpx.Response(503))], archive={"PA": PA_SLICE})
    result = await call_tool("find_place_name", name="Green Mount Cemetery", state="PA")
    assert result["answered_by"] == ["archive_2021"]
    assert result["sources"]["live"]["error"] == "upstream_error"
    assert "not an empty result" in result["sources"]["live"]["message"]


async def test_an_archive_file_that_fails_its_check_is_not_kept(served, services, data_dir):
    bad = httpx.Response(200, content=PA_SLICE, headers={"ETag": f'"{md5(b"other")}"'})
    route(services, archive={"PA": bad})
    result = await call_tool("find_place_name", name="Green Mount Cemetery", state="PA")
    assert result["sources"]["archive_2021"]["error"] == "download_failed"
    assert result["places"] == []
    assert gnis.archive_states(data_dir / gnis.ARCHIVE_DB) == []
    assert not any(p.suffix == ".part" for p in data_dir.iterdir())


async def test_when_every_source_fails_the_tool_says_so(served, services):
    route(services, gnis=[("Green", httpx.Response(500))], archive={})
    result = await call_tool("find_place_name", name="Green Mount Cemetery", state="PA")
    assert result["error"] == "upstream_error"


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"name": " "}, "no_criteria"),
        ({"name": "x"}, "no_criteria"),
        ({"name": "Mount Hope", "state": "Atlantis"}, "invalid_state"),
        ({"name": "Mount Hope", "feature_class": "Graveyard"}, "invalid_feature_class"),
    ],
)
async def test_input_is_checked_before_asking(served, services, args, error):
    routes = route(services)
    assert (await call_tool("find_place_name", **args))["error"] == error
    assert routes["gnis"].call_count == 0


def test_the_fixtures_are_slices_not_the_whole_file():
    assert (FIXTURES / "gnis_archive_pa_slice.txt").stat().st_size < 10_000
