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

Nothing here writes anywhere, and nothing here keeps a family tree. It sits
well beside [nara-catalog-mcp](https://github.com/ianderso/nara-catalog-mcp),
which can run the archive searches this server builds,
[familysearch-mcp](https://github.com/ianderso/familysearch-mcp) and
[snac-archives-mcp](https://github.com/ianderso/snac-archives-mcp).

This is an independent project. It is not affiliated with, endorsed by, or
supported by the Newberry Library, OpenHistoricalMap, the Bureau of Land
Management or the National Archives.

## Tools

The server publishes nine tools, all read-only and annotated so for the
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

**From patent to case file**

| Tool | Purpose |
| --- | --- |
| `find_land_entry_file` | From a patent's Authority: the kind of entry, what its file holds, which National Archives series has it, ready-made arguments for nara-catalog-mcp's `search_records_advanced`, and how to order the file if it is not online. Offline. |
| `glo_links` | A link to a search, or to one record, on BLM's General Land Office Records site, for you to open. Offline. |
| `cache_status` | This session's live calls and cache hits. Offline. |

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
| `US_PLACES_CACHE_DIR` | Response cache directory. Default `~/.cache/us-places-mcp`. |
| `US_PLACES_TIMEOUT` | HTTP timeout in seconds. Default 60. |
| `US_PLACES_CONTACT` | An email address or URL added to the User-Agent, so either service can reach you. Optional, and courteous. |

Both URLs must be https. Their two hosts are the only ones the server will
contact.

## Being a good guest

OpenHistoricalMap's Overpass server runs on donated capacity and publishes no
rate limit. The server sends one request at a time to each service, two
seconds apart for OpenHistoricalMap and half a second for BLM, joins identical
calls in flight, and caches answers on disk: county answers for 90 days, survey
answers until you pass `refresh=true`. A 429 or a 5xx is retried three times
with back-off, then reported as `rate_limited` or `upstream_error`, which is
never the same as "nothing here".

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

## Deliberately not here

- **Searching GLO itself.** The rebuilt site has no public API. The server
  builds links for you to open; it does not fetch the site.
- **Towns, townships and church parishes.** The atlas is counties only.
- **Writing anywhere.**

## Security

- **Two hosts.** A request hook refuses any request not for the two configured
  services, so a value a model passes in cannot make the server fetch another
  site.
- **Inputs are validated** before they reach a query: coordinates as finite
  numbers in range, states against a table, survey numbers as digits, and a
  county name escaped character by character into the Overpass query.
- **Event and statute text is data.** It comes from the atlas and reaches the
  model verbatim; the server's instructions tell the model to treat it as data,
  never as instructions.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches either service
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # a few paced calls to both live services
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [docs/API-NOTES.md](docs/API-NOTES.md)
for what was observed of each service and when, and
[docs/DESIGN.md](docs/DESIGN.md) for why the server is shaped this way.

## Credits

County boundaries: the Newberry Library's *Atlas of Historical County
Boundaries* (John H. Long, editor), as imported into
[OpenHistoricalMap](https://www.openhistoricalmap.org) and released under CC0.
Survey data: the Bureau of Land Management's National PLSS (CadNSDI), a US
government work.

## License

[MIT](LICENSE).
