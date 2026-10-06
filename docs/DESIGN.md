# Design

## The question it answers

"Which office holds the record?" depends on who governed the place on the
date of the event. Counties were created and divided constantly, a new county
did not take its parent's earlier records, and federal land was described by a
survey grid, not by address. Genealogy software stores where an event happened
as the place is named now. This server bridges the two.

## Sources, and why these

- **The Newberry atlas, through OpenHistoricalMap.** The atlas is the
  authority on US county boundaries, dated to the day with statutes. Newberry
  offers downloads but no API; OpenHistoricalMap imported it and its Overpass
  API answers point-in-polygon queries with no key, under CC0.
- **BLM's national PLSS (CadNSDI).** The documented, keyless ArcGIS service
  that turns a township, range and section into geometry and back.
- **USGS's GNIS, live and as archived in August 2021.** The live service is
  the official gazetteer; the archive is the only place the cemeteries,
  churches, schools and post offices it dropped in 2021 are still listed. Both
  are searched for the same name, and a feature in both is reported once.
- **TNM Access for the historical topographic maps,** the documented route
  to USGS's scans, with TopoView linked for the formats TNM lacks.
- **Blevins and Helbock's post offices,** the fullest list of small places
  that are gone, with dates. CC0 on Harvard Dataverse.
- **Nothing scraped.** GLO Records has no public API since its July 2026
  rebuild, so the server builds links and does not fetch the site.

## Shape of the results

- **Status words, not just lists.** `county_at` says `one`,
  `changed_during_period`, `contested`, `none` or `no_coverage`, so a model
  cannot miss a dispute or a mid-year change in a list of holders.
- **The chain, always.** The whole succession for the point comes back, so the
  answer for one date shows what came before and after.
- **Warnings, not guesses.** The parser reports what it inferred; the locator
  reports when BLM's data lacks the subdivision asked for and what it does
  hold.
- **Arguments, not results, for the National Archives.** MCP servers cannot
  call each other; `find_land_entry_file` returns the exact arguments for
  nara-catalog-mcp.
- **Which source answered.** `find_place_name` says whether the live GNIS or
  the 2021 archive found each place, and gives a source that failed its own
  error, so an outage is never read as "not there".

## Downloaded datasets

The post-office list and the GNIS archive are files, not services. Each is
downloaded once, when a tool first needs it (the archive a state at a time,
so a search in Pennsylvania costs 9.8 MB, not the 86 MB national file), into
`<cache dir>/data`. It is checked against the checksum its publisher states
before anything is kept, loaded into SQLite with the standard library, and
read locally from then on. The result that caused a download says so. Only
the classes GNIS dropped are kept from the archive; the rest are live.

## Courtesy

One request at a time per service, two seconds apart for OpenHistoricalMap,
half a second for BLM and a second for USGS and Dataverse; identical calls in
flight joined; county answers cached 90 days, GNIS and map answers 30, survey
answers until refreshed; datasets downloaded once. The User-Agent names the
project, and `US_PLACES_CONTACT` adds the operator's address.

## Out of scope, by decision

- **Scraping GLO Records,** until BLM offers a sanctioned route.
- **Writing anywhere.**
- **Townships and church parishes as jurisdictions:** the atlas is counties
  only.
- **Each topo scan's own metadata.** It separates the survey, edit and
  imprint years, at one more request per scan.
- **A local copy of the atlas.** The Newberry shapefiles are free to reuse and
  would make the server independent of OpenHistoricalMap, at the cost of a
  large download and a geometry library. Worth adding if the Overpass server
  proves unreliable.

## Tests

Mocked with respx against recorded answers; never live. The two datasets are
tested on slices of the real files, byte for byte, never the whole. The parser
has golden cases, including a run-on description from real family papers. Contract tests
pin the tool surface, the descriptions' warnings, the read-only annotations,
and that no tool raises when a service fails. `tests/live_check.py` makes a
few paced live calls by hand.
