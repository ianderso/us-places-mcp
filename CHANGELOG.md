# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

## [0.2.0] — 2026-10-06

Vanished places, and the maps that show them.

### Added

- `find_place_name`: a named place in USGS's GNIS, with its point, class and
  county. Searches the live GNIS and, given a state, the archive of
  25 August 2021, which keeps the cemeteries, churches, schools, post offices,
  buildings and locales GNIS dropped that year; says which source answered and
  reports a feature found in both once. Mt., Ft., St. and Pt. are written out,
  and apostrophes dropped, as GNIS spells names.
- `historical_topo_maps`: every USGS topographic map covering a point, from
  The National Map's TNM Access API, oldest first, with date, scale,
  quadrangle, GeoPDF, GeoTIFF and JPEG preview links, and a TopoView link.
- `post_offices`: Blevins and Helbock's US post offices, 1639-2000, by name,
  state and today's county, around a point, and open in a given year.
- Datasets downloaded once to `<cache dir>/data`, checked before they are kept
  (the post-office file against Dataverse's MD5, a GNIS state file against its
  S3 ETag) and announced in the result that triggered the download.
  `cache_status` lists them.
- Settings `US_PLACES_GNIS_URL`, `US_PLACES_GNIS_ARCHIVE_URL`,
  `US_PLACES_TNM_URL` and `US_PLACES_DATAVERSE_URL`.

### Fixed

- `glo_links` sends its state filter as `geostatecodes`, the parameter BLM's
  search frame was observed using on 2026-10-06; the site ignored the `State`
  that 0.1.0 sent, so a state-filtered link searched every state.

### Changed

- The host allowlist covers the new services and Dataverse's file store; a
  download follows a redirect only to an allowed host.
- The tool-description budget rose from 4,500 to 5,500 characters, for the
  three new tools' warnings.
- Tool descriptions are dedented by the server, so mcp 2.0, which published
  docstrings with their indentation, sends the same text as later releases.

## [0.1.0] — 2026-10-05

First release.

### Added

- `county_at` and `county_history`: which county held a point on a date, and
  each county's succession, from the Newberry *Atlas of Historical County
  Boundaries* through OpenHistoricalMap, with statutes, "attached to" areas,
  contested ground and changes near the date.
- `parse_legal_description`, `plss_locate` and `plss_from_point`: land
  descriptions read, placed and named, with BLM's national PLSS data.
- `public_land_state`, `find_land_entry_file` and `glo_links`: which states
  hold federal land, the route from a patent to its case file (with
  nara-catalog-mcp search arguments), and GLO Records links.
- `cache_status`.
