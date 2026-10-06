# us-places-mcp

[![CI](https://github.com/ianderso/us-places-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/us-places-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/us-places-mcp)](https://pypi.org/project/us-places-mcp/)

<!-- mcp-name: io.github.ianderso/us-places-mcp -->

An [MCP](https://modelcontextprotocol.io) server for **where things were,
then**. Records follow the jurisdiction that held a place on the date of the
event, not today's: a 1795 deed for a farm now in Greene County,
Pennsylvania, is in Washington County's books, because Greene was carved out
the next year. This server answers the questions that decide which office to
write to:

- **Which county held this spot on that date?** From the Newberry Library's
  *Atlas of Historical County Boundaries*, which records every creation and
  boundary change of every US county from 1629 to 2000, dated to the day,
  with the act behind it. OpenHistoricalMap imported the atlas and serves it
  free (CC0); this server asks it.
- **Where is this land description on the ground?** "E½NE Sec. 18, T84N
  R39W, 5th P.M." becomes a centroid, a bounding box and BLM's ids, from the
  Bureau of Land Management's national Public Land Survey data. A map pin
  becomes a land description the other way.
- **Where is the case file behind this land patent?** The patent is the end
  of a process. The file at the National Archives holds the application and,
  for a homestead, years of residence, witnesses and citizenship papers. The
  server says which file and which series, and builds the search.
- **Where was Mount Hope Cemetery, or Hines Corners?** USGS's Geographic
  Names Information System (GNIS) names and places every feature it knows,
  including vanished towns marked "(historical)". In 2021 it dropped
  cemeteries, churches, schools, post offices and other built features; the
  server also searches the archive USGS kept from August 2021, and says which
  answered.
- **Which post offices were there, and when?** Richard Helbock's list of
  every US post office from 1639 to 2000, geocoded by Cameron Blevins: 166,140
  offices with the years they opened and closed. A post office is often the
  only trace of a hamlet.
- **Which old maps show the spot?** Every USGS topographic map since 1884
  that covers a point, oldest first, with links to the scans.

Nothing here writes anywhere, and nothing here keeps a family tree. It sits
well beside [nara-catalog-mcp](https://github.com/ianderso/nara-catalog-mcp),
which can run the archive searches this server builds,
[familysearch-mcp](https://github.com/ianderso/familysearch-mcp) and
[snac-archives-mcp](https://github.com/ianderso/snac-archives-mcp).

This is an independent project. It is not affiliated with, endorsed by, or
supported by the Newberry Library, OpenHistoricalMap, the Bureau of Land
Management, the US Geological Survey, Harvard Dataverse, the dataset's
authors or the National Archives.

## Tools

The server publishes twelve tools, all read-only and annotated so for the
client. Five make no network call at all.

**Jurisdiction at a date**

| Tool | Purpose |
| --- | --- |
| `county_at` | The county (or counties) that held a point on a date: a day, a month or a year. Returns the holder, its dates, the event and statute that made it, the whole chain of counties for that spot, changes within a year (check those by hand), and whether two governments contested it. |
| `county_history` | Every version of one county: created when, from what, and each later change, with statutes. |

**Federal land**

| Tool | Purpose |
| --- | --- |
| `parse_legal_description` | Read a land description, however it is written (`E½NE`, `E2NE`, `E 1/2 NE 1/4`, "the east half of the northeast quarter", GLO's padded `0840N`, lots, several tracts), into its parts, with quarter-quarters and warnings for anything guessed. Offline. |
| `plss_locate` | Place a description on the map: centroid, bounding box, acreage and BLM's ids, to the township, section, quarter-quarter or lot. |
| `plss_from_point` | Name the survey tract at a point: township, range, section and quarter-quarter. |
| `public_land_state` | Was this state federal land? If not, who granted first title and where those records are; if so, its meridians and special cases. Offline. |

**Vanished places and old maps**

| Tool | Purpose |
| --- | --- |
| `find_place_name` | A named place in GNIS: its point, class, state and county. Searches the live GNIS and, given a state, the archive of August 2021 that keeps the cemeteries, churches, schools, post offices and buildings GNIS dropped that year; says which answered. |
| `post_offices` | Which US post offices existed, 1639-2000: by name, by state and today's county, or around a point, and in a given year. Each with its years, whether it ran continuously, and its point if it was geocoded. |
| `historical_topo_maps` | Every USGS topographic map covering a point, oldest first: date, scale and quadrangle, with GeoPDF, GeoTIFF and JPEG preview links, and a TopoView link for JPEG and KMZ. |

**From patent to case file**

| Tool | Purpose |
| --- | --- |
| `find_land_entry_file` | From a patent's Authority: the kind of entry, what its file holds, which National Archives series has it, ready-made arguments for nara-catalog-mcp's `search_records_advanced`, and how to order the file if it is not online. Offline. |
| `glo_links` | A link to a search, or to one record, on BLM's General Land Office Records site, for you to open. Offline. |
| `cache_status` | This session's live calls and cache hits, and the datasets downloaded so far. Offline. |

## Setup

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/). There is
no key to request.

```bash
uvx us-places-mcp
```

or from a clone:

```bash
git clone https://github.com/ianderso/us-places-mcp
cd us-places-mcp
uv sync
uv run us-places-mcp   # stdio server, usually launched by the client
```

### Claude Desktop

```json
{
  "mcpServers": {
    "places": {
      "command": "uvx",
      "args": ["us-places-mcp"]
    }
  }
}
```

If the server fails to start because `uvx` cannot be found, give the full path
that `which uvx` prints as the `command`.

### Claude Code

```bash
claude mcp add places -- uvx us-places-mcp
```

## Configuration

Nothing is required. A `.env` file in the directory the server starts in
supplies anything the environment does not; only that directory is read.

| Variable | Meaning |
| --- | --- |
| `US_PLACES_OVERPASS_URL` | OpenHistoricalMap's Overpass endpoint. Default `https://overpass-api.openhistoricalmap.org/api/interpreter`. |
| `US_PLACES_PLSS_URL` | BLM's national PLSS map service. Default `https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer`. |
| `US_PLACES_GNIS_URL` | USGS's GNIS map service. Default `https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer`. |
| `US_PLACES_GNIS_ARCHIVE_URL` | The folder of GNIS state files from August 2021. Default `https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/Archive/MainDomestic`. |
| `US_PLACES_TNM_URL` | The National Map's TNM Access products API. Default `https://tnmaccess.nationalmap.gov/api/v1/products`. |
| `US_PLACES_DATAVERSE_URL` | Harvard Dataverse, which holds the post-office dataset. Default `https://dataverse.harvard.edu`. |
| `US_PLACES_CACHE_DIR` | Response cache directory; downloaded datasets go in its `data` folder. Default `~/.cache/us-places-mcp`. |
| `US_PLACES_TIMEOUT` | HTTP timeout in seconds. Default 60. |
| `US_PLACES_CONTACT` | An email address or URL added to the User-Agent, so the services can reach you. Optional, and courteous. |

Every URL must be https. Their hosts, and Dataverse's file store
(`dvn-cloud-iqss.s3.amazonaws.com`, where it redirects downloads), are the
only ones the server will contact.

## Being a good guest

OpenHistoricalMap's Overpass server runs on donated capacity and publishes no
rate limit. The server sends one request at a time to each service, two
seconds apart for OpenHistoricalMap, half a second for BLM and a second for
USGS and Dataverse, joins identical calls in flight, and caches answers on
disk: county answers for 90 days, GNIS and map answers for 30, survey answers
until you pass `refresh=true`. A 429 or a 5xx is retried three times with
back-off, then reported as `rate_limited` or `upstream_error`, which is never
the same as "nothing here".

## Downloaded data

Two sources are files rather than services, so the server downloads them once
and reads them locally. Nothing is downloaded until a tool needs it, and the
result that triggered a download says so: what, how big, how it was checked
and where it was saved.

| Data | When | Size | Checked against |
| --- | --- | --- | --- |
| US Post Offices (Blevins and Helbock, [doi:10.7910/DVN/NUKCNA](https://doi.org/10.7910/DVN/NUKCNA), CC0) | The first `post_offices` call | 31 MB download, 21 MB on disk | The MD5 Dataverse publishes for the file |
| GNIS state file of 25 August 2021 (USGS, public domain) | The first `find_place_name` search in that state | Up to 17 MB per state (Pennsylvania 9.8 MB); only the dropped classes are kept, about 6 MB for Pennsylvania | The ETag USGS's bucket reports (an MD5, or the MD5 of the upload's parts) |

Both are stored as SQLite files in `data` under the cache directory
(`~/.cache/us-places-mcp/data` by default), never in the repository. A file
that fails its check is deleted and the tool reports `download_failed`.
`cache_status` lists what is there; delete the folder to start again.

## How to read what comes back

- **The county then, not now.** A record was made by the county that held the
  place on the day. A new county does not take its parent's earlier records,
  so a deed from before Greene County existed is in Washington County's books
  still.
- **Check dates near a change.** `boundary_change_within_a_year` lists changes
  close to your date. Laws took effect on stated days, but offices took time to
  organise; records from those months can be in either county.
- **"Attached to".** Before an area was organised as a county it was often
  attached to a neighbour for administration, and that neighbour kept its
  records. `county_at` reads this from the atlas's event text.
- **Contested ground.** Pennsylvania and Virginia both governed the
  Waynesburg area in the 1770s, and similar disputes ran elsewhere.
  `"status": "contested"` means look in both governments' records.
- **The atlas files counties under today's state.** Monongalia County was
  created by Virginia but is filed under West Virginia; the event text says
  which government acted.
- **The atlas ends in 2000** and holds counties only: not towns, townships or
  parishes as church units.
- **A located tract is not a house.** A section's centre is up to half a mile
  from any point in it, and BLM's data is a modern compilation that can differ
  from the original plat near correction lines and water. Lotted sections
  (along a township's north and west edges, or by water) have lots where a
  regular section has quarter-quarters.
- **A parse is a reading of a reading.** `parse_legal_description` keeps the
  original text and says what it guessed: a section number with no "Sec.", a
  meridian taken from the state.
- **A patent proves a conveyance, on its signature date.** The entry was years
  earlier: homesteaders lived on the land five years before final proof, and
  mid-century backlogs put years between purchase and signature. The
  Homestead Act took effect in 1863, so an "1856 homestead" in a family story
  is a cash, credit, preemption or warrant entry.
- **The patentee may never have seen the land.** Military bounty-land warrants
  were bought and sold; the veteran is in the warrant file, the patentee may be
  a speculator.
- **No federal patents in state-land states.** The thirteen colonies, Maine,
  Vermont, Kentucky, Tennessee, West Virginia, Texas and Hawaii granted their
  own land. A nil search there means nothing; `public_land_state` says where
  first title was recorded.
- **Old GLO links are dead.** BLM rebuilt glorecords.blm.gov in July 2026, and
  older record links now land on the home page. Cite a patent by its accession
  number, document number, state and signature date.
- **GNIS names are today's official names,** not the spellings in old
  records. GNIS writes out Mount, Fort and Saint and drops possessive
  apostrophes (Pikes Peak); the server does the same to what you type. A place
  that is gone is often listed as "Name (historical)". A GNIS county is
  today's county: pass the point to `county_at`.
- **The 2021 archive is frozen.** Cemeteries, churches, schools, post offices
  and buildings are as GNIS held them on 25 August 2021, and USGS no longer
  maintains them. `topo_quad` names the 1:24,000 map each was read from.
- **A map's date is the date of its survey or edit,** not of the ground on the
  day you care about, and a reprint keeps the old date. Several scans often
  share a quadrangle and a date: later printings or other copies of one
  edition. Compare them. At 1:62,500 and larger, maps show roads, churches,
  schools and cemeteries, and often houses; a house symbol names no one.
- **A post office's years are Helbock's.** A renaming, or a change to a
  branch, ends one record and may start another, so "discontinued" can mean
  renamed. An office closed for under ten years stays one record, marked
  `continuous: false`. Moves within a town are not recorded.
- **A post office's county is today's.** Helbock listed the county in which
  the site lies now. For the county that kept the records then, pass the
  office's point and year to `county_at`.
- **A third of the post offices have no point.** Blevins placed an office by
  matching its name to a GNIS feature; offices that matched nothing have no
  coordinates, so a search around a point misses them. Search the county too.
  `gnis_match` shows what each was matched to and how closely.
- **Postmasters' names** are in the Records of Appointment of Postmasters at
  the National Archives (microfilm M1131 for 1789-1832, M841 for 1832-1971).

## Deliberately not here

- **Searching GLO itself.** The rebuilt site has no public API. The server
  builds links for you to open; it does not fetch the site.
- **Townships and church parishes as jurisdictions.** The atlas is counties
  only; GNIS names places but says nothing of who governed them.
- **Writing anywhere.**

## Security

- **A fixed set of hosts.** A request hook refuses any request not for a
  configured service or Dataverse's file store, so a value a model passes in
  cannot make the server fetch another site. A download follows a redirect
  only to one of those hosts.
- **Downloads are checked before they are kept,** against the checksum the
  publisher states, and are capped in size.
- **Inputs are validated** before they reach a query: coordinates as finite
  numbers in range, states and GNIS classes against tables, survey numbers as
  digits, and a county name escaped character by character into the Overpass
  query. A place name reaches GNIS only as `find`'s search text, never inside
  a where clause, and local searches use bound parameters.
- **Event, statute and place-name text is data.** It comes from the sources
  and reaches the model verbatim; the server's instructions tell the model to
  treat it as data, never as instructions.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches a service
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # a few paced calls to every live service
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [docs/API-NOTES.md](docs/API-NOTES.md)
for what was observed of each service and when, and
[docs/DESIGN.md](docs/DESIGN.md) for why the server is shaped this way.

## Credits

County boundaries: the Newberry Library's *Atlas of Historical County
Boundaries* (John H. Long, editor), as imported into
[OpenHistoricalMap](https://www.openhistoricalmap.org) and released under CC0.
Survey data: the Bureau of Land Management's National PLSS (CadNSDI), a US
government work. Place names: the US Geological Survey's Geographic Names
Information System, a US government work. Maps: USGS's Historical Topographic
Map Collection, through The National Map. Post offices: Cameron Blevins and
Richard W. Helbock, *US Post Offices*, Harvard Dataverse,
[doi:10.7910/DVN/NUKCNA](https://doi.org/10.7910/DVN/NUKCNA), released under
CC0.

## License

[MIT](LICENSE).
