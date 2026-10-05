# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

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
