"""US post offices: the Dataverse download, its check, and the local queries."""

from __future__ import annotations

import httpx
import pytest

from us_places_mcp import postoffices

from .conftest import (
    FIXTURES,
    OFFICES_FILE_ID,
    call_tool,
    dataverse_answer,
    fixture,
    md5,
    raw,
    route,
)

SLICE = raw("post_offices_slice.csv")
KINGSBURY_1890 = {"state": "SD", "county": "Kingsbury", "year": 1890}
WAYNESBURG = {"latitude": 39.896, "longitude": -80.179}


def test_the_recorded_dataset_description_is_read():
    entry = postoffices.dataset_file(fixture("dataverse_post_offices"))
    assert entry == {
        "id": OFFICES_FILE_ID,
        "algorithm": "md5",
        "checksum": "72a67b658fdc0befa5a0f48a909cd3dc",
        "size": 31_415_567,
        "version": "1.0",
        "license": "CC0 1.0",
    }


def test_a_description_without_the_file_is_refused():
    answer = fixture("dataverse_post_offices")
    answer["data"]["latestVersion"]["files"] = []
    with pytest.raises(postoffices.DatasetChanged, match="us-post-offices.csv"):
        postoffices.dataset_file(answer)


@pytest.fixture
def db(tmp_path):
    csv = tmp_path / "offices.csv"
    csv.write_bytes(SLICE)
    path = tmp_path / "offices.sqlite"
    assert postoffices.build(csv, path, {"version": "1.0"}) == 42
    return path


def search(db, **criteria):
    options = {
        "name": "",
        "state": None,
        "county": "",
        "point": None,
        "radius_km": 10.0,
        "year": None,
        "limit": 50,
    }
    return postoffices.search(db, **(options | criteria))


def test_kingsbury_county_in_1890(db):
    total, unplaced, offices = search(db, state="SD", county="Kingsbury", year=1890)
    assert (total, unplaced) == (15, 3)
    assert [o["name"] for o in offices][:3] == ["SPRINGLAKE", "DESMET", "IROQUOIS"]
    first = offices[0]
    assert (first["established"], first["discontinued"], first["lat"]) == (1879, 1901, None)
    desmet = offices[1]
    assert desmet["discontinued"] is None, "still open in 2000"
    assert desmet["gnis_match"] == {
        "id": 2709814,
        "class": "Post Office",
        "name": "Desmet Post Office",
        "score": 1.0,
    }


def test_a_county_with_no_year_lists_every_office(db):
    total, _, offices = search(db, state="SD", county="KINGSBURY COUNTY")
    assert total == 33
    assert [o["established"] for o in offices] == sorted(o["established"] for o in offices)


@pytest.mark.parametrize(
    ("name", "found"),
    [
        ("Mt Morris", "MOUNT MORRIS"),
        ("mount morris", "MOUNT MORRIS"),
        ("Waynesburgh", "WAYNESBURG(H)"),
        ("Carmichael's", "CARMICHAEL(')S"),
        ("aaronsburgh", "AARONSBURG(H)"),
    ],
)
def test_names_match_every_spelling_helbock_recorded(db, name, found):
    _, _, offices = search(db, name=name)
    assert [o["name"] for o in offices] == [found]


def test_an_office_on_a_state_line_is_in_both_states(db):
    for state in ("MI", "OH"):
        _, _, offices = search(db, name="Depot", state=state)
        assert [o["state"] for o in offices] == ["MI/OH"]


def test_offices_around_a_point_nearest_first(db):
    total, _, near = search(db, point=(39.896, -80.179), radius_km=5)
    assert total == 1 and near[0]["name"] == "WAYNESBURG(H)"
    assert near[0]["distance_km"] == pytest.approx(0.8, abs=0.2)
    total, _, wider = search(db, point=(39.896, -80.179), radius_km=15)
    assert [o["name"] for o in wider] == ["WAYNESBURG(H)", "ROGERSVILLE", "JEFFERSON"]
    assert [o["distance_km"] for o in wider] == sorted(o["distance_km"] for o in wider)


@pytest.mark.parametrize(("name", "found"), [("De Smet", "DESMET"), ("Spring Lake", "SPRINGLAKE")])
def test_names_match_whatever_the_spacing(db, name, found):
    _, _, offices = search(db, state="SD", name=name)
    assert [o["name"] for o in offices] == [found]


def test_a_slip_in_the_years_is_flagged(db):
    _, _, offices = search(db, state="KS", name="Haysville")
    assert offices[0]["established"] == 185 and offices[0]["date_suspect"] is True
    _, _, fine = search(db, state="SD", name="De Smet")
    assert "date_suspect" not in fine[0]


# --------------------------------------------------------------------------- #
# The tool, with the download
# --------------------------------------------------------------------------- #
async def test_the_first_call_downloads_checks_and_announces(served, services, data_dir):
    routes = route(services, offices=SLICE)
    result = await call_tool("post_offices", **KINGSBURY_1890)
    assert result["total"] == 15 and len(result["offices"]) == 15
    announced = result["downloaded"]
    assert announced["file"] == "us-post-offices.csv"
    assert announced["bytes"] == len(SLICE) and announced["offices"] == 42
    assert announced["verified"] == f"MD5 matches Dataverse's ({md5(SLICE)})"
    assert announced["saved_to"] == str(data_dir / "us-post-offices.sqlite")
    assert "doi:10.7910/DVN/NUKCNA" in announced["what"]
    assert routes["download"].call_count == routes["store"].call_count == 1
    assert "format=original" in str(routes["download"].calls.last.request.url)
    assert "Counties are today's" in result["caution"]
    assert "3 of these have no coordinates" in result["notes"][0]

    again = await call_tool("post_offices", **KINGSBURY_1890)
    assert "downloaded" not in again and again["total"] == 15
    assert routes["dataverse"].call_count == routes["store"].call_count == 1
    assert [p.name for p in data_dir.iterdir()] == ["us-post-offices.sqlite"]


def _describe(routes, change) -> None:
    """Serve Dataverse's recorded description of the slice, altered by ``change``."""
    answer = dataverse_answer(SLICE)
    for entry in answer["data"]["latestVersion"]["files"]:
        if entry["dataFile"]["id"] == OFFICES_FILE_ID:
            change(entry["dataFile"])
    routes["dataverse"].mock(return_value=httpx.Response(200, json=answer))


async def test_a_download_that_fails_its_checksum_is_not_kept(served, services, data_dir):
    routes = route(services, offices=SLICE)
    _describe(routes, lambda f: f["checksum"].update(value=md5(b"something else")))
    result = await call_tool("post_offices", **KINGSBURY_1890)
    assert result["error"] == "download_failed"
    assert "MD5 checksum" in result["message"] and "not an empty result" in result["message"]
    assert list(data_dir.iterdir()) == [], "neither the file nor a database is kept"


async def test_a_download_of_the_wrong_size_is_not_kept(served, services, data_dir):
    routes = route(services, offices=SLICE)
    _describe(routes, lambda f: f.update(originalFileSize=len(SLICE) + 1))
    result = await call_tool("post_offices", **KINGSBURY_1890)
    assert result["error"] == "download_failed" and "bytes" in result["message"]
    assert list(data_dir.iterdir()) == []


async def test_a_dataset_description_that_changed_shape_is_reported(served, services):
    routes = route(services, offices=SLICE)
    _describe(routes, lambda f: f.update(originalFileName="renamed.csv", filename="renamed.tab"))
    result = await call_tool("post_offices", **KINGSBURY_1890)
    assert result["error"] == "download_failed" and "no longer lists" in result["message"]
    assert routes["download"].call_count == 0


async def test_a_point_search_says_what_it_cannot_find(served, services):
    route(services, offices=SLICE)
    result = await call_tool("post_offices", **WAYNESBURG, radius_km=15)
    assert [o["name"] for o in result["offices"]][0] == "WAYNESBURG(H)"
    assert result["criteria"]["radius_km"] == 15
    assert any("two in three" in n for n in result["notes"])


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({}, "no_criteria"),
        ({"county": "Kingsbury"}, "no_criteria"),
        ({"name": "..."}, "no_criteria"),
        ({"state": "Atlantis", "name": "Depot"}, "invalid_state"),
        ({"latitude": 39.9}, "invalid_point"),
        ({**WAYNESBURG, "radius_km": 0}, "invalid_radius"),
        ({**WAYNESBURG, "radius_km": 500}, "invalid_radius"),
        ({"name": "Depot", "year": 1500}, "invalid_date"),
    ],
)
async def test_input_is_checked_before_downloading(served, services, args, error):
    routes = route(services, offices=SLICE)
    assert (await call_tool("post_offices", **args))["error"] == error
    assert routes["dataverse"].call_count == routes["download"].call_count == 0


def test_the_fixture_is_a_slice_not_the_whole_file():
    assert (FIXTURES / "post_offices_slice.csv").stat().st_size < 20_000
