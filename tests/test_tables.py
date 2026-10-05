"""The static tables: meridians, states, and which land was federal."""

from __future__ import annotations

import pytest

from us_places_mcp.tables import (
    MERIDIANS,
    SPECIAL_CASES,
    STATE_LAND,
    STATE_MERIDIANS,
    STATE_NAMES,
    meridian_code,
    state_code,
)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("5", "05"),
        ("05", "05"),
        ("5th", "05"),
        ("5th P.M.", "05"),
        ("Fifth Principal Meridian", "05"),
        ("fifth principal", "05"),
        ("Mount Diablo", "21"),
        ("Mt. Diablo Meridian", "21"),
        ("Boise Meridian", "08"),
        ("Gila and Salt River", "14"),
        ("Fourth Principal Meridian Extended", "46"),
        ("Willamette", "33"),
    ],
)
def test_meridians_are_read_in_their_usual_spellings(value, code):
    assert meridian_code(value) == code


@pytest.mark.parametrize("value", ["", "M.D.M.", "Greenwich", "99", "7th"])
def test_an_unknown_meridian_is_none(value):
    assert meridian_code(value) is None


def test_the_service_s_mislabelled_codes_take_this_table_s_names():
    """BLM's data also labels 18 'St. Helena', 27 'Mount Diablo' and 45 'Kateel River'."""
    assert MERIDIANS["18"] == "Louisiana Meridian"
    assert MERIDIANS["27"] == "San Bernardino Meridian"
    assert MERIDIANS["45"] == "Umiat Meridian"


def test_every_state_is_exactly_one_of_public_land_or_state_land():
    public = set(STATE_MERIDIANS)
    state_land = set(STATE_LAND)
    assert public | state_land == set(STATE_NAMES)
    assert public & state_land == set()
    assert len(public) == 30


def test_every_state_meridian_is_in_the_table():
    assert {m for codes in STATE_MERIDIANS.values() for m in codes} <= set(MERIDIANS)


def test_special_cases_are_public_land_states():
    assert set(SPECIAL_CASES) <= set(STATE_MERIDIANS)


@pytest.mark.parametrize(("value", "code"), [("ia", "IA"), ("Iowa", "IA"), (" new york ", "NY")])
def test_states_by_code_or_name(value, code):
    assert state_code(value) == code


@pytest.mark.parametrize("value", ["", "Iowa Territory", "XX", None])
def test_not_a_state(value):
    assert state_code(value) is None
