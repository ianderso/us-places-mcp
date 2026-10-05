"""Static reference tables: principal meridians and which states hold federal land.

The meridian codes are BLM's two-digit ``PRINMERCD`` codes. BLM's own PLSS
service labels some codes inconsistently (see docs/API-NOTES.md): code 18
also appears as "St. Helena", 27 as "Mount Diablo" and 45 as "Kateel River".
So names here come from this table, keyed on the code, never from the
service's label.
"""

from __future__ import annotations

import re

#: BLM principal-meridian code -> name.
MERIDIANS: dict[str, str] = {
    "01": "First Principal Meridian",
    "02": "Second Principal Meridian",
    "03": "Third Principal Meridian",
    "04": "Fourth Principal Meridian",
    "05": "Fifth Principal Meridian",
    "06": "Sixth Principal Meridian",
    "07": "Black Hills Meridian",
    "08": "Boise Meridian",
    "09": "Chickasaw Meridian",
    "10": "Choctaw Meridian",
    "11": "Cimarron Meridian",
    "12": "Copper River Meridian",
    "13": "Fairbanks Meridian",
    "14": "Gila and Salt River Meridian",
    "15": "Humboldt Meridian",
    "16": "Huntsville Meridian",
    "17": "Indian Meridian",
    "18": "Louisiana Meridian",
    "19": "Michigan Meridian",
    "20": "Principal Meridian, Montana",
    "21": "Mount Diablo Meridian",
    "22": "Navajo Meridian",
    "23": "New Mexico Principal Meridian",
    "24": "St. Helena Meridian",
    "25": "St. Stephens Meridian",
    "26": "Salt Lake Meridian",
    "27": "San Bernardino Meridian",
    "28": "Seward Meridian",
    "29": "Tallahassee Meridian",
    "30": "Uintah Special Meridian",
    "31": "Ute Meridian",
    "32": "Washington Meridian",
    "33": "Willamette Meridian",
    "34": "Wind River Meridian",
    "36": "Between the Miamis (Ohio)",
    "37": "Muskingum River (Ohio)",
    "38": "Ohio River Base (Ohio)",
    "39": "Scioto River, First (Ohio)",
    "40": "Scioto River, Second (Ohio)",
    "41": "Scioto River, Third (Ohio)",
    "44": "Kateel River Meridian",
    "45": "Umiat Meridian",
    "46": "Fourth Principal Meridian Extended",
    "47": "West of the Great Miami (Ohio)",
    "48": "U.S. Military Survey (Ohio)",
}

_ORDINALS = {
    "1": "01", "first": "01", "2": "02", "second": "02", "3": "03", "third": "03",
    "4": "04", "fourth": "04", "5": "05", "fifth": "05", "6": "06", "sixth": "06",
}  # fmt: skip

#: Spellings found in patents, tract books and family papers -> code.
_NAME_ALIASES: dict[str, str] = {
    "black hills": "07",
    "boise": "08",
    "chickasaw": "09",
    "choctaw": "10",
    "cimarron": "11",
    "copper river": "12",
    "fairbanks": "13",
    "gila and salt river": "14",
    "gila & salt river": "14",
    "gila salt river": "14",
    "humboldt": "15",
    "huntsville": "16",
    "indian": "17",
    "louisiana": "18",
    "michigan": "19",
    "montana": "20",
    "principal": "20",
    "mount diablo": "21",
    "mt diablo": "21",
    "mt. diablo": "21",
    "navajo": "22",
    "new mexico": "23",
    "new mexico principal": "23",
    "st. helena": "24",
    "st helena": "24",
    "saint helena": "24",
    "st. stephens": "25",
    "st stephens": "25",
    "saint stephens": "25",
    "salt lake": "26",
    "san bernardino": "27",
    "seward": "28",
    "tallahassee": "29",
    "uintah": "30",
    "uintah special": "30",
    "ute": "31",
    "washington": "32",
    "willamette": "33",
    "wind river": "34",
    "between the miamis": "36",
    "muskingum river": "37",
    "ohio river base": "38",
    "kateel river": "44",
    "umiat": "45",
    "fourth principal extended": "46",
    "extended fourth": "46",
    "west of the great miami": "47",
    "us military survey": "48",
    "u.s. military survey": "48",
    "united states military survey": "48",
}

#: Meridians governing each state's surveys, from BLM's PLSS data on 2026-10-05,
#: with the stray codes it also holds left out (see docs/API-NOTES.md).
STATE_MERIDIANS: dict[str, tuple[str, ...]] = {
    "AL": ("16", "25", "29"),
    "AK": ("12", "13", "28", "44", "45"),
    "AZ": ("14", "22", "27"),
    "AR": ("05", "09", "10"),
    "CA": ("14", "15", "21", "27"),
    "CO": ("06", "23", "31"),
    "FL": ("29",),
    "ID": ("08",),
    "IL": ("02", "03", "04"),
    "IN": ("01", "02"),
    "IA": ("05",),
    "KS": ("06",),
    "LA": ("18", "24"),
    "MI": ("19",),
    "MN": ("05", "46"),
    "MS": ("09", "10", "16", "25", "32"),
    "MO": ("05",),
    "MT": ("20",),
    "NE": ("06",),
    "NV": ("21",),
    "NM": ("23",),
    "ND": ("05",),
    "OH": ("01", "19", "36", "37", "38", "39", "40", "41", "47", "48"),
    "OK": ("11", "17"),
    "OR": ("33",),
    "SD": ("05", "06", "07"),
    "UT": ("26", "30"),
    "WA": ("33",),
    "WI": ("46",),
    "WY": ("06", "34"),
}

STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}  # fmt: skip

#: States whose land was never federal public domain: first title came from
#: the colony or state. Value: who granted it, and where its records are.
STATE_LAND: dict[str, str] = {
    "CT": "Colonial and state grants; town proprietors' records and the Connecticut State Library.",
    "DE": "Proprietary and state grants; Delaware Public Archives.",
    "GA": "Headright grants, then the land lotteries of 1805-1833; Georgia Archives.",
    "HI": "The Kingdom of Hawaii's Great Mahele and royal patents; Hawaii State Archives.",
    "KY": "Virginia grants, then Kentucky grants, by metes and bounds; Kentucky Secretary of "
    "State's Land Office.",
    "ME": "Massachusetts until 1820, then Maine; both states' archives.",
    "MD": "Proprietary and state patents; Maryland State Archives (Land Office).",
    "MA": "Colonial and town grants; Massachusetts Archives and town records.",
    "NH": "Colonial and state grants; New Hampshire State Archives.",
    "NJ": "East and West Jersey proprietors; New Jersey State Archives.",
    "NY": "Colonial and state patents; New York State Archives.",
    "NC": "Lords Proprietors', royal and state grants; State Archives of North Carolina.",
    "PA": "Proprietary and state warrants, surveys and patents; Pennsylvania State Archives "
    "(Land Office records).",
    "RI": "Colonial and town grants; Rhode Island State Archives and town records.",
    "SC": "Royal and state grants and plats; South Carolina Department of Archives and History.",
    "TN": "North Carolina grants, then Tennessee grants; Tennessee State Library and Archives.",
    "TX": "Spanish, Mexican, Republic and state grants; the Texas General Land Office in Austin "
    "is a STATE agency, not the federal GLO.",
    "VT": "New Hampshire and New York grants, then Vermont; Vermont State Archives.",
    "VA": "Colonial patents and state grants; Library of Virginia.",
    "WV": "Virginia grants until 1863; Library of Virginia and West Virginia Archives.",
    "DC": "Maryland and Virginia grants before 1791.",
}

#: Federal public-land states where some first titles are not PLSS patents.
SPECIAL_CASES: dict[str, str] = {
    "OH": "Federal, but much of Ohio was surveyed outside the rectangular system: the "
    "Virginia Military District (metes and bounds, Virginia warrants), the U.S. Military "
    "District, and the Connecticut Western Reserve, which Connecticut sold itself, so it "
    "has no federal patents.",
    "LA": "Spanish and French private land claims, confirmed by federal commissions, predate "
    "the surveys and do not follow the grid.",
    "MO": "French and Spanish private land claims predate the surveys.",
    "FL": "Spanish land grants predate the surveys.",
    "CA": "Spanish and Mexican ranchos, confirmed as private land claims.",
    "NM": "Spanish and Mexican grants, confirmed as private land claims.",
    "AZ": "Some Spanish and Mexican grants, confirmed as private land claims.",
    "MI": "French private claims (Detroit and the river lots) predate the surveys.",
    "MS": "British and Spanish grants predate the surveys in the Natchez district.",
    "AL": "Spanish grants near Mobile predate the surveys.",
    "IN": "French claims at Vincennes predate the surveys.",
    "IL": "French claims in the American Bottom predate the surveys.",
}


def state_code(value: object) -> str | None:
    """A two-letter state code from a code or a full name, or None."""
    text = str(value or "").strip()
    if text.upper() in STATE_NAMES:
        return text.upper()
    lowered = text.lower()
    for code, name in STATE_NAMES.items():
        if name.lower() == lowered:
            return code
    return None


def meridian_code(value: object) -> str | None:
    """BLM's two-digit code for a meridian given as a code, an ordinal or a name.

    Accepts ``5``, ``05``, ``5th``, ``Fifth Principal Meridian``, ``5th P.M.``
    and names such as ``Mount Diablo``. Initials such as ``M.D.M.`` are refused
    as ambiguous, and so is any name not in the table.
    """
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text.isdigit():
        code = text.zfill(2)
        return code if code in MERIDIANS else None
    if m := re.fullmatch(
        r"(\d|first|second|third|fourth|fifth|sixth)(?:st|nd|rd|th)?"
        r"(?:\s*(?:p\.?\s*m\.?|principal(?:\s+meridian)?|meridian))?",
        text,
    ):
        return _ORDINALS.get(m.group(1))
    name = re.sub(r"\s+", " ", re.sub(r"\b(principal\s+)?meridian\b|\bp\.?\s*m\.?$", "", text))
    name = name.strip(" ,.")
    if "extended" in text and ("4" in text or "fourth" in text):
        return "46"
    return _NAME_ALIASES.get(name)
