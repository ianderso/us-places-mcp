"""Place names from USGS's Geographic Names Information System (GNIS).

Two sources, searched for the same name:

* **The live gazetteer,** The National Map's ``geonames`` map service. Its
  layers hold populated places, civil and census areas, landforms, streams
  and lakes, crossings, and three layers of "historical" features (places and
  waters that no longer exist, named "… (historical)"). One ArcGIS ``find``
  request searches them all; the state and the class reach it only as
  ``layerDefs`` built from fixed tables, never from free text.
* **The archive of 25 August 2021.** That year GNIS stopped keeping the built
  features: cemeteries, churches, schools, post offices, buildings, locales
  and more. USGS kept the last full state files
  (``PA_Features_20210825.txt``, pipe-delimited) in its staged-products
  bucket. A state's file is downloaded on first use, checked against its S3
  ETag, and only the dropped classes are loaded into a local SQLite table.

A feature has the same id in both (``gaz_id`` live, ``FEATURE_ID`` in the
archive), so one found in both is reported once, from the live service.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

#: Live layers searched: civil, census and populated places; landforms,
#: streams and other waters; crossings; and the three historical layers.
#: Layer 8 (Antarctica) is left out.
LIVE_LAYERS = (1, 2, 3, 5, 6, 7, 10, 12, 13, 14)

#: Feature classes the live service holds (observed 2026-10-05).
LIVE_CLASSES = frozenset(
    {
        "Arch", "Area", "Arroyo", "Bar", "Basin", "Bay", "Beach", "Bench", "Bend",
        "Canal", "Cape", "Census", "Channel", "Civil", "Cliff", "Crater", "Crossing",
        "Falls", "Flat", "Gap", "Glacier", "Gut", "Island", "Isthmus", "Lake", "Lava",
        "Levee", "Military", "Pillar", "Plain", "Populated Place", "Range", "Rapids",
        "Reservoir", "Ridge", "Sea", "Slope", "Spring", "Stream", "Summit", "Swamp",
        "Valley", "Woods",
    }
)  # fmt: skip

#: Classes GNIS dropped in 2021, searched in the archive. Military is in both:
#: the live service keeps only the historical installations.
ARCHIVE_CLASSES = frozenset(
    {
        "Airport", "Bridge", "Building", "Cave", "Cemetery", "Church", "Dam", "Forest",
        "Harbor", "Hospital", "Locale", "Military", "Mine", "Oilfield", "Park",
        "Post Office", "Reserve", "School", "Tower", "Trail", "Tunnel", "Well",
    }
)  # fmt: skip

CLASSES = LIVE_CLASSES | ARCHIVE_CLASSES

#: The archive's date, as it appears in its file names.
ARCHIVE_DATE = "20210825"
ARCHIVE_DB = "gnis-2021.sqlite"

#: Columns the archive files must carry.
ARCHIVE_FIELDS = (
    "FEATURE_ID",
    "FEATURE_NAME",
    "FEATURE_CLASS",
    "STATE_ALPHA",
    "COUNTY_NAME",
    "PRIM_LAT_DEC",
    "PRIM_LONG_DEC",
    "MAP_NAME",
)

#: Leading abbreviations GNIS (and Helbock) write out in full.
ABBREVIATIONS = {"MT": "Mount", "FT": "Fort", "ST": "Saint", "PT": "Point"}

_COUNTY_SUFFIX = re.compile(r"\s+(county|parish|borough|census area)$", re.IGNORECASE)


def feature_class(value: str) -> str | None:
    """The canonical GNIS class for a name in any case, or None."""
    wanted = " ".join(value.split()).lower()
    return next((c for c in CLASSES if c.lower() == wanted), None)


def search_text(name: str) -> str:
    """A name as GNIS would spell it: Mt., Ft., St. and Pt. written out, no apostrophes.

    GNIS policy drops the possessive apostrophe (Pikes Peak) and abbreviations.
    """
    words = name.replace("’", "'").replace("'", "").split()
    out = []
    for i, word in enumerate(words):
        bare = word.rstrip(".").upper()
        out.append(ABBREVIATIONS[bare] if bare in ABBREVIATIONS and i < len(words) - 1 else word)
    return " ".join(out)


def key(text: str) -> str:
    """An uppercase key with punctuation removed, for matching names locally."""
    return " ".join(re.sub(r"[\W_]+", " ", search_text(text).replace(".", "")).upper().split())


def county_key(county: str) -> str:
    """A county's key, without the word County, Parish or Borough."""
    return key(_COUNTY_SUFFIX.sub("", " ".join(county.split())))


def find_params(text: str, state: str | None, cls: str | None) -> dict[str, str]:
    """ArcGIS ``find`` parameters: the name in any layer, filtered by state and class.

    ``state`` and ``cls`` must come from the state and class tables: they are
    placed in ``layerDefs`` as SQL literals.
    """
    where = []
    if state:
        where.append(f"state_alpha='{state}'")
    if cls:
        where.append(f"gaz_featureclass='{cls}'")
    out = {
        "searchText": text,
        "contains": "true",
        "searchFields": "gaz_name",
        "layers": ",".join(str(n) for n in LIVE_LAYERS),
        "returnGeometry": "true",
        "sr": "4326",
        "f": "json",
    }
    if where:
        clause = " AND ".join(where)
        out["layerDefs"] = json.dumps({str(n): clause for n in LIVE_LAYERS}, sort_keys=True)
    return out


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if text and text != "Null" else None


def _int(value: object) -> int | None:
    text = _text(value)
    return int(text) if text and text.isdigit() else None


def _coords(lat: object, lon: object) -> tuple[float | None, float | None]:
    try:
        y, x = float(lat), float(lon)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, None
    if y == 0 and x == 0:
        return None, None  # the archive's "unknown"
    return round(y, 5), round(x, 5)


def _geometry_point(geometry: object) -> tuple[float | None, float | None]:
    if not isinstance(geometry, dict):
        return None, None
    points = geometry.get("points")
    if isinstance(points, list) and points and isinstance(points[0], list | tuple):
        return _coords(points[0][1], points[0][0])
    return _coords(geometry.get("y"), geometry.get("x"))


def live_places(payload: Any) -> list[dict]:
    """The features in an ArcGIS ``find`` answer."""
    results = payload.get("results") if isinstance(payload, dict) else None
    out = []
    for result in results if isinstance(results, list) else []:
        if not isinstance(result, dict) or not isinstance(result.get("attributes"), dict):
            continue
        attrs = result["attributes"]
        lat, lon = _geometry_point(result.get("geometry"))
        out.append(
            {
                "name": _text(attrs.get("gaz_name")),
                "class": _text(attrs.get("gaz_featureclass")),
                "state": _text(attrs.get("state_alpha")),
                "county": _text(attrs.get("county_name")),
                "lat": lat,
                "lon": lon,
                "gnis_id": _int(attrs.get("gaz_id")),
                "source": "live",
            }
        )
    return out


def in_county(place: dict, wanted: str) -> bool:
    return bool(wanted) and county_key(place.get("county") or "") == wanted


def rank(places: list[dict], wanted: str) -> list[dict]:
    """Exact names first, then names that start with the search, then the rest."""

    wanted = wanted.replace(" ", "")

    def order(place: dict) -> tuple:
        name = key(place.get("name") or "")
        bare = name.replace(" ", "")
        closeness = 0 if bare == wanted else 1 if bare.startswith(wanted) else 2
        tie = place.get("gnis_id") or 0
        return (closeness, place.get("state") or "", place.get("county") or "", name, tie)

    return sorted(places, key=order)


# --------------------------------------------------------------------------- #
# The August 2021 archive
# --------------------------------------------------------------------------- #
def archive_file(state: str) -> str:
    return f"{state}_Features_{ARCHIVE_DATE}.txt"


def archive_url(base: str, state: str) -> str:
    return f"{base.rstrip('/')}/{archive_file(state)}"


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS features (id INTEGER PRIMARY KEY, name TEXT, name_key TEXT, "
    "class TEXT, state TEXT, county TEXT, county_key TEXT, lat REAL, lon REAL, quad TEXT)",
    "CREATE INDEX IF NOT EXISTS features_state ON features (state, class)",
    "CREATE TABLE IF NOT EXISTS states (state TEXT PRIMARY KEY, file TEXT, bytes INTEGER, "
    "etag TEXT, features INTEGER, loaded TEXT)",
)


def _connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(db, timeout=30)


def archive_states(db: Path) -> list[str]:
    """The states already loaded from the archive."""
    if not db.exists():
        return []
    try:
        with closing(_connect(db)) as conn:
            return [r[0] for r in conn.execute("SELECT state FROM states ORDER BY state")]
    except sqlite3.Error:
        return []


def read_archive(path: Path, state: str) -> list[tuple]:
    """The dropped-class features of one state from an archive file.

    Each state file also lists features of its neighbours that reach into it
    (a stream, a shared lake); only the state's own are kept.
    """
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="|", quoting=csv.QUOTE_NONE)
        missing = [f for f in ARCHIVE_FIELDS if f not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"the archive file lacks the columns {', '.join(missing)}")
        rows = []
        for row in reader:
            cls = (row.get("FEATURE_CLASS") or "").strip()
            if cls not in ARCHIVE_CLASSES or (row.get("STATE_ALPHA") or "").strip() != state:
                continue
            fid = _int(row.get("FEATURE_ID"))
            name = _text(row.get("FEATURE_NAME"))
            if fid is None or not name:
                continue
            county = _text(row.get("COUNTY_NAME"))
            lat, lon = _coords(row.get("PRIM_LAT_DEC"), row.get("PRIM_LONG_DEC"))
            rows.append(
                (fid, name, key(name), cls, state, county, county_key(county or ""), lat, lon,
                 _text(row.get("MAP_NAME")))
            )  # fmt: skip
    return rows


def load_archive(path: Path, state: str, db: Path, *, size: int, etag: str) -> int:
    """Load one state's dropped-class features into the archive database."""
    rows = read_archive(path, state)
    db.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(db)) as conn:
        with conn:
            for statement in _SCHEMA:
                conn.execute(statement)
            conn.execute("DELETE FROM features WHERE state = ?", (state,))
            conn.executemany(
                "INSERT OR REPLACE INTO features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
            )
            conn.execute(
                "INSERT OR REPLACE INTO states VALUES (?, ?, ?, ?, ?, ?)",
                (state, archive_file(state), size, etag, len(rows), time.strftime("%Y-%m-%d")),
            )
    return len(rows)


def search_archive(
    db: Path, state: str, name_key: str, county: str, classes: frozenset[str], limit: int
) -> tuple[int, list[dict]]:
    """Archive features of one state whose name contains ``name_key``: (total, first rows).

    Names are compared without spaces, so Greenmount finds Green Mount.
    """
    squashed = name_key.replace(" ", "")
    where = [
        "state = ?",
        "REPLACE(name_key, ' ', '') LIKE ?",
        f"class IN ({', '.join('?' * len(classes))})",
    ]
    args: list[Any] = [state, f"%{squashed}%", *sorted(classes)]
    if county:
        where.append("county_key = ?")
        args.append(county)
    clause = " AND ".join(where)
    with closing(_connect(db)) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM features WHERE {clause}", args).fetchone()[0]
        rows = conn.execute(
            "SELECT id, name, class, state, county, lat, lon, quad FROM features "
            f"WHERE {clause} ORDER BY CASE WHEN REPLACE(name_key, ' ', '') = ? THEN 0 "
            "WHEN REPLACE(name_key, ' ', '') LIKE ? THEN 1 ELSE 2 END, county, name, id "
            "LIMIT ?",
            [*args, squashed, f"{squashed}%", limit],
        ).fetchall()
    return total, [
        {
            "name": name,
            "class": cls,
            "state": st,
            "county": cty,
            "lat": lat,
            "lon": lon,
            "gnis_id": fid,
            "source": "archive_2021",
            "topo_quad": quad,
        }
        for fid, name, cls, st, cty, lat, lon, quad in rows
    ]
