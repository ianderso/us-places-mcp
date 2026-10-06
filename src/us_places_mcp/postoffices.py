"""US post offices, 1639-2000: Blevins and Helbock's dataset, queried locally.

Richard W. Helbock compiled every independent US post office he could find,
mainly from the Post Office Department's Records of Appointments of
Postmasters, with its state, county, and years of establishment and
discontinuance. Cameron Blevins geocoded the records by matching their names
to GNIS features and published the result on Harvard Dataverse
(doi:10.7910/DVN/NUKCNA, CC0): 166,140 offices, two in three with
coordinates.

How to read it, from Blevins's data biography:

* The years are Helbock's. A major renaming, or a change to branch status,
  ends one record and may start another, so a "discontinued" year can be a
  new name and an "established" year a renamed office. An office closed for
  under ten years stays one record, marked not ``continuous``.
* Counties are those in which the office's site lies *now* (Helbock wrote in
  the 1990s-2000s), not the county that held it then.
* Coordinates come from a name match to a GNIS feature (a post office, a
  populated place, a locale), scored 0.75-1 for closeness. A move within a
  town, or to a store down the road, is not recorded.
* A blank discontinuance means the office was still open in 2000.

The CSV is downloaded once (``format=original``, which is the file whose MD5
Dataverse publishes), checked, and loaded into SQLite; queries never touch
the network again.
"""

from __future__ import annotations

import csv
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .gnis import county_key, key

DOI = "doi:10.7910/DVN/NUKCNA"
ORIGINAL_NAME = "us-post-offices.csv"
DB_NAME = "us-post-offices.sqlite"
CITATION = (
    "Blevins, Cameron; Helbock, Richard W., US Post Offices, Harvard Dataverse, "
    "doi:10.7910/DVN/NUKCNA (CC0)"
)

#: The years the dataset covers; a date outside them, or a discontinuance
#: before the establishment, is a transcription slip.
FIRST_YEAR, LAST_YEAR = 1639, 2000

#: Earth's mean radius, for distances.
EARTH_KM = 6371.0088

#: Columns the CSV must carry.
COLUMNS = (
    "Name",
    "AltName",
    "OrigName",
    "State",
    "County1",
    "County2",
    "County3",
    "OrigCounty",
    "Established",
    "Discontinued",
    "Continuous",
    "ID",
    "GNIS.Match",
    "GNIS.FEATURE_ID",
    "GNIS.Feature.Class",
    "GNIS.OrigName",
    "GNIS.Dist",
    "Latitude",
    "Longitude",
)


class DatasetChanged(ValueError):
    """Dataverse's description of the dataset is not what this module reads."""


def dataset_file(payload: Any) -> dict:
    """The post-office CSV's entry in Dataverse's dataset description.

    Returns its file id, the checksum Dataverse publishes (of the original
    upload), its size, and the dataset version and licence.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    version = data.get("latestVersion") if isinstance(data, dict) else None
    files = version.get("files") if isinstance(version, dict) else None
    for entry in files if isinstance(files, list) else []:
        df = entry.get("dataFile") if isinstance(entry, dict) else None
        if not isinstance(df, dict) or ORIGINAL_NAME not in (
            df.get("originalFileName"),
            df.get("filename"),
        ):
            continue
        checksum = df.get("checksum") if isinstance(df.get("checksum"), dict) else {}
        algorithm = str(checksum.get("type") or "").lower().replace("-", "")
        value = str(checksum.get("value") or "").lower()
        size = df.get("originalFileSize") or df.get("filesize")
        if not isinstance(df.get("id"), int) or not algorithm or not value:
            break
        licence = version.get("license")
        return {
            "id": df["id"],
            "algorithm": algorithm,
            "checksum": value,
            "size": size if isinstance(size, int) else None,
            "version": f"{version.get('versionNumber')}.{version.get('versionMinorNumber')}",
            "license": licence.get("name") if isinstance(licence, dict) else None,
        }
    raise DatasetChanged(f"Dataverse's record for {DOI} no longer lists {ORIGINAL_NAME}.")


def _int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _keys(*names: str) -> str:
    """Every spelling of a name as one searchable string, ``|``-separated."""
    out = []
    for name in names:
        # Helbock writes a variant letter in parentheses: AARONSBURG(H).
        for variant in (name, name.replace("(", "").replace(")", "")):
            if (k := key(variant)) and k not in out:
                out.append(k)
    return "|" + "|".join(out) + "|"


_SCHEMA = (
    "CREATE TABLE offices (id INTEGER, name TEXT, alt_name TEXT, keys TEXT, state TEXT, "
    "county TEXT, counties TEXT, established INTEGER, discontinued INTEGER, continuous "
    "INTEGER, lat REAL, lon REAL, gnis_id INTEGER, gnis_class TEXT, gnis_name TEXT, "
    "gnis_score REAL)",
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)",
)
_INDEXES = (
    "CREATE INDEX offices_state ON offices (state)",
    "CREATE INDEX offices_lat ON offices (lat)",
)


def build(csv_path: Path, db: Path, meta: dict[str, str]) -> int:
    """Load the CSV into a new SQLite database at ``db``. Returns the office count."""
    rows = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise DatasetChanged(f"{ORIGINAL_NAME} lacks the columns {', '.join(missing)}")
        for r in reader:
            matched = r["GNIS.Match"].strip().upper() == "TRUE"
            counties = [key(c) for c in (r["County1"], r["County2"], r["County3"]) if c.strip()]
            gnis = (
                (
                    _int(r["GNIS.FEATURE_ID"]),
                    r["GNIS.Feature.Class"].strip() or None,
                    r["GNIS.OrigName"].strip() or None,
                    _float(r["GNIS.Dist"]),
                )
                if matched
                else (None, None, None, None)
            )
            rows.append(
                (
                    _int(r["ID"]),
                    r["OrigName"].strip() or r["Name"].strip(),
                    r["AltName"].strip() or None,
                    _keys(r["Name"], r["AltName"], r["OrigName"]),
                    r["State"].strip().upper(),
                    r["OrigCounty"].strip() or None,
                    "|" + "|".join(counties) + "|",
                    _int(r["Established"]),
                    _int(r["Discontinued"]),
                    0 if r["Continuous"].strip().upper() == "FALSE" else 1,
                    _float(r["Latitude"]),
                    _float(r["Longitude"]),
                    *gnis,
                )
            )
    db.unlink(missing_ok=True)
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            for statement in _SCHEMA:
                conn.execute(statement)
            conn.executemany(f"INSERT INTO offices VALUES ({', '.join('?' * 16)})", rows)
            for statement in _INDEXES:
                conn.execute(statement)
            facts = {**meta, "offices": str(len(rows))}
            conn.executemany("INSERT INTO meta VALUES (?, ?)", sorted(facts.items()))
    return len(rows)


def read_meta(db: Path) -> dict[str, str]:
    with closing(sqlite3.connect(db)) as conn:
        return dict(conn.execute("SELECT key, value FROM meta"))


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(min(1.0, a)))


def suspect(established: int | None, discontinued: int | None) -> bool:
    """True if the years cannot both be right."""
    for year in (established, discontinued):
        if year is not None and not FIRST_YEAR <= year <= LAST_YEAR:
            return True
    return established is not None and discontinued is not None and discontinued < established


def _office(row: tuple, point: tuple[float, float] | None) -> dict:
    (oid, name, alt, state, county, est, disc, cont, lat, lon, gid, gcls, gname, gscore) = row
    out: dict[str, Any] = {
        "name": name,
        "state": state,
        "county": county,
        "established": est,
        "discontinued": disc,
        "continuous": bool(cont),
        "lat": lat,
        "lon": lon,
        "gnis_match": {"id": gid, "class": gcls, "name": gname, "score": gscore}
        if gid is not None
        else None,
        "helbock_id": oid,
    }
    if alt:
        out["alt_name"] = alt
    if point and lat is not None and lon is not None:
        out["distance_km"] = round(distance_km(point[0], point[1], lat, lon), 2)
    if suspect(est, disc):
        out["date_suspect"] = True
    return out


_FIELDS = (
    "id, name, alt_name, state, county, established, discontinued, continuous, lat, lon, "
    "gnis_id, gnis_class, gnis_name, gnis_score"
)


def search(
    db: Path,
    *,
    name: str,
    state: str | None,
    county: str,
    point: tuple[float, float] | None,
    radius_km: float,
    year: int | None,
    limit: int,
) -> tuple[int, int, list[dict]]:
    """Offices matching every criterion given.

    Returns (how many match, how many of those have no coordinates, the first
    ``limit``: nearest first with a point, else oldest first).
    """
    where: list[str] = []
    args: list[Any] = []
    if name:
        # Both sides are keys (upper case, punctuation gone, Mt. written Mount),
        # compared without spaces: Helbock often wrote SPRINGLAKE and DESMET.
        where.append("REPLACE(keys, ' ', '') LIKE ?")
        args.append(f"%{key(name).replace(' ', '')}%")
    if state:
        # Helbock writes an office on a state line as MI/OH.
        where.append("('/' || state || '/') LIKE ?")
        args.append(f"%/{state}/%")
    if county:
        where.append("counties LIKE ?")
        args.append(f"%|{county_key(county)}|%")
    if year is not None:
        where.append("established <= ? AND (discontinued IS NULL OR discontinued >= ?)")
        args += [year, year]
    if point:
        lat, lon = point
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
        where.append("lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?")
        args += [lat - dlat, lat + dlat, lon - dlon, lon + dlon]
    clause = " AND ".join(where) or "1"
    with closing(sqlite3.connect(db)) as conn:
        if point:
            found = [
                r
                for r in conn.execute(f"SELECT {_FIELDS} FROM offices WHERE {clause}", args)
                if distance_km(point[0], point[1], r[8], r[9]) <= radius_km
            ]
            found.sort(key=lambda r: (distance_km(point[0], point[1], r[8], r[9]), r[1]))
            return len(found), 0, [_office(r, point) for r in found[:limit]]
        total, unplaced = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(lat IS NULL), 0) FROM offices WHERE {clause}", args
        ).fetchone()
        rows = conn.execute(
            f"SELECT {_FIELDS} FROM offices WHERE {clause} "
            "ORDER BY established IS NULL, established, name LIMIT ?",
            [*args, limit],
        ).fetchall()
    return total, unplaced, [_office(r, None) for r in rows]
