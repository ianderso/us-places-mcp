"""Reading land descriptions as patents, tract books and family papers write them."""

from __future__ import annotations

import pytest

from us_places_mcp.legal import expand_aliquot, parse

#: (text, state, meridian, township, range, section, aliquot cells, lots)
GOLDEN = [
    ("E½NE Sec. 18, T84N R39W, 5th P.M.", None, "05", "84N", "39W", 18, ["NENE", "SENE"], []),
    ("E2NE S18 T84N R39W 5th PM", None, "05", "84N", "39W", 18, ["NENE", "SENE"], []),
    (
        "E 1/2 NE 1/4 Section 18, Township 84 North, Range 39 West of the 5th Principal Meridian",
        None, "05", "84N", "39W", 18, ["NENE", "SENE"], [],
    ),
    ("NWNE Sec 18 0840N 0390W", "IA", "05", "84N", "39W", 18, ["NWNE"], []),
    ("A,SWSE Sec 4 T1N R25W 6th PM", None, "06", "1N", "25W", 4, ["SWSE"], []),
    ("Lot 3 Sec 30 T2N R17W 6th PM", None, "06", "2N", "17W", 30, [], [3]),
    ("Lots 1, 2 and 3, Sec. 4, T. 1 N., R. 20 W.", "Nebraska", "06", "1N", "20W", 4, [], [1, 2, 3]),
    (
        "S½NW and N½SW Sec. 22, T1N R25W 6th P.M.",
        None, "06", "1N", "25W", 22, ["SENW", "SWNW", "NESW", "NWSW"], [],
    ),
    (
        "the east half of the northeast quarter of section 18, township 84 north, "
        "range 39 west, fifth principal meridian",
        None, "05", "84N", "39W", 18, ["NENE", "SENE"], [],
    ),
    ("NE Sec 10 T5S R3E Boise Meridian", None, "08", "5S", "3E", 10,
     ["NENE", "NWNE", "SENE", "SWNE"], []),
    (
        "SE¼ of Section 12 in Township 2 North of Range 14 East of the Fourth Principal Meridian",
        None, "04", "2N", "14E", 12, ["NESE", "NWSE", "SESE", "SWSE"], [],
    ),
    ("E½ Sec 7 T10N R5W Mount Diablo Meridian", None, "21", "10N", "5W", 7,
     ["NENE", "NWNE", "SENE", "SWNE", "NESE", "NWSE", "SESE", "SWSE"], []),
]  # fmt: skip


@pytest.mark.parametrize(
    ("text", "state", "meridian", "township", "rng", "section", "cells", "lots"), GOLDEN
)
def test_golden_descriptions(text, state, meridian, township, rng, section, cells, lots):
    [tract] = parse(text, state)["tracts"]
    assert tract["meridian_code"] == meridian
    assert (tract["township"], tract["range"], tract["section"]) == (township, rng, section)
    assert tract["quarter_quarters"] == cells
    assert tract["lots"] == lots
    assert tract["raw"] == text.strip()


def test_a_family_papers_run_on_is_read_with_warnings():
    """The records-to-fetch #88 string: no T, no R, no "Sec.", no meridian."""
    [tract] = parse("SENW No 13 N 17 W 31", "MI")["tracts"]
    assert (tract["township"], tract["range"], tract["section"]) == ("13N", "17W", 31)
    assert tract["quarter_quarters"] == ["SENW"]
    assert tract["meridian_code"] == "19"
    warnings = " ".join(tract["warnings"])
    assert "without 'T' and 'R'" in warnings
    assert "bare number after the range" in warnings
    assert "assumed" in warnings


def test_a_second_tract_inherits_the_township():
    tracts = parse("N½NW Sec. 22, T1N R25W 6th PM; SWSW Sec. 15")["tracts"]
    assert [t["section"] for t in tracts] == [22, 15]
    assert tracts[1]["township"] == "1N" and tracts[1]["meridian_code"] == "06"
    assert "carried from the tract before" in tracts[1]["warnings"][-1]


def test_finer_than_a_quarter_quarter_is_located_to_its_cell_with_a_warning():
    [tract] = parse("S½SW¼NE¼ Sec 18 T84N R39W 5th PM")["tracts"]
    assert tract["quarter_quarters"] == ["SWNE"]
    assert "finer than a quarter-quarter" in tract["warnings"][0]


def test_no_meridian_and_an_ambiguous_state_says_so():
    [tract] = parse("NENE Sec 1 T1N R1W", "SD")["tracts"]
    assert tract["meridian_code"] is None
    assert any("no meridian" in w for w in tract["warnings"])


def test_a_section_out_of_range_is_reported():
    [tract] = parse("NENE Sec 37 T1N R1W 5th PM")["tracts"]
    assert tract["section"] is None
    assert any("not 1-36" in w for w in tract["warnings"])


def test_nothing_recognisable_gives_warnings_not_an_exception():
    [tract] = parse("the old home place by the creek")["tracts"]
    assert tract["township"] is None
    assert tract["warnings"]


@pytest.mark.parametrize(
    ("aliquot", "cells"),
    [
        ("NWNE", ["NWNE"]),
        ("E½NE", ["NENE", "SENE"]),
        ("N½NW", ["NENW", "NWNW"]),
        ("W2SW", ["NWSW", "SWSW"]),
        ("SE", ["NESE", "NWSE", "SESE", "SWSE"]),
        ("NE¼SW¼", ["NESW"]),
        ("A,NWSE", ["NWSE"]),
    ],
)
def test_aliquots_expand_to_quarter_quarters(aliquot, cells):
    assert expand_aliquot(aliquot) == (cells, [])


@pytest.mark.parametrize("bad", ["XYZ", "NENEX", "E3NE", ""])
def test_an_unreadable_aliquot_is_reported(bad):
    cells, warnings = expand_aliquot(bad)
    assert cells == [] and warnings
