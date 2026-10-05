"""Ask the live services what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check

A few calls, paced by the client itself, each checking that the services
still answer in the shape the server reads. Not collected by pytest, never
run in CI.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from us_places_mcp import server
from us_places_mcp.config import load_config
from us_places_mcp.fetch import Fetcher

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
]


async def main() -> int:
    cfg = load_config()
    with tempfile.TemporaryDirectory() as cache:
        server.holder.config = cfg
        server.holder.fetcher = Fetcher(
            Path(cache),
            {
                urlsplit(cfg.overpass_url).hostname: server.OVERPASS_INTERVAL,
                urlsplit(cfg.plss_url).hostname: server.PLSS_INTERVAL,
            },
            timeout=cfg.timeout,
            contact=cfg.contact,
        )
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
        await server.holder.fetcher.aclose()
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
