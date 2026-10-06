"""USGS historical topographic maps, through The National Map's TNM Access API.

The Historical Topographic Map Collection holds a scan of every edition of
every USGS topographic map since the program began in 1884, at scales from
1:24,000 to 1:250,000. TNM Access lists the scans whose sheet covers a
bounding box; a point is a bounding box of zero size. Each item is one scan
with a GeoPDF, a GeoTIFF (``urls``) and a small JPEG preview.

Each item's ``publicationDate`` is the year printed on the map (as
``YYYY-01-01``), and the title carries the scale and the quadrangle's name:
"USGS 1:62500-scale Quadrangle for Waynesburg, PA 1901". The year is the
date of the survey or of the edit behind that edition. Several scans often
share a quadrangle and a year: they are later printings, or other copies,
of the same edition.
"""

from __future__ import annotations

import re
from typing import Any

DATASET = "Historical Topographic Maps"

#: More scans than cover any one point; the largest seen was 37.
MAX_ITEMS = 1000

#: TopoView, USGS's own viewer of the same scans, which also offers them as
#: JPEG and KMZ. The fragment is zoom/latitude/longitude.
TOPOVIEW = "https://ngmdb.usgs.gov/topoview/viewer/#13/{lat:.4f}/{lon:.4f}"

_TITLE = re.compile(r"1:([\d,]+)-scale Quadrangle for (.+?)\s+(\d{4})\s*$")
_SCAN = re.compile(r"_(\d+)_(\d{4})_[\d]+_geo\.(?:pdf|tif)$")


def params(lat: float, lon: float) -> dict[str, str]:
    """Query parameters for every historical topographic scan covering a point."""
    point = f"{lon:.5f},{lat:.5f}"
    return {"datasets": DATASET, "bbox": f"{point},{point}", "max": str(MAX_ITEMS)}


def _year(text: object) -> int | None:
    m = re.match(r"(\d{4})", str(text or ""))
    return int(m.group(1)) if m else None


def _url(value: object) -> str | None:
    return value if isinstance(value, str) and value.startswith("https://") else None


def scan(item: object) -> dict | None:
    """One scan, compact. None if the item is not a historical topographic map."""
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "")
    m = _TITLE.search(title)
    if not m:
        return None
    urls = item.get("urls") if isinstance(item.get("urls"), dict) else {}
    geopdf = _url(urls.get("GeoPDF")) or _url(item.get("downloadURL"))
    geotiff = _url(urls.get("GeoTIFF"))
    scan_id = _SCAN.search(geopdf or geotiff or "")
    return {
        "date": _year(item.get("publicationDate")) or int(m.group(3)),
        "scale": int(m.group(1).replace(",", "")),
        "quadrangle": m.group(2),
        "extent": item.get("extent") or None,
        "scan_id": int(scan_id.group(1)) if scan_id else None,
        "geopdf": geopdf,
        "geotiff": geotiff,
        "preview_jpg": _url(item.get("previewGraphicURL")),
        "metadata": _url(item.get("metaUrl")),
    }


def scans(payload: Any) -> list[dict]:
    """Every scan in a TNM Access answer, oldest first, then largest scale first."""
    items = payload.get("items") if isinstance(payload, dict) else None
    out = [s for i in (items if isinstance(items, list) else []) if (s := scan(i))]
    return sorted(out, key=lambda s: (s["date"], s["scale"], s["quadrangle"], s["scan_id"] or 0))


def total(payload: Any) -> int | None:
    """How many scans TNM Access says cover the point."""
    value = payload.get("total") if isinstance(payload, dict) else None
    return value if isinstance(value, int) else None


def reprinted(maps: list[dict]) -> bool:
    """True if two scans share a quadrangle, scale and date."""
    seen = set()
    for m in maps:
        key = (m["quadrangle"], m["scale"], m["date"])
        if key in seen:
            return True
        seen.add(key)
    return False
