"""The tools, called as a client calls them, against recorded answers."""

from __future__ import annotations

import httpx
import pytest

from us_places_mcp import server
from us_places_mcp.config import Config, ConfigError

from .conftest import call_tool, fixture, raw, route

WAYNESBURG = {"latitude": 39.896, "longitude": -80.179}
IOWA_POINT = {"latitude": 42.0877, "longitude": -95.43}

IA_TOWNSHIP = ((1, "TWNSHPNO='084'"), fixture("plss_township_ia"))
IA_SECTION = ((2, "PLSSID='IA050840N0390W0' AND FRSTDIVNO='18'"), fixture("plss_section_ia18"))
IA_E2NE = ((3, "SECDIVLAB IN ('NENE', 'SENE')"), fixture("plss_e2ne_ia18"))


async def test_county_at_one_holder(served, services):
    route(services, overpass=[("is_in(39.89600,-80.17900)", fixture("overpass_waynesburg"))])
    result = await call_tool("county_at", **WAYNESBURG, date="1795-06-01")
    assert result["status"] == "one"
    assert [h["county"] for h in result["held_by"]] == ["Washington County"]
    assert result["boundary_change_within_a_year"] == ["1796-02-08", "1796-02-09"]
    assert len(result["chain"]) == 17
    assert "Newberry" in result["source"]


async def test_county_at_contested(served, services):
    route(services, overpass=[("is_in(", fixture("overpass_waynesburg"))])
    result = await call_tool("county_at", **WAYNESBURG, date="1775")
    assert result["status"] == "contested"


async def test_county_at_an_attached_area(served, services):
    route(services, overpass=[("is_in(", fixture("overpass_crawford_ia"))])
    result = await call_tool("county_at", **IOWA_POINT, date="1844-06")
    assert result["held_by"][0]["attached_to"] == "Linn"


async def test_county_at_before_any_county(served, services):
    route(services, overpass=[("is_in(", fixture("overpass_crawford_ia"))])
    result = await call_tool("county_at", **IOWA_POINT, date="1790")
    assert result["status"] == "none" and result["held_by"] == []
    assert "No county held this spot" in result["notes"][0]


async def test_county_at_after_the_atlas_ends(served, services):
    route(services, overpass=[("is_in(", fixture("overpass_waynesburg"))])
    result = await call_tool("county_at", **WAYNESBURG, date="2010")
    assert result["held_by"][0]["county"] == "Greene County"
    assert "ends in 2000" in result["notes"][0]


async def test_county_at_outside_the_atlas(served, services):
    route(services)
    result = await call_tool("county_at", latitude=51.5, longitude=-0.12, date="1850")
    assert result["status"] == "no_coverage"


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"latitude": 39.9, "longitude": 280.0, "date": "1795"}, "invalid_point"),
        ({"latitude": 95.0, "longitude": -80.0, "date": "1795"}, "invalid_point"),
        ({**WAYNESBURG, "date": "June 1795"}, "invalid_date"),
    ],
)
async def test_county_at_checks_its_input_before_asking(served, services, args, error):
    routes = route(services)
    assert (await call_tool("county_at", **args))["error"] == error
    assert routes["overpass"].call_count == 0


async def test_county_history(served, services):
    routes = route(
        services, overpass=[('"nl_ahcb:id_text"~"^pas_"', fixture("overpass_history_greene_pa"))]
    )
    result = await call_tool("county_history", county="Greene County", state="Pennsylvania")
    assert [v["from"] for v in result["versions"]] == ["1796-02-09", "1802-01-22"]
    assert routes["overpass"].call_count == 1


async def test_county_history_none_found_explains(served, services):
    route(services)
    result = await call_tool("county_history", county="Nowhere", state="PA")
    assert result["versions"] == [] and "modern state" in result["message"]


async def test_parse_legal_description_tool():
    result = await call_tool("parse_legal_description", text="E½NE Sec. 18, T84N R39W, 5th P.M.")
    assert result["tracts"][0]["quarter_quarters"] == ["NENE", "SENE"]
    assert (await call_tool("parse_legal_description", text="x", state="Atlantis"))["error"] == (
        "invalid_state"
    )


async def test_plss_locate_to_the_aliquot(served, services):
    routes = route(services, plss=[IA_TOWNSHIP, IA_SECTION, IA_E2NE])
    result = await call_tool(
        "plss_locate", state="Iowa", description="E½NE Sec. 18, T84N R39W, 5th P.M."
    )
    [tract] = result["tracts"]
    assert tract["precision"] == "aliquot"
    assert sorted(tract["subdivisions"]) == ["NENE", "SENE"]
    assert tract["gis_acres"] == pytest.approx(81.71, abs=0.1)
    assert 42.08 < tract["centroid"]["lat"] < 42.10
    assert tract["warnings"] == []
    assert routes["plss"].call_count == 3


async def test_plss_locate_a_lot(served, services):
    route(
        services,
        plss=[
            ((1, "STATEABBR='NE'"), fixture("plss_township_ne1n20w")),
            ((2, "FRSTDIVNO='04'"), fixture("plss_section_ne1n20w4")),
            ((3, "GOVLOT IN ('2')"), fixture("plss_lot2_ne1n20w4")),
        ],
    )
    result = await call_tool("plss_locate", state="NE", description="Lot 2 Sec. 4, T1N R20W")
    [tract] = result["tracts"]
    assert tract["precision"] == "lot" and tract["subdivisions"] == ["L 2"]
    assert any("assumed" in w for w in tract["warnings"])


async def test_a_section_held_whole_is_said_so(served, services):
    route(services, plss=[IA_TOWNSHIP, IA_SECTION])
    result = await call_tool(
        "plss_locate", state="IA", description="NWSW Sec. 18, T84N R39W, 5th P.M."
    )
    [tract] = result["tracts"]
    assert tract["precision"] == "section"
    assert "only as a whole" in tract["warnings"][-1]


async def test_a_lotted_section_names_what_it_holds(served, services):
    held = {
        "features": [{"attributes": {"SECDIVLAB": "L 1"}}, {"attributes": {"SECDIVLAB": "SENE"}}]
    }
    route(services, plss=[IA_TOWNSHIP, IA_SECTION, ((3, "SECDIVLAB IS NOT NULL"), held)])
    result = await call_tool(
        "plss_locate", state="IA", description="NENE Sec. 18, T84N R39W, 5th P.M."
    )
    warning = result["tracts"][0]["warnings"][-1]
    assert "It holds L 1, SENE" in warning and "lotted" in warning


async def test_plss_locate_unknown_township(served, services):
    route(services)
    result = await call_tool("plss_locate", state="IA", description="Sec. 1, T999N R1W, 5th P.M.")
    assert result["tracts"][0]["error"] == "not_found"


async def test_plss_locate_refuses_a_state_land_state(served, services):
    routes = route(services)
    result = await call_tool("plss_locate", state="Pennsylvania", description="Sec 4 T1N R20W")
    assert (
        result["error"] == "state_land_state" and "Pennsylvania State Archives" in result["message"]
    )
    assert routes["plss"].call_count == 0


async def test_plss_locate_needs_a_meridian(served, services):
    routes = route(services)
    result = await call_tool("plss_locate", state="SD", description="NENE Sec 1 T1N R1W")
    assert result["tracts"][0]["error"] == "incomplete"
    assert routes["plss"].call_count == 0


async def test_plss_from_point(served, services):
    route(services, plss=[((3, "-95.430000,42.087700"), fixture("plss_point_ia"))])
    result = await call_tool("plss_from_point", **IOWA_POINT)
    assert result["found"] is True
    assert result["description"] == "SENW Sec. 18, T84N R39W, Fifth Principal Meridian"


async def test_plss_from_point_finds_nothing_in_a_state_land_state(served, services):
    routes = route(services)
    result = await call_tool("plss_from_point", **WAYNESBURG)
    assert result["found"] is False
    assert routes["plss"].call_count == 2, "subdivisions first, then townships"


async def test_public_land_state():
    iowa = await call_tool("public_land_state", state="Iowa")
    assert iowa["federal_public_domain"] is True and iowa["meridians"][0]["code"] == "05"
    kentucky = await call_tool("public_land_state", state="KY")
    assert kentucky["federal_public_domain"] is False and "Virginia" in kentucky["first_title_from"]
    ohio = await call_tool("public_land_state", state="OH")
    assert "Western Reserve" in ohio["special_case"]


async def test_find_land_entry_file():
    result = await call_tool(
        "find_land_entry_file",
        authority="May 20, 1862: Homestead EntryOriginal (12 Stat. 392)",
        state="Nebraska",
        land_office="Lincoln",
        certificate_number="12018",
        signature_date="1906-03-01",
    )
    assert result["entry_type"] == "homestead"
    assert result["nara_catalog_searches"][0]["title"] == (
        "Lincoln Land Office (Nebraska), Homestead Final Certificate No. 12018"
    )
    assert result["warnings"] == []


async def test_a_homestead_signed_before_the_act_is_flagged():
    result = await call_tool(
        "find_land_entry_file", authority="Homestead Entry", state="IA", signature_date="1856-05-01"
    )
    assert "1 January 1863" in result["warnings"][0]


async def test_a_certificate_number_is_checked():
    result = await call_tool(
        "find_land_entry_file", authority="Homestead", state="NE", certificate_number="12018; DROP"
    )
    assert result["error"] == "invalid_id"


async def test_glo_links():
    search = await call_tool(
        "glo_links", search_text="Crothers", state="SD", document_category="Patent"
    )
    assert "%26geostatecodes%3DSD%26" in search["url"]
    assert "geostatecodes, 2026-10-06" in search["note"] and "not verified" in search["note"]
    record = await call_tool("glo_links", document_id="6811616370992565615")
    assert record["url"].endswith("documentid=6811616370992565615")
    assert (await call_tool("glo_links", document_id="12; x"))["error"] == "invalid_id"
    assert (await call_tool("glo_links"))["error"] == "no_criteria"


async def test_rate_limiting_is_reported_as_such(served, services):
    route(services, overpass=[("is_in(", httpx.Response(429))])
    result = await call_tool("county_at", **WAYNESBURG, date="1795")
    assert result["error"] == "rate_limited" and "says nothing about the place" in result["message"]


async def test_a_bad_setting_surfaces_on_the_first_call(monkeypatch):
    monkeypatch.setattr(server.holder, "fetcher", None)

    def broken():
        raise ConfigError("US_PLACES_TIMEOUT must be a number; got 'sixty'.")

    monkeypatch.setattr(server, "load_config", broken)
    result = await call_tool("county_at", **WAYNESBURG, date="1795")
    assert result["error"] == "not_configured"


def test_the_allowlist_is_the_configured_hosts_and_dataverses_file_store():
    assert server.hosts(Config()) == {
        "overpass-api.openhistoricalmap.org": 2.0,
        "gis.blm.gov": 0.5,
        "carto.nationalmap.gov": 1.0,
        "tnmaccess.nationalmap.gov": 1.0,
        "prd-tnm.s3.amazonaws.com": 1.0,
        "dataverse.harvard.edu": 1.0,
        "dvn-cloud-iqss.s3.amazonaws.com": 1.0,
    }
    moved = server.hosts(Config(gnis_url="https://names.example.gov/MapServer"))
    assert "names.example.gov" in moved and "carto.nationalmap.gov" not in moved


async def test_cache_status_lists_the_datasets(served, services, data_dir):
    route(services, offices=raw("post_offices_slice.csv"))
    before = await call_tool("cache_status")
    assert before["datasets"]["us_post_offices"] is None
    assert before["datasets"]["directory"] == str(data_dir)
    await call_tool("post_offices", state="SD", county="Kingsbury")
    after = (await call_tool("cache_status"))["datasets"]
    assert after["us_post_offices"]["offices"] == 42
    assert after["us_post_offices"]["version"] == "1.0"
    assert after["gnis_2021_archive"] is None
