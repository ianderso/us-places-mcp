"""Which county held a spot on a date: the Newberry atlas, through OpenHistoricalMap.

The Newberry Library's *Atlas of Historical County Boundaries* (AHCB) records
every creation and boundary change of every US county, 1629-2000, dated to
the day, with the event and the statute. OpenHistoricalMap imported it, one
relation per county *version*, and its Overpass API answers "which versions
contain this point" with no key. The data is CC0.

AHCB files each county under its *modern* state (``nl_ahcb:id_text`` such as
``wvs_monongalia``), so a Virginia county now in West Virginia is filed
under WV; the event text says which government created it.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

#: Tags that mark a relation as imported from the Newberry atlas.
NEWBERRY = "Newberry"

#: The atlas stops here; later changes are not in it.
AHCB_END = date(2000, 12, 31)

#: A date this close to a change is flagged for a manual check.
NEAR_CHANGE_DAYS = 365

_DATE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
_ATTACHED = re.compile(r"attached to ((?:[A-Z][A-Z.'\-]*)(?: [A-Z][A-Z.'\-]*)*)")


def period(text: str) -> tuple[date, date] | None:
    """The first and last day a date string covers: a year, a month or a day."""
    m = _DATE.match((text or "").strip())
    if not m:
        return None
    year = int(m.group(1))
    try:
        if m.group(3):
            day = date(year, int(m.group(2)), int(m.group(3)))
            return day, day
        if m.group(2):
            month = int(m.group(2))
            return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        return date(year, 1, 1), date(year, 12, 31)
    except ValueError:
        return None


def point_query(lat: float, lon: float) -> str:
    """Overpass QL: every county version whose area contains the point."""
    return (
        f"[out:json][timeout:60];is_in({lat:.5f},{lon:.5f})->.a;"
        "rel(pivot.a)[boundary=administrative][admin_level=6];out tags;"
    )


def _overpass_regex(text: str) -> str:
    """A literal for an Overpass regex inside a double-quoted string."""
    out = []
    for ch in text:
        if ch.isalnum() or ch in " '-":
            out.append(ch)
        elif ch == "\\" or ch == '"':
            continue
        else:
            out.append(f"[{ch}]")
    return "".join(out)


def history_query(county: str, state: str) -> str:
    """Overpass QL: every version of one county, by name, within one AHCB state file."""
    name = re.sub(r"\s+(county|parish|borough|district)$", "", county.strip(), flags=re.IGNORECASE)
    return (
        "[out:json][timeout:60];rel[boundary=administrative][admin_level=6]"
        f'["nl_ahcb:id_text"~"^{state.lower()}s_"]'
        f'["name"~"^{_overpass_regex(name)}( County| Parish| Borough| District)?$",i];'
        "out tags;"
    )


def _tags(element: object) -> dict:
    if isinstance(element, dict) and isinstance(element.get("tags"), dict):
        return element["tags"]
    return {}


def is_newberry(tags: dict) -> bool:
    return "nl_ahcb:id_text" in tags or NEWBERRY in str(tags.get("source:name", ""))


def version(element: object) -> dict | None:
    """One county version, compact. None if it is not from the Newberry atlas."""
    tags = _tags(element)
    if not is_newberry(tags):
        return None
    event = tags.get("start_event") or ""
    attached = _ATTACHED.search(event)
    id_text = tags.get("nl_ahcb:id_text") or ""
    return {
        "county": tags.get("name"),
        "from": tags.get("start_date"),
        "to": tags.get("end_date"),
        "how": event or None,
        "statute": tags.get("nl_ahcb:source"),
        "kind": tags.get("import:county_type"),
        "attached_to": attached.group(1).title() if attached else None,
        "ahcb_state_file": id_text.split("_", 1)[0][:2].upper() or None,
        "ahcb_id": id_text or None,
        "wikidata": tags.get("wikidata"),
        "ohm_relation": element.get("id") if isinstance(element, dict) else None,
    }


def versions(payload: object) -> list[dict]:
    """Newberry county versions from an Overpass answer, oldest first."""
    elements = payload.get("elements") if isinstance(payload, dict) else None
    out = [v for e in (elements if isinstance(elements, list) else []) if (v := version(e))]
    return sorted(out, key=lambda v: (v["from"] or "", v["county"] or ""))


def _span(v: dict) -> tuple[date, date]:
    start = period(v["from"] or "")
    end = period(v["to"] or "") if v["to"] else None
    return (start[0] if start else date.min, end[1] if end else date.max)


def held_on(chain: list[dict], when: tuple[date, date]) -> list[dict]:
    """The versions whose span overlaps the period ``when``."""
    lo, hi = when
    return [v for v in chain if _span(v)[0] <= hi and _span(v)[1] >= lo]


def changes_near(
    chain: list[dict], when: tuple[date, date], days: int = NEAR_CHANGE_DAYS
) -> list[str]:
    """Change dates (a version starting or ending) within ``days`` of the period."""
    lo, hi = when
    out = set()
    for v in chain:
        start, end = _span(v)
        for edge in (start, end):
            if edge in (date.min, date.max):
                continue
            gap = 0 if lo <= edge <= hi else min(abs((edge - lo).days), abs((edge - hi).days))
            if gap <= days:
                out.add(edge.isoformat())
    return sorted(out)


def status(holders: list[dict]) -> str:
    """``one``, ``changed_during_period``, ``contested`` or ``none``."""
    ids = {h["ahcb_id"] for h in holders}
    if not holders:
        return "none"
    if len(ids) == 1:
        return "one"
    spans = [_span(h) for h in holders]
    for i, a in enumerate(spans):
        for j, b in enumerate(spans):
            if i < j and holders[i]["ahcb_id"] != holders[j]["ahcb_id"]:
                if a[0] <= b[1] and b[0] <= a[1]:
                    return "contested"
    return "changed_during_period"
