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

## Courtesy

One request at a time per service, two seconds apart for OpenHistoricalMap
and half a second for BLM; identical calls in flight joined; county answers
cached 90 days and survey answers until refreshed. The User-Agent names the
project, and `US_PLACES_CONTACT` adds the operator's address.

## Out of scope, by decision

- **Scraping GLO Records,** until BLM offers a sanctioned route.
- **Writing anywhere.**
- **Towns, townships and church parishes:** the atlas is counties only.
- **A local copy of the atlas.** The Newberry shapefiles are free to reuse and
  would make the server independent of OpenHistoricalMap, at the cost of a
  large download and a geometry library. Worth adding if the Overpass server
  proves unreliable.

## Tests

Mocked with respx against recorded answers; never live. The parser has golden
cases, including a run-on description from real family papers. Contract tests
pin the tool surface, the descriptions' warnings, the read-only annotations,
and that no tool raises when a service fails. `tests/live_check.py` makes a
few paced live calls by hand.
