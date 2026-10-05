# Service notes

What the two services actually do, observed on 2026-10-05.

## OpenHistoricalMap Overpass (`overpass-api.openhistoricalmap.org`)

- `POST /api/interpreter` with a form field `data` holding Overpass QL. No key.
  Answers are CC0.
- **Point in county:**
  `[out:json][timeout:60];is_in(39.896,-80.179)->.a;rel(pivot.a)[boundary=administrative][admin_level=6];out tags;`
  returned 17 relations for Waynesburg, Pa. (14 KB, about 1.3 s): every
  version of every county that held the spot, Pennsylvania's and Virginia's.
- **One relation per county *version*.** Tags on each: `name`, `start_date`,
  `end_date` (absent on the current version), `start_event` ("GREENE created
  from WASHINGTON."), `nl_ahcb:source` (the statute), `nl_ahcb:id_text`
  (`pas_greene`), `nl_ahcb:id`, `nl_ahcb:version`, `import:county_type`
  (`county`, `district`, …), `source:name` ("Newberry Library Atlas of
  Historical County Boundaries"), `license` (`CC0-1.0`), `wikidata`,
  `wikipedia`.
- **`nl_ahcb:id_text` prefixes name the atlas's state file,** which is the
  *modern* state: `pas_` Pennsylvania, `vas_` Virginia, `wvs_` West Virginia,
  `ias_` Iowa, `mos_` Missouri. Monongalia County, created by Virginia, is
  `wvs_monongalia`.
- **Non-county areas** appear as `IA NCA 7` and the like; the event text says
  when one was "attached to" an organised county ("Non-County Area 7 attached
  to LINN …").
- **AHCB dates are day-exact.** OpenHistoricalMap's other data (the US
  national boundary, colonies at `admin_level=2`) sometimes carries a year
  alone (`1913`).
- **State-level queries are expensive.** The same point with
  `admin_level~"^(2|4)$"` returned 605 KB, mostly national-boundary versions,
  so the state is read from the county's `nl_ahcb:id_text` instead.
- **County history by name:**
  `rel[boundary=administrative][admin_level=6]["nl_ahcb:id_text"~"^pas_"]["name"~"^Greene( County)?$",i];out tags;`
  returned Greene's two versions in 0.5 s.
- Errors: Overpass reports a timeout or memory abort as a `remark` inside a
  200 answer; it answers 429 when busy and 504 on gateway timeout.

## BLM National PLSS, CadNSDI (`gis.blm.gov`)

`/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer`, ArcGIS
11.5, `maxRecordCount` 2000. No key. Layers: 0 state boundaries, 1 townships,
2 sections ("first divisions"), 3 quarter-quarters and lots ("second
divisions"), each layer carrying the ids of those above it.

- Township: `STATEABBR='IA' AND PRINMERCD='05' AND TWNSHPNO='084' AND
  TWNSHPDIR='N' AND RANGENO='039' AND RANGEDIR='W'` → `PLSSID
  IA050840N0390W0`, `TWNSHPLAB '84N 39W'`.
- Section: `PLSSID='IA050840N0390W0' AND FRSTDIVNO='18'` → `FRSTDIVID
  IA050840N0390W0SN180`.
- Quarter-quarters: `FRSTDIVID=…SN180` → 16 rows, `SECDIVLAB` `NENE` … with
  `GISACRE` ≈ 40.9. Ids end `A<label>`.
- Lots: `SECDIVTYP 'L'`, `SECDIVLAB 'L 2'`, `GOVLOT '2'`, id ending `L2`.
  Other types: `A` aliquot, `B` remainder aliquot, `O` unnumbered lot.
- Some sections have **no** second divisions (Nebraska T1N R25W sec. 22: one
  layer-3 row, every field null).
- A point query on layer 3 (`geometry=lon,lat`, `inSR=4326`,
  `spatialRel=esriSpatialRelIntersects`) returns the full row: state,
  meridian, township, range, section and subdivision. The `identify`
  operation returns field *aliases* and the string `"Null"`, so it is not used.
- `returnGeometry=true&outSR=4326` returns rings in lon/lat.

### Meridian codes and names

`PRINMERCD` is two digits, except that North Dakota's rows carry `5`. Names
in `PRINMER` are unreliable: `05` also appears as `05` and null; `18` appears
as "Louisiana Meridian" and "St. Helena Meridian"; `21` as three spellings of
Mount Diablo; `27` as "San Bernardino Meridian" in AZ and CA but "Mount
Diablo Meridian" in NV; `45` as both "Umiat" and "Kateel River". The server
keys on the code and names it from its own table. Stray codes left out of the
per-state table: `05` in KS and MS, `18` in MS, `27` in NV.

## GLO Records links

Verified 2026-10-04 (see the research spec this server came from): a search
link is `https://glorecords.blm.gov/s/advanced-search?searchTerm=` followed by
the URL-encoded path `/search?q=…&page=1&pageSize=25`. The `State` and
`documenttype` parameters are taken from the site's code, not verified. A
record link is `…/s/advanced-search#/searchresults?documentid=<id>`.

## National Archives bridge

`record_group_number "49"` with title `Lincoln Land Office (Nebraska),
Homestead Final Certificate No. 12018` returned NAID 63668992 (21 images)
first, and also certificate 7054: the Catalog's title search matches words.
