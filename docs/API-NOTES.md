# Service notes

What the services actually do, observed on the dates given.

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

## USGS GNIS (`carto.nationalmap.gov`)

Observed 2026-10-05 and 2026-10-06.
`/arcgis/rest/services/geonames/MapServer`, ArcGIS 11.3, `maxRecordCount`
2000, no key; "Data Refreshed October, 2026". Layers: 1 Incorporated Places
(Civil), 2 Unincorporated Places (Census), 3 Populated Places, 5 Landforms,
6 Streams (mouth), 7 Other Hydrographic Features, 8 Antarctica, 10 Crossings,
12-14 Historical cultural-political, hydrographic and physical points (names
end "(historical)"). Fields on each: `gaz_id`, `gaz_name`,
`gaz_featureclass`, `state_alpha`, `county_name`, `isunknowncoords` (2 on
every row checked). Geometry is a multipoint, except layer 7, which answered
a point (`x`, `y`).

- **No built features.** Grouping every layer by `gaz_featureclass` found no
  Cemetery, Church, School, Post Office, Building, Locale, Park, Dam, Mine,
  Airport, Bridge, Tower, Trail, Tunnel, Hospital, Forest, Reserve, Oilfield,
  Well, Harbor or Cave outside Antarctica. Military appears only in layer 12,
  as historical installations.
- **`find` searches every layer at once:** `searchText=Waynesburg`,
  `contains=true`, `searchFields=gaz_name`,
  `layers=1,2,3,5,6,7,10,12,13,14`, `layerDefs={"1": "state_alpha='PA'", ...}`,
  `sr=4326`. Case-insensitive; about 6 s for one state, where a single layer's
  `query` took 1.2 s. With `state_alpha='OH'` the same search returned only
  Ohio rows, so `layerDefs` does filter. "Mount Hope" with no state returned
  78 rows. Attribute values come back as strings.
- Exact names: `Borough of Waynesburg` (Civil), `Waynesburg` (Populated
  Place, `gaz_id` 1190723), `West Waynesburg Census Designated Place`.

### The archive of 25 August 2021 (`prd-tnm.s3.amazonaws.com`)

`StagedProducts/GeographicNames/Archive/MainDomestic/` holds
`XX_Features_20210825.txt` for each state, DC and the territories (0.8 MB for
DC to 17.3 MB for California; Pennsylvania 9.8 MB), plus `NationalFile.zip`
(85.7 MB), all last modified 2023-05-02. Pipe-delimited, UTF-8 with a BOM,
CRLF, 20 columns from `FEATURE_ID` to `DATE_EDITED`, with `MAP_NAME` the
1:24,000 quadrangle. `FEATURE_ID` equals the live `gaz_id` (Waynesburg is
1190723 in both).

- A state's file lists neighbours' features that reach into it: the PA file
  has 321 rows whose `STATE_ALPHA` is MD, NY, WV, NJ, OH, DE or KY.
- Names can contain double quotes (`"Old Main" Administration Building`), so
  the file is read with quoting off.
- Unknown coordinates are `Unknown` (DMS) and `0` (decimal).
- PA holds 70,231 rows; 41,584 are Pennsylvania features in the dropped
  classes (the file has 7,484 cemeteries, 4,319 churches, 7,198 schools and
  2,275 post offices).
  Green Mount Cemetery, Waynesburg, is `FEATURE_ID` 1176092, not in the live
  service.
- **ETags.** A file uploaded whole has its MD5 as ETag (SD:
  `0f35276a70aa03a425388037f25f185b`, the MD5 of the download). PA's is
  `e526524b9340323c4856316f60a9840f-2`, which is the MD5 of the MD5s of its
  8 MiB parts. A missing file answers 404 `NoSuchKey`.

## TNM Access (`tnmaccess.nationalmap.gov`)

Observed 2026-10-05 and 2026-10-06. `GET /api/v1/products?datasets=Historical
Topographic Maps&bbox=minX,minY,maxX,maxY&max=1000`, no key. A point given as
a bounding box of zero size works: Waynesburg (39.896, -80.179) returned 16
scans in 0.5 s; a box of about 20 by 10 km returned 37. A point in London
returned `total` 0.

- Each item is one scan: `title` ("USGS 1:62500-scale Quadrangle for
  Waynesburg, PA 1901"), `publicationDate` (`1901-01-01`, the year only),
  `extent` ("15 x 15 minute"), `urls` with `GeoPDF` and `GeoTIFF`,
  `previewGraphicURL` (a small JPEG), `metaUrl` (ScienceBase) and
  `boundingBox`. There is no full-size JPEG; TopoView
  (`ngmdb.usgs.gov/topoview/viewer/#zoom/lat/lon`, checked in a browser)
  offers the scans as JPEG and KMZ.
- Waynesburg has one 1901 and five 1904 scans of the 15-minute Waynesburg
  quadrangle (scan ids 222433; 170082-170084, 222435, 222437), four 1961
  scans at 1:24,000, and 1:100,000 and 1:250,000 sheets.
- The scan's FGDC metadata (`vendorMetaUrl`) separates "Date on Map", "Imprint
  Year" and "Survey Year", at one more request per scan; not used.
- **A bad request is a 200 that is not JSON:** `bbox=abc` answered
  `{errorMessage=[BadRequest] 'Value 'abc' of property bbox must be numeric
  and have at least four numbers' , errorType=Exception, ...}`.

## Harvard Dataverse (`dataverse.harvard.edu`)

Observed 2026-10-06. `GET /api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/NUKCNA`
describes *US Post Offices* (Blevins and Helbock), version 1.0, released
2021-03-31, CC0. Files include `us-post-offices.tab` (id 4491713, ingested
from `us-post-offices.csv`, `originalFileSize` 31,415,567), the data
dictionary, a variant with random coordinates for unplaced offices, and the
January 2021 GNIS national file (316 MB).

- **The published MD5 is the original upload's.**
  `/api/access/datafile/4491713?format=original` returns the CSV whose MD5 is
  `72a67b658fdc0befa5a0f48a909cd3dc`, as listed; the default `.tab` download
  does not match it, and `noVarHeader=true` answered 503.
- A download answers 303 to a signed URL on `dvn-cloud-iqss.s3.amazonaws.com`.
- The CSV: 166,140 rows, 29 columns, comma-separated with quoted strings, LF.
  112,521 have coordinates. `Discontinued` is blank for 29,089 (open in 2000),
  `Established` for 44. A few dates are slips: an `Established` of 185, a
  `Discontinued` of 19223, 45 offices discontinued before established. Six
  offices are in `MI/OH`, one in `VAy`. Helbock often writes names run
  together (`DESMET`, `SPRINGLAKE`) and variants in parentheses
  (`WAYNESBURG(H)`).
- Kingsbury County, S.D.: 33 offices, 15 open at some time in 1890.

## GLO Records links

Verified 2026-10-04 (see the research spec this server came from): a search
link is `https://glorecords.blm.gov/s/advanced-search?searchTerm=` followed by
the URL-encoded path `/search?q=…&page=1&pageSize=25`. A record link is
`…/s/advanced-search#/searchresults?documentid=<id>`.

- **The state filter is `geostatecodes`.** On 2026-10-06 BLM's search frame
  was observed sending `geostatecodes=SD` for a South Dakota search. The
  `State=SD` that 0.1.0 sent, read from the site's code, is ignored by the
  site, so 0.1.0's state filter did nothing. The page itself is a Salesforce
  community app and does not show the parameter; the search runs in a frame.
- The `documenttype` parameter is still taken from the site's code and not
  verified.

## National Archives bridge

`record_group_number "49"` with title `Lincoln Land Office (Nebraska),
Homestead Final Certificate No. 12018` returned NAID 63668992 (21 images)
first, and also certificate 7054: the Catalog's title search matches words.
