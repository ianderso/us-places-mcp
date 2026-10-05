"""Locating Public Land Survey tracts with BLM's national PLSS service (CadNSDI).

Layer 1 holds townships, layer 2 sections ("first divisions"), layer 3 the
quarter-quarters and government lots ("second divisions"), each with ids
such as ``IA050840N0390W0`` (township), ``…SN180`` (section 18) and
``…SN180ANENE`` (its NE¼NE¼). Every value placed in a query here comes from
a validated table or from digits, never from free text.

CadNSDI is a modern compilation that includes resurveys. It locates a tract,
not a house, and a fractional township or a lot near a correction line may
not match the nineteenth-century plat.
"""

from __future__ import annotations

from typing import Any

from .tables import MERIDIANS

TOWNSHIP_LAYER = 1
SECTION_LAYER = 2
SUBDIVISION_LAYER = 3

POINT_FIELDS = (
    "STATEABBR,PRINMERCD,TWNSHPNO,TWNSHPDIR,RANGENO,RANGEDIR,PLSSID,TWNSHPLAB,"
    "FRSTDIVID,FRSTDIVNO,FRSTDIVLAB,SECDIVID,SECDIVTYP,SECDIVLAB,GOVLOT,GISACRE,STEWARD"
)


#: Fields for a point that falls in a township with no subdivision data.
TOWNSHIP_POINT_FIELDS = (
    "STATEABBR,PRINMERCD,TWNSHPNO,TWNSHPDIR,RANGENO,RANGEDIR,PLSSID,TWNSHPLAB,STEWARD"
)


def _codes(code: str) -> str:
    """SQL list for a meridian code, which the service also stores unpadded ('5')."""
    values = {code, code.lstrip("0") or "0"}
    return ", ".join(f"'{v}'" for v in sorted(values))


def township_where(state: str, meridian: str, number: int, ns: str, rng: int, ew: str) -> str:
    return (
        f"STATEABBR='{state}' AND PRINMERCD IN ({_codes(meridian)}) "
        f"AND TWNSHPNO='{number:03d}' AND TWNSHPDIR='{ns}' "
        f"AND RANGENO='{rng:03d}' AND RANGEDIR='{ew}'"
    )


def section_where(plss_id: str, section: int) -> str:
    return f"PLSSID='{plss_id}' AND FRSTDIVNO='{section:02d}'"


def subdivision_where(first_div_id: str, labels: list[str], lots: list[int]) -> str:
    parts = []
    if labels:
        parts.append("SECDIVLAB IN (" + ", ".join(f"'{label}'" for label in labels) + ")")
    if lots:
        parts.append("(SECDIVTYP='L' AND GOVLOT IN (" + ", ".join(f"'{n}'" for n in lots) + "))")
    return f"FRSTDIVID='{first_div_id}' AND ({' OR '.join(parts)})"


def query_params(where: str, fields: str, *, geometry: bool) -> dict[str, str]:
    return {
        "where": where,
        "outFields": fields,
        "returnGeometry": "true" if geometry else "false",
        "outSR": "4326",
        "geometryPrecision": "6",
        "f": "json",
    }


def point_params(lat: float, lon: float) -> dict[str, str]:
    return {
        "geometry": f"{lon:.6f},{lat:.6f}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": POINT_FIELDS,
        "returnGeometry": "false",
        "f": "json",
    }


def features(payload: Any) -> list[dict]:
    """The features of an ArcGIS query answer, or [] for anything else."""
    rows = payload.get("features") if isinstance(payload, dict) else None
    return [f for f in rows if isinstance(f, dict)] if isinstance(rows, list) else []


def attributes(feature: dict) -> dict:
    attrs = feature.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def _rings(feature: dict) -> list[list[list[float]]]:
    geometry = feature.get("geometry")
    rings = geometry.get("rings") if isinstance(geometry, dict) else None
    return (
        [r for r in rings if isinstance(r, list) and len(r) >= 3] if isinstance(rings, list) else []
    )


def extent(feats: list[dict]) -> dict | None:
    """Bounding box and area-weighted centroid of a set of polygons, in lat/lon.

    Uses the shoelace formula on longitude/latitude, which is accurate enough
    over a township. Holes, wound the other way, subtract themselves.
    """
    xs, ys = [], []
    area_sum = cx_sum = cy_sum = 0.0
    for feature in feats:
        for ring in _rings(feature):
            pts = [(float(p[0]), float(p[1])) for p in ring if len(p) >= 2]
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
            a = cx = cy = 0.0
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=False):
                cross = x0 * y1 - x1 * y0
                a += cross
                cx += (x0 + x1) * cross
                cy += (y0 + y1) * cross
            area_sum += a
            cx_sum += cx
            cy_sum += cy
    if not xs:
        return None
    if abs(area_sum) > 1e-15:
        lon, lat = cx_sum / (3 * area_sum), cy_sum / (3 * area_sum)
    else:
        lon, lat = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return {
        "centroid": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "bbox": {
            "south": round(min(ys), 6),
            "west": round(min(xs), 6),
            "north": round(max(ys), 6),
            "east": round(max(xs), 6),
        },
    }


def acres(feats: list[dict]) -> float | None:
    values = [attributes(f).get("GISACRE") for f in feats]
    numbers = [float(v) for v in values if isinstance(v, int | float)]
    return round(sum(numbers), 2) if numbers else None


def legal_label(
    meridian: str, township: str, rng: str, section: int | None, parts: list[str]
) -> str:
    """A description in the conventional order: parts, section, township, range, meridian."""
    head = ", ".join(parts) + " " if parts else ""
    sec = f"Sec. {section}, " if section else ""
    return f"{head}{sec}T{township} R{rng}, {MERIDIANS.get(meridian, meridian)}"


def describe_point(attrs: dict) -> dict:
    """What a point lies in, from one layer-3 (or layer-1) row."""
    code = str(attrs.get("PRINMERCD") or "").zfill(2)
    t = f"{int(attrs['TWNSHPNO'])}{attrs['TWNSHPDIR']}" if attrs.get("TWNSHPNO") else None
    r = f"{int(attrs['RANGENO'])}{attrs['RANGEDIR']}" if attrs.get("RANGENO") else None
    section = int(attrs["FRSTDIVNO"]) if str(attrs.get("FRSTDIVNO") or "").isdigit() else None
    typ = attrs.get("SECDIVTYP")
    part = None
    if typ == "L" and attrs.get("GOVLOT"):
        part = f"Lot {attrs['GOVLOT']}"
    elif typ in ("A", "B") and attrs.get("SECDIVLAB"):
        part = attrs["SECDIVLAB"]
    return {
        "state": attrs.get("STATEABBR"),
        "meridian_code": code if code in MERIDIANS else None,
        "meridian_name": MERIDIANS.get(code),
        "township": t,
        "range": r,
        "section": section,
        "subdivision": part,
        "plss_id": attrs.get("PLSSID"),
        "section_id": attrs.get("FRSTDIVID"),
        "subdivision_id": attrs.get("SECDIVID"),
        "description": legal_label(code, t, r, section, [part] if part else [])
        if t and r
        else None,
        "steward": attrs.get("STEWARD"),
    }
