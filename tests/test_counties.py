"""County-at-date logic over the Newberry atlas, from recorded OpenHistoricalMap answers."""

from __future__ import annotations

from datetime import date

import pytest

from us_places_mcp import counties

from .conftest import fixture


@pytest.mark.parametrize(
    ("text", "first", "last"),
    [
        ("1796", date(1796, 1, 1), date(1796, 12, 31)),
        ("1796-02", date(1796, 2, 1), date(1796, 2, 29)),
        ("1795-02", date(1795, 2, 1), date(1795, 2, 28)),
        ("1796-02-09", date(1796, 2, 9), date(1796, 2, 9)),
    ],
)
def test_a_date_covers_a_period(text, first, last):
    assert counties.period(text) == (first, last)


@pytest.mark.parametrize("text", ["", "96", "1796-13", "1796-02-30", "Feb 1796", "1796/02/09"])
def test_an_unreadable_date_is_none(text):
    assert counties.period(text) is None


@pytest.fixture
def waynesburg() -> list[dict]:
    return counties.versions(fixture("overpass_waynesburg"))


def test_versions_are_oldest_first_and_compact(waynesburg):
    assert len(waynesburg) == 17
    assert waynesburg[0]["county"] == "Pennsylvania County"
    greene = [v for v in waynesburg if v["county"] == "Greene County"]
    assert greene[0]["how"] == "GREENE created from WASHINGTON."
    assert greene[0]["statute"] == "Pa. Stat., ch. 1870, sec. 1/15:380-381"
    assert greene[0]["ahcb_state_file"] == "PA"


def test_a_county_now_in_another_state_is_filed_under_it(waynesburg):
    monongalia = [v for v in waynesburg if v["county"] == "Monongalia County"]
    assert {v["ahcb_state_file"] for v in monongalia} == {"WV"}
    assert "by Virginia" in monongalia[0]["how"]


def test_one_holder_on_a_day(waynesburg):
    holders = counties.held_on(waynesburg, counties.period("1795-06-01"))
    assert [h["county"] for h in holders] == ["Washington County"]
    assert counties.status(holders) == "one"


def test_a_year_with_a_change_returns_both(waynesburg):
    holders = counties.held_on(waynesburg, counties.period("1796"))
    assert [h["county"] for h in holders] == ["Washington County", "Greene County"]
    assert counties.status(holders) == "changed_during_period"


def test_two_governments_claiming_the_spot_is_contested(waynesburg):
    holders = counties.held_on(waynesburg, counties.period("1775"))
    assert {h["ahcb_state_file"] for h in holders} == {"PA", "VA"}
    assert counties.status(holders) == "contested"


def test_versions_of_one_county_are_not_a_change(waynesburg):
    holders = counties.held_on(waynesburg, counties.period("1788-09"))
    assert {h["ahcb_id"] for h in holders} == {"pas_washington"}
    assert counties.status(holders) == "one"


def test_changes_within_a_year_are_listed(waynesburg):
    near = counties.changes_near(waynesburg, counties.period("1795-06-01"))
    assert near == ["1796-02-08", "1796-02-09"]
    assert counties.changes_near(waynesburg, counties.period("1830")) == []


def test_an_attached_non_county_area_names_its_county():
    chain = counties.versions(fixture("overpass_crawford_ia"))
    [holder] = counties.held_on(chain, counties.period("1844"))
    assert holder["county"] == "IA NCA 7"
    assert holder["attached_to"] == "Linn"


def test_nothing_from_another_import_is_kept():
    payload = {
        "elements": [
            {"type": "relation", "id": 1, "tags": {"name": "Somewhere", "admin_level": "6"}}
        ]
    }
    assert counties.versions(payload) == []


def test_the_point_query_rounds_to_about_a_metre():
    q = counties.point_query(39.8960049, -80.1790051)
    assert "is_in(39.89600,-80.17901)" in q
    assert "[admin_level=6]" in q


@pytest.mark.parametrize(
    ("name", "fragment"),
    [
        ("Greene County", '"name"~"^Greene( County'),
        ("St. Charles", '"name"~"^St[.] Charles('),
        ("Prince George's", "Prince George's"),
        ('Evil"];out;rel(1', '"name"~"^Evil[]][;]out[;]rel[(]1('),
    ],
)
def test_history_queries_escape_the_name(name, fragment):
    q = counties.history_query(name, "PA")
    assert fragment in q
    assert '"nl_ahcb:id_text"~"^pas_"' in q
    assert q.count('"') % 2 == 0
