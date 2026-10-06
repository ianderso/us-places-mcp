"""Ask the live services what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check [--fresh-data]

A few calls, paced by the client itself, each checking that the services
still answer in the shape the server reads. Answers are cached in a temporary
directory, so every check asks the service. The downloaded datasets (31 MB of
post offices, 9.8 MB of Pennsylvania's GNIS archive) are kept in the usual
data directory and reused; ``--fresh-data`` downloads and checks them again
into the temporary directory. Not collected by pytest, never run in CI.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from us_places_mcp import server
from us_places_mcp.config import load_config

CHECKS: list[tuple[str, dict, Callable[[dict], bool], str]] = [
    (
        "county_at",
        {"latitude": 39.896, "longitude": -80.179, "date": "1795-06-01"},
        lambda r: [h["county"] for h in r.get("held_by", [])] == ["Washington County"],
        "Waynesburg, Pa., was in Washington County in mid-1795",
    ),
    (
        "county_at",
        {"latitude": 39.896, "longitude": -80.179, "date": "1775"},
        lambda r: r.get("status") == "contested",
        "Pennsylvania and Virginia both claimed it in 1775",
    ),
    (
        "county_history",
        {"county": "Greene", "state": "PA"},
        lambda r: [v["from"] for v in r.get("versions", [])][:1] == ["1796-02-09"],
        "Greene County, Pa., was created on 9 February 1796",
    ),
    (
        "plss_locate",
        {"state": "IA", "description": "E½NE Sec. 18, T84N R39W, 5th P.M."},
        lambda r: (
            r["tracts"][0].get("precision") == "aliquot"
            and 42.08 < r["tracts"][0]["centroid"]["lat"] < 42.10
        ),
        "the Lincoln patent's E½NE of section 18 locates to two quarter-quarters",
    ),
    (
        "plss_from_point",
        {"latitude": 42.0877, "longitude": -95.43},
        lambda r: r.get("section") == 18 and r.get("township") == "84N",
        "a point names its section",
    ),
    (
        "plss_locate",
        {"state": "NE", "description": "S½NW and N½SW Sec. 22, T1N R25W"},
        lambda r: r["tracts"][0].get("precision") == "section",
        "S1422's section, which BLM holds only as a whole",
    ),
    (
        "historical_topo_maps",
        {"latitude": 39.896, "longitude": -80.179},
        lambda r: (
            (r["maps"][0]["date"], r["maps"][0]["scale"], r["maps"][0]["quadrangle"])
            == (1901, 62500, "Waynesburg, PA")
            and r["maps"][0]["geotiff"].endswith(".tif")
            and r["covering_this_point"] >= 16
        ),
        "Waynesburg, Pa.: the oldest map is the 1901 15-minute Waynesburg sheet",
    ),
    (
        "post_offices",
        {"state": "SD", "county": "Kingsbury", "year": 1890},
        lambda r: (
            r["total"] == 15
            and {"DESMET", "LAKE PRESTON", "ARLINGTON", "SPRINGLAKE"}
            <= {o["name"] for o in r["offices"]}
        ),
        "fifteen post offices in Kingsbury County, S.D., were open in 1890",
    ),
    (
        "find_place_name",
        {"name": "Green Mount Cemetery", "state": "PA", "county": "Greene"},
        lambda r: (
            r["answered_by"] == ["archive_2021"]
            and r["sources"]["live"] == {"found": 0}
            and r["places"][0]["gnis_id"] == 1176092
            and r["places"][0]["topo_quad"] == "Waynesburg"
        ),
        "Green Mount Cemetery, Waynesburg, dropped from GNIS in 2021, is in the archive",
    ),
    (
        "find_place_name",
        {"name": "Waynesburg", "state": "PA", "feature_class": "Populated Place"},
        lambda r: r["answered_by"] == ["live"] and r["places"][0]["gnis_id"] == 1190723,
        "the live GNIS still names Waynesburg",
    ),
]


async def main(fresh_data: bool) -> int:
    cfg = load_config()
    with tempfile.TemporaryDirectory() as cache:
        data = Path(cache) / "data" if fresh_data else cfg.data_dir
        server.holder.config = replace(cfg, datasets_dir=data)
        server.holder.fetcher = server.build_fetcher(cfg, Path(cache))
        failed = 0
        for tool, args, check, meaning in CHECKS:
            result = json.loads((await server.mcp.call_tool(tool, args)).content[0].text)
            try:
                ok = "error" not in result and bool(check(result))
            except (KeyError, IndexError, TypeError):
                ok = False
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {tool}: {meaning}")
            if not ok:
                print(f"      got: {json.dumps(result)[:400]}")
            if "downloaded" in result:
                got = result["downloaded"]
                print(f"      downloaded {got['file']}, {got['bytes']:,} bytes: {got['verified']}")
        await server.holder.fetcher.aclose()
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--fresh-data" in sys.argv[1:])))
