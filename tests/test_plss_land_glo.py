"""PLSS query building and geometry, land-entry classification, and GLO links."""

from __future__ import annotations

import pytest

from us_places_mcp import glo, landfiles, plss

from .conftest import fixture


def test_township_where_pads_and_accepts_the_unpadded_meridian_code():
    where = plss.township_where("ND", "05", 140, "N", 63, "W")
    assert "PRINMERCD IN ('05', '5')" in where
    assert "TWNSHPNO='140'" in where and "RANGENO='063'" in where


def test_subdivision_where_combines_cells_and_lots():
    where = plss.subdivision_where("X", ["NENE", "SENE"], [2])
    assert where == (
        "FRSTDIVID='X' AND (SECDIVLAB IN ('NENE', 'SENE') OR (SECDIVTYP='L' AND GOVLOT IN ('2')))"
    )


def test_extent_of_a_unit_square():
    square = {"geometry": {"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}}
    out = plss.extent([square])
    assert out["centroid"] == {"lat": 0.5, "lon": 0.5}
    assert out["bbox"] == {"south": 0.0, "west": 0.0, "north": 1.0, "east": 1.0}


def test_extent_of_recorded_aliquots_lies_inside_the_section():
    section = plss.extent(plss.features(fixture("plss_section_ia18")))
    half = plss.extent(plss.features(fixture("plss_e2ne_ia18")))
    s, h = section["bbox"], half["bbox"]
    assert s["south"] <= h["south"] and h["north"] <= s["north"]
    assert s["west"] <= h["west"] and h["east"] <= s["east"]
    assert h["west"] > (s["west"] + s["east"]) / 2, "the E½NE is in the east half"


def test_no_geometry_is_no_extent():
    assert plss.extent([{"attributes": {}}]) is None


def test_describe_point_from_a_recorded_row():
    [row] = plss.features(fixture("plss_point_ia"))
    d = plss.describe_point(plss.attributes(row))
    assert (d["township"], d["range"], d["section"], d["subdivision"]) == ("84N", "39W", 18, "SENW")
    assert d["meridian_name"] == "Fifth Principal Meridian"
    assert d["description"] == "SENW Sec. 18, T84N R39W, Fifth Principal Meridian"


@pytest.mark.parametrize(
    ("authority", "kind"),
    [
        ("May 20, 1862: Homestead EntryOriginal (12 Stat. 392)", "homestead"),
        ("April 24, 1820: Sale-Cash Entry (3 Stat. 566)", "cash"),
        ("March 3, 1855: ScripWarrant Act of 1855 (10 Stat. 701)", "military_warrant"),
        ("September 28, 1850: ScripWarrant Act of 1850 (9 Stat. 520)", "military_warrant"),
        ("September 4, 1841: Preemption Act (5 Stat. 453)", "preemption"),
        ("March 3, 1873: Timber Culture Act", "timber_culture"),
        ("March 3, 1877: Desert Land Act", "desert_land"),
        ("September 28, 1850: Swamp Land Grant", "state_grant"),
        ("Something unheard of", "unclassified"),
    ],
)
def test_authorities_are_classified(authority, kind):
    assert landfiles.classify(authority)[0] == kind


def test_a_nebraska_homestead_gets_the_verified_title_pattern():
    """ "Lincoln Land Office (Nebraska), Homestead Final Certificate No. 12018" is NAID 63668992."""
    searches = landfiles.nara_search("homestead", "NE", "Lincoln Land Office", "12018", "")
    assert searches[0] == {
        "record_group_number": "49",
        "title": "Lincoln Land Office (Nebraska), Homestead Final Certificate No. 12018",
    }
    assert searches[1]["level_of_description"] == "series"


def test_a_warrant_searches_the_veteran_s_file():
    [veteran, *_] = landfiles.nara_search("military_warrant", "IA", "", "", "Abraham Lincoln")
    assert veteran["record_group_number"] == "15"


def test_the_verified_glo_search_link_byte_for_byte():
    assert glo.search_link("Abraham  Lincoln") == (
        "https://glorecords.blm.gov/s/advanced-search?searchTerm="
        "%2Fsearch%3Fq%3DAbraham%2BLincoln%26page%3D1%26pageSize%3D25"
    )


def test_glo_filters_are_appended_inside_the_search_term():
    link = glo.search_link("Crothers", "SD", "Patent")
    assert link.endswith("%26State%3DSD%26documenttype%3DPatent")


def test_the_glo_record_permalink():
    assert glo.record_link("6811616370992565615") == (
        "https://glorecords.blm.gov/s/advanced-search#/searchresults?documentid=6811616370992565615"
    )
